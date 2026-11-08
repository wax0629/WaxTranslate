"""Win32 input listener, run as a child of the UI process."""

import ctypes
from ctypes import wintypes as wt
import json
from queue import SimpleQueue
import sys
from threading import Thread, get_native_id


CTRL_KEYS = {"left": 0xA2, "right": 0xA3, "off": None}
TAP_LIMIT_MS = 350

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
VK_ESCAPE = 0x1B
REPLAY_TAG = 0x57585452
REPLAY_CLICK = 0x8001  # private message on the hook thread

user32 = ctypes.WinDLL("user32", use_last_error=True)
HookProc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HookProc, wt.HMODULE, wt.DWORD)
user32.SetWindowsHookExW.restype = wt.HANDLE
user32.CallNextHookEx.argtypes = (wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wt.HANDLE,)
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetCursorPos.argtypes = (ctypes.POINTER(wt.POINT),)
user32.SetThreadDpiAwarenessContext.argtypes = (wt.HANDLE,)
user32.SetThreadDpiAwarenessContext.restype = wt.HANDLE
user32.GetWindowRect.argtypes = (wt.HWND, ctypes.POINTER(wt.RECT))
user32.WindowFromPhysicalPoint.argtypes = (wt.POINT,)
user32.WindowFromPhysicalPoint.restype = wt.HWND
user32.GetAncestor.argtypes = (wt.HWND, wt.UINT)
user32.GetAncestor.restype = wt.HWND
user32.GetMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)


