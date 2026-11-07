"""Run only on an isolated Windows desktop. Exercise the user-facing executable."""
import ctypes
from ctypes import wintypes as wt
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
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
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    app = QApplication([])
    has_tray = QSystemTrayIcon.isSystemTrayAvailable()
    user = ctypes.windll.user32
    user.FindWindowW.argtypes = (wt.LPCWSTR, wt.LPCWSTR)
    user.FindWindowW.restype = wt.HWND
    user.IsIconic.argtypes = (wt.HWND,)
    user.IsWindowVisible.argtypes = (wt.HWND,)
    user.GetWindowLongW.argtypes = (wt.HWND, ctypes.c_int)
    user.PostMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.TerminateProcess.argtypes = (wt.HANDLE, wt.UINT)
    kernel.CloseHandle.argtypes = (wt.HANDLE,)
    kernel.WaitForSingleObject.argtypes = (wt.HANDLE, wt.DWORD)
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
    assert command == f'"{exe.resolve()}" --background', f"Expected the portable launcher, got {command!r}"
    for login in (False, True):
        if login:
            # A fresh login uses the real registered command and the alternate
            # explicit close setting, in this test's own temporary profile.
            prefs = QSettings(str(Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate/preferences.ini"), QSettings.IniFormat)
            prefs.setValue("closeBehavior", "quit")
            prefs.sync()
            assert prefs.status() == QSettings.NoError
        launcher_pid = launch(command if login else [exe])
        pid, = wait_for(lambda: python_children(launcher_pid), "the launcher's child")
        process = kernel.OpenProcess(0x00100001, False, pid)  # SYNCHRONIZE | PROCESS_TERMINATE
        assert process
        try:
            wait_for(lambda: python_children(pid), "the app's background gesture listener")
            if has_tray:
                assert not visible_main(), "Cold startup showed the main window"
            else:
                wait_for(visible_main, "visible fallback without a system tray")
            repeat = launch(command)
            wait_for(lambda: not python_children(repeat), "the redundant background launch to exit")
            if has_tray:
                assert not visible_main(), "Repeated login launch raised the hidden app"
            launch([exe])
            window = wait_for(visible_main, "the manually activated window")
            active_pid = wt.DWORD()
            user.GetWindowThreadProcessId(window, ctypes.byref(active_pid))
            assert active_pid.value == pid, "A second main instance opened"
            style = user.GetWindowLongW(window, -16)
            ex_style = user.GetWindowLongW(window, -20)
            assert bool(ex_style & 0x80) == has_tray, f"Unexpected WS_EX_TOOLWINDOW: {ex_style:#x}"
            if has_tray:
                assert not ex_style & 0x40000, f"Unexpected WS_EX_APPWINDOW: {ex_style:#x}"
            assert style & 0x70000 == 0x70000, f"Missing resize/minimize/maximize style: {style:#x}"
            if not login:
                def stowed():
                    return not user.IsWindowVisible(window) if has_tray else user.IsIconic(window)

                assert user.PostMessageW(window, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND / SC_MINIMIZE
                wait_for(stowed, "minimize into the tray or ordinary taskbar")
                repeat = launch(command)
                wait_for(lambda: not python_children(repeat), "the repeat background launch to exit")
                assert stowed(), "Background launch reopened the minimized window"
                launch([exe])
                wait_for(lambda: visible_main() == window and not user.IsIconic(window), "restore the same window")
            assert user.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE
            if login or not has_tray:
                assert kernel.WaitForSingleObject(process, 10000) == 0, "The app did not exit"
            else:
                wait_for(lambda: not user.IsWindowVisible(window), "close into the tray by default")
                assert kernel.WaitForSingleObject(process, 0) == 258, "Close unexpectedly exited"
        finally:
            try:
                if kernel.WaitForSingleObject(process, 0) == 258:
                    kernel.TerminateProcess(process, 0)
                    assert kernel.WaitForSingleObject(process, 10000) == 0
            finally:
                kernel.CloseHandle(process)
    print(f"Verified both cold-start commands, taskbar styles, minimize/close and single-instance restore "
          f"(system tray available: {has_tray}).", flush=True)


if __name__ == "__main__":
    with TemporaryDirectory() as profile, patch.dict(os.environ, {"LOCALAPPDATA": profile}):
        check(Path(sys.argv[1]))
