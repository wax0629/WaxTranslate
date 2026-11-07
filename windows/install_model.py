"""Install the pinned offline translation and English part-of-speech models."""

import argparse
import hashlib
from http.client import IncompleteRead
import os
from pathlib import Path
import shutil
import tempfile
from urllib.error import URLError
import urllib.request
import zipfile


PACKAGE = "translate-en_zh-1_9"
URL = f"https://argos-net.com/v1/{PACKAGE}.argosmodel"
MIRROR = f"https://data.argosopentech.com/argospm/v1/{PACKAGE}.argosmodel"
DIGEST = "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab"
MODEL = Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "models" / PACKAGE
FILES = ("model/model.bin", "model/config.json", "model/shared_vocabulary.json",
         "sentencepiece.model", "README.md", "metadata.json")
POS_PACKAGE = "averaged_perceptron_tagger_eng"
POS_ARCHIVE = MODEL.parent / f"{POS_PACKAGE}.zip"
POS_SHA = "6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b"
POS_URL = ("https://raw.githubusercontent.com/nltk/nltk_data/"
           f"304a3c5432dd2fe08ae8b436dc6eec54c3593445/packages/taggers/{POS_ARCHIVE.name}")


def install_word_tags():
    if POS_ARCHIVE.is_file():
        with POS_ARCHIVE.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() == POS_SHA:
                return
    print("Downloading English part-of-speech model (1.5 MiB)...", flush=True)
    POS_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=POS_ARCHIVE.parent) as stage:
        pending = Path(stage) / POS_ARCHIVE.name
        with urllib.request.urlopen(POS_URL, timeout=90) as response, pending.open("wb") as output:
            shutil.copyfileobj(response, output)
        with pending.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != POS_SHA:
                raise ValueError("English part-of-speech model checksum mismatch.")
        os.replace(pending, POS_ARCHIVE)


def install(archive=None):
    if all((MODEL / name).is_file() for name in FILES):
        return
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL.parent) as stage:
        if archive is None:
            print("Downloading English -> Chinese model (67.5 MiB)...", flush=True)
            archive = Path(stage) / "download.zip"
            for url in (URL, MIRROR):
                try:
                    with urllib.request.urlopen(url, timeout=90) as response, archive.open("wb") as output:
                        shutil.copyfileobj(response, output)
                    break
                except (URLError, TimeoutError, IncompleteRead) as error:
                    if url == MIRROR:
                        raise
                    print(f"Download failed ({error}); trying the Argos model archive.", flush=True)
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
    install_word_tags()
    print(f"Model ready at {MODEL}")