class KeyboardEvent(ctypes.Structure):
    _fields_ = [("vk", wt.DWORD), ("scan", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("extra", ctypes.c_size_t)]


class MouseEvent(ctypes.Structure):
    _fields_ = [("point", wt.POINT), ("data", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("extra", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("data", wt.DWORD),
                ("flags", wt.DWORD), ("time", wt.DWORD), ("extra", ctypes.c_size_t)]


class Input(ctypes.Structure):
    # MOUSEINPUT is the largest member of the native INPUT union.
    _fields_ = [("type", wt.DWORD), ("mouse", MouseInput)]


user32.SendInput.argtypes = (wt.UINT, ctypes.POINTER(Input), ctypes.c_int)


class CtrlGestures:
    def __init__(self, mode="left"):
        self.mode = mode
        self.held_ctrl = None
        self.pressed_at = 0
        self.armed = False
        self.origin = None
        self.dragging = False
        self.owns_button = False
        self.owns_escape = False
        self.handles = []
        self.keyboard_proc = HookProc(self.keyboard)
        self.mouse_proc = HookProc(self.mouse)
        self.events = SimpleQueue()
        self.watched_card = None

    def listen(self):
        # Windows drops slow hooks. Keep both Qt's event loop and the model's
        # Python GIL out of the listener, and do pipe I/O outside the callback.
        message = wt.MSG()
        # Match low-level pointer coordinates when reading native window bounds.
        user32.SetThreadDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
        self.thread_id = get_native_id()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        writer = Thread(target=self.write_events)
        writer.start()
        Thread(target=self.watch_parent, daemon=True).start()
        try:
            for kind, proc in ((13, self.keyboard_proc), (14, self.mouse_proc)):
                handle = user32.SetWindowsHookExW(kind, proc, None, 0)
                if not handle:
                    self.events.put(("error", ctypes.get_last_error(), None))
                    return
                self.handles.append(handle)
            self.events.put(("ready", self.mode, None))
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == REPLAY_CLICK:
                    pair = (Input * 2)(Input(mouse=MouseInput(flags=2, extra=REPLAY_TAG)),
                                       Input(mouse=MouseInput(flags=4, extra=REPLAY_TAG)))
                    if user32.SendInput(2, pair, ctypes.sizeof(Input)) == 1:
                        user32.SendInput(1, ctypes.byref(pair[1]), ctypes.sizeof(Input))
        finally:
            for handle in self.handles:
                user32.UnhookWindowsHookEx(handle)
            self.handles.clear()
            self.events.put(None)
            writer.join()

    def watch_parent(self):
        # Only observe clicks while the parent is showing a card. EOF also
        # releases both hooks if the application exits unexpectedly.
        try:
            for line in sys.stdin.buffer:
                ticket, hwnd, mode = json.loads(line)
                self.watched_card = (ticket, hwnd) if hwnd else None
                if mode != self.mode and mode in CTRL_KEYS:
                    self.mode = mode
                    self.events.put(("mode", mode, None))
        finally:
            user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT

    def write_events(self):
        while (event := self.events.get()) is not None:
            try:
                print(json.dumps(event), flush=True)
            except (BrokenPipeError, OSError):
                user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
                return

    def cancel(self):
        self.armed = False
        self.origin = None
        if self.dragging:
            self.dragging = False
            self.events.put(("cancel", None, None))

    def keyboard(self, code, message, payload):
        if code == 0:
            event = KeyboardEvent.from_address(payload)
            vk = event.vk
            down = message in (0x100, 0x104)  # WM_KEYDOWN / WM_SYSKEYDOWN
            wanted = CTRL_KEYS[self.mode]
            if self.held_ctrl is not None and self.held_ctrl != wanted:
                self.cancel()
            if vk == self.held_ctrl or (self.held_ctrl is None and vk == wanted):
                if down and self.held_ctrl is None:
                    self.held_ctrl = vk
                    self.pressed_at = event.time
                    # Also reject chords whose other key/button went down first.
                    self.armed = not any(user32.GetAsyncKeyState(key) & 0x8000
                                         for key in range(1, 255) if key not in (0x11, vk))
                elif not down:
                    elapsed = (event.time - self.pressed_at) & 0xffffffff
                    if self.armed and not self.owns_button and elapsed <= TAP_LIMIT_MS:
                        point = wt.POINT()
                        if user32.GetCursorPos(ctypes.byref(point)):
                            self.events.put(("lookup", (point.x, point.y), None))
                    self.held_ctrl = None
                    self.cancel()
            elif vk == VK_ESCAPE and (self.owns_escape or (down and self.owns_button)):
                self.owns_escape = down
                self.cancel()
                return 1
            elif down and self.held_ctrl is not None:
                self.cancel()
        return user32.CallNextHookEx(None, code, message, payload)

    def mouse(self, code, message, payload):
        if code == 0 and self.held_ctrl is not None and self.held_ctrl != CTRL_KEYS[self.mode]:
            self.cancel()
        card = self.watched_card
        if code == 0 and message == WM_LBUTTONDOWN and card:
            ticket, hwnd = card
            point = MouseEvent.from_address(payload).point
            bounds = wt.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(bounds)) and not (
                    bounds.left <= point.x < bounds.right and bounds.top <= point.y < bounds.bottom):
                # An owned menu can extend beyond the card. Observe the press
                # without intercepting or replaying it.
                target = user32.WindowFromPhysicalPoint(point)
                if user32.GetAncestor(target, 3) != hwnd:  # GA_ROOTOWNER
                    self.events.put(("dismiss", ticket, None))
        if code == 0 and (self.armed or self.owns_button):
            event = MouseEvent.from_address(payload)
            if event.extra != REPLAY_TAG and self.handle_mouse(message, (event.point.x, event.point.y)):
                return 1
        return user32.CallNextHookEx(None, code, message, payload)

    def handle_mouse(self, message, point):
        if message == WM_LBUTTONDOWN and self.armed:
            self.armed = False
            self.owns_button = True
            self.origin = point
            return True
        if message == WM_MOUSEMOVE and self.origin is not None:
            if self.dragging:
                self.events.put(("move", self.origin, point))
            elif (point[0] - self.origin[0]) ** 2 + (point[1] - self.origin[1]) ** 2 >= 8 ** 2:
                self.dragging = True
                self.events.put(("start", self.origin, point))
        elif message == WM_LBUTTONUP and self.owns_button:
            self.owns_button = False
            if self.dragging:
                self.events.put(("finish", self.origin, point))
            elif self.origin is not None:
                # Replay a plain Ctrl+click to its foreground app. The tag keeps
                # this pair out of our own recognizer.
                user32.PostThreadMessageW(self.thread_id, REPLAY_CLICK, 0, 0)
            self.dragging = False
            self.origin = None
            return True
        elif message != WM_MOUSEMOVE:
            self.cancel()
        return False


if __name__ == "__main__":
    CtrlGestures(sys.argv[1] if len(sys.argv) > 1 else "left").listen()
