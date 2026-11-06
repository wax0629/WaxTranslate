"""Run only on an isolated Windows desktop. Exercise the user-facing executable."""
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import subprocess
import sys
import time


def wait_for(predicate):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for the portable app window")


def check(root):
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
    exe = root / "WaxTranslate.exe"
    title = "我靠翻译 · WaxTranslate"
    assert not user.FindWindowW(None, title), "Only run this check on an isolated desktop"
    subprocess.run([exe], check=True)
    def visible_main():
        window = user.FindWindowW(None, title)
        return window if window and user.IsWindowVisible(window) else None

    # Qt creates the HWND during construction, before showing the main window.
    # Wait until that first show has happened before sending a minimize request.
    window = wait_for(visible_main)
    pid = wt.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    try:
        assert user.PostMessageW(window, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND / SC_MINIMIZE
        wait_for(lambda: user.IsIconic(window))
        subprocess.run([exe], check=True)
        wait_for(lambda: not user.IsIconic(window))
        assert user.FindWindowW(None, title) == window
        print("Launcher opened and restored the original window.", flush=True)
    finally:
        # The isolated runner has no user data or other instance. Ending this
        # exact child also exercises the gesture listener's parent-pipe cleanup.
        process = kernel.OpenProcess(1, False, pid.value)
        if process:
            kernel.TerminateProcess(process, 0)
            kernel.CloseHandle(process)
        wait_for(lambda: not user.FindWindowW(None, title))


if __name__ == "__main__":
    check(Path(sys.argv[1]))
