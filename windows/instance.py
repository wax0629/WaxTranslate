"""Use one auto-reset event per interactive session for single-instance activation."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QWinEventNotifier
from shiboken6 import VoidPtr


def activation_event(app):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateEventW(None, False, False, r"Local\WaxTranslate.Activate.1")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel.SetEvent(handle)
        kernel.CloseHandle(handle)
        return None
    notifier = QWinEventNotifier(VoidPtr(handle), app)

    def close():
        notifier.setEnabled(False)
        kernel.CloseHandle(handle)

    app.aboutToQuit.connect(close)
    return notifier
