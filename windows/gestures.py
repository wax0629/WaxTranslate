"""Global left-Ctrl tap and drag gestures for the Windows Qt message loop."""

import ctypes
from ctypes import wintypes as wt
from threading import Event, Thread, get_native_id

from PySide6.QtCore import QObject, Signal


LOOKUP_HINT = "轻按左 Ctrl"
REGION_HINT = "按住左 Ctrl，左键拖动"

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
VK_LCONTROL, VK_ESCAPE = 0xA2, 0x1B
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
user32.GetMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)


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


class CtrlGestures(QObject):
    # Coordinates in hook events are physical screen pixels. The receiver is
    # queued so painting, screenshots and OCR never run inside a Win32 hook.
    action = Signal(str, object, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.ctrl_down = False
        self.armed = False
        self.origin = None
        self.dragging = False
        self.owns_button = False
        self.owns_escape = False
        self.handles = []
        self.keyboard_proc = HookProc(self.keyboard)
        self.mouse_proc = HookProc(self.mouse)
        self.error = None
        self.ready = Event()
        self.thread = Thread(target=self.listen, name="Ctrl gestures", daemon=True)
        self.thread.start()
        self.ready.wait()

    def listen(self):
        self.thread_id = get_native_id()
        message = wt.MSG()
        # Establish a queue before advertising readiness or accepting WM_QUIT.
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        try:
            for kind, proc in ((13, self.keyboard_proc), (14, self.mouse_proc)):
                handle = user32.SetWindowsHookExW(kind, proc, None, 0)
                if not handle:
                    self.error = ctypes.get_last_error()
                    return
                self.handles.append(handle)
            self.ready.set()
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
            self.ready.set()

    def stop(self):
        if self.thread.is_alive():
            user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT
            self.thread.join()

    def cancel(self):
        self.armed = False
        self.origin = None
        if self.dragging:
            self.dragging = False
            self.action.emit("cancel", None, None)

    def keyboard(self, code, message, payload):
        if code == 0:
            vk = wt.DWORD.from_address(payload).value
            down = message in (0x100, 0x104)  # WM_KEYDOWN / WM_SYSKEYDOWN
            if vk == VK_LCONTROL:
                if down and not self.ctrl_down:
                    self.ctrl_down = True
                    # Also reject chords whose other key/button went down first.
                    self.armed = not any(user32.GetAsyncKeyState(key) & 0x8000
                                         for key in range(1, 255) if key not in (0x11, VK_LCONTROL))
                elif not down:
                    if self.armed and not self.owns_button:
                        point = wt.POINT()
                        if user32.GetCursorPos(ctypes.byref(point)):
                            self.action.emit("lookup", (point.x, point.y), None)
                    self.ctrl_down = False
                    self.cancel()
            elif vk == VK_ESCAPE and (self.owns_escape or (down and self.owns_button)):
                self.owns_escape = down
                self.cancel()
                return 1
            elif down and self.ctrl_down:
                self.cancel()
        return user32.CallNextHookEx(None, code, message, payload)

    def mouse(self, code, message, payload):
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
                self.action.emit("move", self.origin, point)
            elif (point[0] - self.origin[0]) ** 2 + (point[1] - self.origin[1]) ** 2 >= 8 ** 2:
                self.dragging = True
                self.action.emit("start", self.origin, point)
        elif message == WM_LBUTTONUP and self.owns_button:
            self.owns_button = False
            if self.dragging:
                self.action.emit("finish", self.origin, point)
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
