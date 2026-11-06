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
    user.ShowWindow.argtypes = (wt.HWND, ctypes.c_int)
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
    window = wait_for(lambda: user.FindWindowW(None, title))
    pid = wt.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    try:
        user.ShowWindow(window, 6)  # SW_MINIMIZE
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
