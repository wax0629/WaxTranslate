"""Install the pinned English → Chinese Argos/OPUS-MT model for this user."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile


PACKAGE = "translate-en_zh-1_9"
URL = f"https://argos-net.com/v1/{PACKAGE}.argosmodel"
DIGEST = "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab"
MODEL = Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "models" / PACKAGE
FILES = ("model/model.bin", "model/config.json", "model/shared_vocabulary.json",
         "sentencepiece.model", "README.md", "metadata.json")


def install(archive=None):
    if all((MODEL / name).is_file() for name in FILES):
        return
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL.parent) as stage:
        if archive is None:
            print("Downloading English -> Chinese model (67.5 MiB)...", flush=True)
            archive = Path(stage) / "download.zip"
            with urllib.request.urlopen(URL, timeout=90) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        with open(archive, "rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != DIGEST:
                raise ValueError("Model checksum mismatch. Please download the package again.")
        extracted = Path(stage) / PACKAGE
        with zipfile.ZipFile(archive) as bundle:
            for name in FILES:
                path = extracted / name
                path.parent.mkdir(exist_ok=True, parents=True)
                with bundle.open(f"{PACKAGE}/{name}") as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output)
        try:
            extracted.rename(MODEL)
        except FileExistsError:
            if not all((MODEL / name).is_file() for name in FILES):
                raise RuntimeError(f"Incomplete model at {MODEL}. Move that folder aside and retry.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="install from an already downloaded .argosmodel")
    install(parser.parse_args().archive)
    print(f"Model ready at {MODEL}")
