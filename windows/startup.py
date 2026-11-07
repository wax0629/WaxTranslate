"""Register this copy for the current user's next Windows sign-in."""
from pathlib import Path
import shlex
import sys
import winreg


RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
NAME = "WaxTranslate"


def _value(key_path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
            return winreg.QueryValueEx(key, NAME)
    except FileNotFoundError:
        return None


class LoginStartup:
    def __init__(self):
        self.script = Path(__file__).parent.resolve() / "app.py"
        root = self.script.parents[1]
        # %TEMP% and the executable can use a DOS short path while Python's
        # module path is expanded. Keep the venv's pythonw, resolving its directory.
        interpreter_dir = Path(sys.executable).parent.resolve()
        self.pythonw = interpreter_dir / "pythonw.exe"
        if interpreter_dir == root / "runtime":
            self.paths = (root / "WaxTranslate.exe",)
        else:
            self.paths = (self.pythonw, self.script)

    def _registered_paths(self):
        item = _value(RUN)
        if item is None:
            return ()
        command, kind = item
        if kind == winreg.REG_SZ:
            # File paths have no embedded double quotes; accept both the
            # quoted form we write and a bare path with no spaces.
            try:
                tokens = shlex.split(command, posix=False)
            except ValueError:
                tokens = []
            if tokens and tokens[-1] == "--background":
                paths = tuple(Path(token.strip('"')) for token in tokens[:-1])
                portable = len(paths) == 1 and paths[0].name.lower() == "waxtranslate.exe"
                source = (len(paths) == 2 and paths[0].name.lower() == "pythonw.exe"
                          and paths[1].parent.name.lower() == "windows" and paths[1].name.lower() == "app.py")
                if (portable or source) and all(path.is_absolute() for path in paths):
                    return paths
        raise ValueError("Windows 已有其他命令使用 WaxTranslate 这个启动项名称。请先检查该启动项。")

    def status(self):
        """off / on / moved / blocked; reading never changes the registry."""
        registered = self._registered_paths()
        if not registered:
            return "off"
        if registered != self.paths:
            return "moved"
        approval = _value(APPROVED)
        if approval and approval[1] == winreg.REG_BINARY and len(approval[0]) >= 4:
            # Explorer manages this blob. Observe its disabled states without
            # clearing the user's decision when changing the Run registration.
            if int.from_bytes(approval[0][:4], "little") in (3, 7, 9):
                return "blocked"
        return "on"

    def set_enabled(self, enabled):
        registered = self._registered_paths()
        if not enabled:
            if registered:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, NAME)
                except FileNotFoundError:
                    pass
            return
        command = " ".join(f'"{path}"' for path in self.paths) + " --background"
        # Windows documents a maximum of 260 characters for a Run command.
        if len(command.encode("utf-16-le")) // 2 > 260:
            raise ValueError("启动路径过长。请将程序移到较短的路径，再开启登录启动。")
        if not all(path.is_file() for path in {*self.paths, self.script, self.pythonw}):
            raise ValueError("找不到启动文件。请确认程序已完整解压或开发环境已安装。")
        if registered != self.paths:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command)
