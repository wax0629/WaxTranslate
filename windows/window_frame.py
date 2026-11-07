"""Native resize borders and caption dragging for the Windows navigation bar."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QAbstractButton


user32 = ctypes.windll.user32
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.LONG)
user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT)
dwm = ctypes.windll.dwmapi
dwm.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)

GWL_STYLE = -16
WS_MINIMIZEBOX = 0x20000
WS_MAXIMIZEBOX = 0x10000
WM_NCHITTEST = 0x84
HTCAPTION = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUNDSMALL = 3


def configure_frame(window):
    if QApplication.platformName() != "windows":
        return
    hwnd = int(window.winId())
    # Qt's CustomizeWindowHint supplies the native sizing frame. Requesting
    # Qt's min/max title buttons would also reinstate the system caption.
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    buttons = WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    if style & buttons != buttons:
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | buttons)
        # Recalculate the frame without changing size, position, stacking or focus.
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
    preference = wintypes.DWORD(DWMWCP_ROUNDSMALL)
    dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                              ctypes.byref(preference), ctypes.sizeof(preference))


def caption_hit(window, message):
    msg = wintypes.MSG.from_address(int(message))
    if msg.message != WM_NCHITTEST:
        return False
    # WM_NCHITTEST uses signed physical screen pixels, including on displays
    # left of the primary. Convert to client DIPs before testing Qt controls.
    pos = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                         ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
    if not user32.ScreenToClient(msg.hWnd, ctypes.byref(pos)):
        return False
    scale = window.devicePixelRatioF()
    local = QPoint(int(pos.x // scale), int(pos.y // scale))
    if not window.sidebar.geometry().contains(local):
        return False
    return not isinstance(window.childAt(local), QAbstractButton)
