"""Build an offline x64 ZIP with Microsoft's system C# compiler and embedded CPython."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import urllib.request
import zipfile

from install_model import LEXICON, MODELS, MODEL_DIR, POS_ARCHIVE, install, install_lexicon, install_word_tags

SRC = Path(__file__).resolve().parent
PYTHON_ZIP = "python-3.12.10-embed-amd64.zip"
PYTHON_SHA = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
APP_FILES = ("app.py", "gestures.py", "library.py", "notebook.py", "popup.py", "reader.py", "translation.py",
             "instance.py", "theme.py", "workspace.py", "word_details.py", "install_model.py", "speech.py",
             "speech_worker.py", "lexicon.py", "lookup.py", "online_terms.py", "terminology.py", "startup.py",
             "settings_page.py", "home.py", "languages.py", "window_frame.py", "waxtranslate.ico")


def build(output, archive=None):
    if sys.version_info[:2] != (3, 12) or sys.maxsize < 2**32 or sys.platform != "win32":
        raise SystemExit("Build with 64-bit Python 3.12 on Windows.")
    install()
    install_word_tags()
    install_lexicon()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)
        root = stage / "WaxTranslate"
        runtime = root / "runtime"
        if archive is None:
            archive = stage / PYTHON_ZIP
            url = "https://www.python.org/ftp/python/3.12.10/" + PYTHON_ZIP
            urllib.request.urlretrieve(url, archive)
        with archive.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != PYTHON_SHA:
                raise ValueError("Embedded Python checksum mismatch.")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(runtime)
        (runtime / "python312._pth").write_text(
            "python312.zip\n.\nLib/site-packages\n../windows\nimport site\n", encoding="ascii")
        packages = runtime / "Lib/site-packages"
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                        "--only-binary=:all:", "--no-compile", "--target", str(packages),
                        "-r", str(SRC / "requirements.txt")], check=True)
        # Some non-Qt extensions load before Qt adds its DLL directory.
        for dll in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll"):
            shutil.copy2(packages / "PySide6" / dll, runtime / dll)
        (root / "windows").mkdir()
        for name in APP_FILES:
            shutil.copy2(SRC / name, root / "windows" / name)
        shutil.copytree(SRC / "fonts", root / "windows/fonts")
        for asset in (Path("Assets/Brand/barrette.svg"), Path("Assets/Editorial/glance.png")):
            (root / asset.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy2(SRC.parent / asset, root / asset)
        for package in MODELS.values():
            for name in package.files:
                relative = Path(package.name) / name
                dest = root / "models" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(MODEL_DIR / relative, dest)
        shutil.copy2(POS_ARCHIVE, root / "models" / POS_ARCHIVE.name)
        shutil.copy2(SRC / "licenses/english-pos.txt", root / "models/english-pos-LICENSE.txt")
        shutil.copy2(LEXICON, root / "models" / LEXICON.name)
        shutil.copy2(SRC / "licenses/ecdict.txt", root / "models/ecdict-LICENSE.txt")
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                        "/r:System.Windows.Forms.dll", "/codepage:65001", "/win32icon:" + str(SRC / "waxtranslate.ico"),
                        "/out:" + str(root / "WaxTranslate.exe"), str(SRC / "Launcher.cs")], check=True)
        shutil.copy2(SRC / "portable-readme.txt", root / "使用说明.txt")
        zipped = shutil.make_archive(str(stage / "windows-x64"), "zip", stage, root.name)
        os.replace(zipped, output)
    print(output, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runtime-archive", type=Path)
    opts = parser.parse_args()
    build(opts.output, opts.runtime_archive)
