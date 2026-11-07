import ctypes
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
import winreg

import startup


class LoginStartupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())) / "便携 测试"
        # Exercise winreg without putting anything in Windows' real logon keys.
        branch = rf"Software\WaxTranslate-Test-{uuid4().hex}"
        self.run = branch + r"\Commands"
        self.approval = branch + r"\Approval"
        self.enterContext(patch.object(startup, "RUN", self.run))
        self.enterContext(patch.object(startup, "APPROVED", self.approval))
        self.addCleanup(self.clean_keys, [self.approval, self.run, branch])

    @staticmethod
    def clean_keys(paths):
        for path in paths:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass

    def install(self, name, portable=True):
        root = self.root / name
        python_dir = root / ("runtime" if portable else ".venv/Scripts")
        script = root / "windows/app.py"
        for path in (script, python_dir / "pythonw.exe", root / "WaxTranslate.exe"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        with patch.object(startup, "__file__", str(script.with_name("startup.py"))), \
                patch.object(startup.sys, "executable", str(python_dir / "python.exe")):
            return startup.LoginStartup()

    def write(self, path, name, data, kind=winreg.REG_SZ):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, kind, data)

    def read(self, path, name=startup.NAME):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]

    def argv(self, command):
        # Windows must round-trip the same argument boundaries the registry will launch.
        argc = ctypes.c_int()
        parse = ctypes.windll.shell32.CommandLineToArgvW
        parse.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int))
        parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
        argv = parse(command, ctypes.byref(argc))
        self.assertTrue(argv)
        try:
            return argv[:argc.value]
        finally:
            release = ctypes.windll.kernel32.LocalFree
            release.argtypes = (ctypes.c_void_p,)
            release.restype = ctypes.c_void_p
            release(argv)

    def test_registration_roundtrip_and_relocation(self):
        first = self.install("原 始")
        self.assertEqual(first.status(), "off")
        first.set_enabled(False)
        with self.assertRaises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.run)
        self.write(self.run, "OtherApp", "keep")
        first.set_enabled(True)
        first.set_enabled(True)
        self.assertEqual(first.status(), "on")
        self.assertEqual(self.argv(self.read(self.run)),
                         [str((self.root / "原 始/WaxTranslate.exe").resolve()), "--background"])
        moved = self.install("开发 目录", portable=False)
        original = self.read(self.run)
        self.assertEqual(moved.status(), "moved")
        self.assertEqual(self.read(self.run), original)
        moved.set_enabled(True)
        self.assertEqual(moved.status(), "on")
        self.assertEqual(self.argv(self.read(self.run)),
                         [str((self.root / "开发 目录/.venv/Scripts/pythonw.exe").resolve()),
                          str((self.root / "开发 目录/windows/app.py").resolve()), "--background"])
        moved.set_enabled(False)
        moved.set_enabled(False)
        self.assertEqual(moved.status(), "off")
        self.assertEqual(self.read(self.run, "OtherApp"), "keep")

    def test_system_disable_is_observed_and_preserved(self):
        service = self.install("installed")
        service.set_enabled(True)
        for flag, status in ((2, "on"), (3, "blocked"), (6, "on"), (7, "blocked")):
            value = flag.to_bytes(4, "little") + bytes(8)
            self.write(self.approval, startup.NAME, value, winreg.REG_BINARY)
            self.assertEqual(service.status(), status)
            service.set_enabled(True)
            self.assertEqual(self.read(self.approval), value)
        service.set_enabled(False)
        self.assertEqual(service.status(), "off")
        self.assertEqual(self.read(self.approval), value)
        service.set_enabled(True)
        self.assertEqual(service.status(), "blocked")

    def test_registration_failure_preserves_previous_command(self):
        original = self.install("one")
        original.set_enabled(True)
        stored = self.read(self.run)
        moved = self.install("two")
        (self.root / "two/WaxTranslate.exe").unlink()
        with self.assertRaisesRegex(ValueError, "找不到启动文件"):
            moved.set_enabled(True)
        self.assertEqual(self.read(self.run), stored)
        with patch.object(moved, "paths", (self.root / ("🙂" * 129 + ".exe"),)):
            with self.assertRaisesRegex(ValueError, "路径过长"):
                moved.set_enabled(True)
        self.assertEqual(self.read(self.run), stored)
        with patch("winreg.CreateKeyEx", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                self.install("three").set_enabled(True)
        self.assertEqual(self.read(self.run), stored)

    def test_unrelated_command_under_same_name_is_preserved(self):
        service = self.install("one")
        for command in ('"C:\\Tools\\AnotherApp.exe" --background', 'Not a "valid command'):
            self.write(self.run, startup.NAME, command)
            with self.assertRaisesRegex(ValueError, "其他命令"):
                service.status()
            for enabled in (True, False):
                with self.assertRaisesRegex(ValueError, "其他命令"):
                    service.set_enabled(enabled)
            self.assertEqual(self.read(self.run), command)


if __name__ == "__main__":
    unittest.main()
