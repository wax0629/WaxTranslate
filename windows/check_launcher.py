"""Run only on an isolated Windows desktop. Exercise the user-facing executable."""
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
from uuid import uuid4
import winreg


def wait_for(predicate, description):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for " + description)


def python_children(parent_pid):
    # The launcher exits immediately after spawning pythonw. ParentProcessId
    # stays with the child, even before Qt creates a window for a tray launch.
    query = f"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' AND ParentProcessId={parent_pid}\""
    result = subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                      query + " | Select-Object -ExpandProperty ProcessId"],
                                     creationflags=subprocess.CREATE_NO_WINDOW, text=True)
    return [int(pid) for pid in result.split()]


def registered_command():
    import startup

    # Exercise the portable copy's real Run command without enrolling the
    # runner account for startup. This random key is outside the Run tree.
    key_path = rf"Software\WaxTranslate.Test.{uuid4().hex}"
    with patch.object(startup, "RUN", key_path), patch.object(startup, "APPROVED", key_path + r"\Approved"):
        try:
            registration = startup.LoginStartup()
            registration.set_enabled(True)
            assert registration.status() == "on"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                command, kind = winreg.QueryValueEx(key, startup.NAME)
            assert kind == winreg.REG_SZ
            registration.set_enabled(False)
            assert registration.status() == "off"
            return command
        finally:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                pass


def launch(command):
    with subprocess.Popen(command) as launcher:
        assert launcher.wait(timeout=15) == 0
        return launcher.pid


def check(root):
    from instance import EVENT_NAME
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    app = QApplication([])
    has_tray = QSystemTrayIcon.isSystemTrayAvailable()
    user = ctypes.windll.user32
    user.FindWindowW.argtypes = (wt.LPCWSTR, wt.LPCWSTR)
    user.FindWindowW.restype = wt.HWND
    user.IsIconic.argtypes = (wt.HWND,)
    user.IsWindowVisible.argtypes = (wt.HWND,)
    user.PostMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.TerminateProcess.argtypes = (wt.HANDLE, wt.UINT)
    kernel.CloseHandle.argtypes = (wt.HANDLE,)
    kernel.OpenEventW.argtypes = (wt.DWORD, wt.BOOL, wt.LPCWSTR)
    kernel.OpenEventW.restype = wt.HANDLE
    exe = root / "WaxTranslate.exe"
    title = "WaxTranslate"
    assert not user.FindWindowW(None, title), "Only run this check on an isolated desktop"
    existing = kernel.OpenEventW(0x00100000, False, EVENT_NAME)
    if existing:
        kernel.CloseHandle(existing)
        raise AssertionError("An existing tray instance is running; use an isolated desktop")

    def visible_main():
        window = user.FindWindowW(None, title)
        return window if window and user.IsWindowVisible(window) else None

    command = registered_command()
    launcher_pid = launch(command)
    pid, = wait_for(lambda: python_children(launcher_pid), "the login launcher's child")
    try:
        wait_for(lambda: python_children(pid), "the background app's gesture listener")
        if has_tray:
            assert not visible_main(), "Login startup showed the main window"
        else:
            wait_for(visible_main, "visible fallback without a system tray")
        repeat = launch(command)
        wait_for(lambda: not python_children(repeat), "the second background launch to exit")
        if has_tray:
            assert not visible_main(), "Repeated login launch raised the hidden app"
        launch([exe])
        window = wait_for(visible_main, "the manually activated window")
        active_pid = wt.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(active_pid))
        assert active_pid.value == pid, "A second main instance opened"
        assert user.PostMessageW(window, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND / SC_MINIMIZE
        wait_for(lambda: user.IsIconic(window), "the main window to minimize")
        repeat = launch(command)
        wait_for(lambda: not python_children(repeat), "the redundant login launch to exit")
        assert user.IsIconic(window), "Background launch restored a minimized app"
        launch([exe])
        wait_for(lambda: not user.IsIconic(window), "manual launch to restore the window")
        assert user.FindWindowW(None, title) == window
        startup = "hidden tray startup" if has_tray else "visible fallback (no system tray)"
        print(f"Verified {startup}, quiet repeat login and manual activation of the same PID.", flush=True)
    finally:
        # The isolated runner has no user data or other instance. Ending this
        # exact child also exercises the gesture listener's parent-pipe cleanup.
        process = kernel.OpenProcess(1, False, pid)
        if process:
            kernel.TerminateProcess(process, 0)
            kernel.CloseHandle(process)
        wait_for(lambda: not user.FindWindowW(None, title), "the isolated instance to exit")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
