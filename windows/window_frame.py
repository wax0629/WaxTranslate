"""Borderless Windows client area with native resizing and caption dragging."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QAbstractButton, QWidget


class MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


user32 = ctypes.windll.user32
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.LONG)
user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.IsZoomed.argtypes = (wintypes.HWND,)
user32.MonitorFromRect.argtypes = (ctypes.POINTER(wintypes.RECT), wintypes.DWORD)
user32.MonitorFromRect.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
user32.IntersectRect.argtypes = (ctypes.POINTER(wintypes.RECT),) * 3
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
dwm = ctypes.windll.dwmapi
dwm.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)

GWL_STYLE = -16
WS_MINIMIZEBOX = 0x20000
WS_MAXIMIZEBOX = 0x10000
WS_SYSMENU = 0x80000
WM_NCCALCSIZE = 0x83
WM_NCHITTEST = 0x84
WM_NCLBUTTONDOWN = 0xa1
WM_SYSCOMMAND = 0x112
SC_SIZE = 0xf000
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = range(10, 18)
HTCAPTION = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUNDSMALL = 3
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xfffffffe


class WindowOutline(QWidget):
    """One physical pixel over the content, without consuming a layout or resize margin."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        if self.window().isMaximized() or self.window().isFullScreen():
            return
        half_pixel = 0.5 / self.devicePixelRatioF()
        bounds = QRectF(self.rect()).adjusted(half_pixel, half_pixel, -half_pixel, -half_pixel)
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(119, 115, 108, 82), 0))
            painter.drawRoundedRect(bounds, 4, 4)


def configure_frame(window):
    if QApplication.platformName() != "windows":
        return
    hwnd = int(window.winId())
    # A native sizing frame can paint over even a full-size client area.
    # Keep the system commands on the frameless HWND, with resize hits below.
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    buttons = WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    if style & buttons != buttons:
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | buttons)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
    preference = wintypes.DWORD(DWMWCP_ROUNDSMALL)
    dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                              ctypes.byref(preference), ctypes.sizeof(preference))
    border = wintypes.DWORD(DWMWA_COLOR_NONE)
    dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border))


def frame_result(window, message):
    msg = wintypes.MSG.from_address(int(message))
    if msg.message == WM_NCCALCSIZE:
        # The first RECT is the proposed outer bounds in both message forms.
        # Keep maximized content inside the work area, including on secondary monitors.
        if user32.IsZoomed(msg.hWnd) and not window.isFullScreen():
            bounds = wintypes.RECT.from_address(msg.lParam)
            monitor = user32.MonitorFromRect(ctypes.byref(bounds), 2)  # MONITOR_DEFAULTTONEAREST
            info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                return None
            user32.IntersectRect(ctypes.byref(bounds), ctypes.byref(bounds), ctypes.byref(info.work))
        return 0
    if msg.message == WM_NCLBUTTONDOWN and HTLEFT <= msg.wParam <= HTBOTTOMRIGHT:
        # A frameless HWND does not turn border presses into SC_SIZE by itself.
        # WMSZ_LEFT..WMSZ_BOTTOMRIGHT and HTLEFT..HTBOTTOMRIGHT use the same order.
        direction = 1 + msg.wParam - HTLEFT
        user32.PostMessageW(msg.hWnd, WM_SYSCOMMAND, SC_SIZE | direction, msg.lParam)
        return 0
    if msg.message != WM_NCHITTEST:
        return None
    # WM_NCHITTEST uses signed physical screen pixels, including on displays
    # left of the primary. Convert to client DIPs before testing Qt controls.
    pos = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                         ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
    if not user32.ScreenToClient(msg.hWnd, ctypes.byref(pos)):
        return None
    scale = window.devicePixelRatioF()
    if not user32.IsZoomed(msg.hWnd):
        rect = wintypes.RECT()
        user32.GetClientRect(msg.hWnd, ctypes.byref(rect))
        grip = max(1, round(6 * scale))
        left, right = pos.x < grip, pos.x >= rect.right - grip
        if pos.y < grip:
            return HTTOPLEFT if left else HTTOPRIGHT if right else HTTOP
        if pos.y >= rect.bottom - grip:
            return HTBOTTOMLEFT if left else HTBOTTOMRIGHT if right else HTBOTTOM
        if left or right:
            return HTLEFT if left else HTRIGHT
    local = QPoint(int(pos.x // scale), int(pos.y // scale))
    if window.sidebar.geometry().contains(local) and not isinstance(window.childAt(local), QAbstractButton):
        return HTCAPTION
    return None
