"""Install the pinned offline models and English-Chinese dictionary."""

import argparse
from contextlib import closing
import csv
import hashlib
from http.client import IncompleteRead
import os
from pathlib import Path
import re
import shutil
import sqlite3
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
ECDICT_REV = "39cfb9672c0906b63569e0453c2e6abfb9ab182a"
ECDICT_URL = f"https://raw.githubusercontent.com/skywind3000/ECDICT/{ECDICT_REV}/ecdict.csv"
ECDICT_SHA = "d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc"
LEXICON = MODEL.parent / f"ecdict-{ECDICT_REV[:8]}-v2.sqlite3"

_LINES = re.compile(r"\\r\\n|\\n|\r?\n")
_POS = re.compile(r"^(?:a|adj|adv|abbr|art|aux|conj|det|int|interj|n|num|p|pl|prep|pron|v|vi|vt)\.\s*", re.I)
_LABEL = re.compile(r"\[[^\]]{1,24}\]")
_CHINESE = re.compile(r"[\u3400-\u9fff]")


def _brief_gloss(translation):
    for line in _LINES.split(translation):
        line = _POS.sub("", line.strip()).strip()
        # A label such as "[网络]" alone does not make an echoed headword a gloss.
        if not _CHINESE.search(_LABEL.sub("", line)):
            continue
        if len(line) > 96:
            separators = list(re.finditer(r"[;,，；。]", line[:96]))
            end = separators[-1].start() if separators and separators[-1].start() >= 12 else 95
            line = line[:end].rstrip() + "…"
        return line
    return ""


def _common_word(row):
    # BNC and contemporary rank 1 denote the most frequent word; 0 means
    # unranked. Core learner lists rescue common words underrepresented in one corpus.
    ranks = (int(row.get(field) or 0) for field in ("bnc", "frq"))
    return (any(0 < rank <= 8000 for rank in ranks) or row.get("oxford") == "1"
            or bool({"zk", "gk", "cet4", "cet6"} & set((row.get("tag") or "").split())))


def _build_lexicon(source, dest):
    with source.open(encoding="utf-8-sig", newline="") as data, closing(sqlite3.connect(dest)) as db:
        db.execute("CREATE TABLE entries (word TEXT PRIMARY KEY, gloss TEXT NOT NULL,"
                   " abbreviation INTEGER NOT NULL, common INTEGER NOT NULL) WITHOUT ROWID")
        variants = []
        for row in csv.DictReader(data):
            word = row["word"].strip()
            gloss = _brief_gloss(row["translation"])
            if not word or not gloss:
                continue
            common = _common_word(row)
            abbreviation = row["translation"].lstrip().startswith("abbr.")
            db.execute("INSERT INTO entries VALUES (?, ?, ?, ?)", (word, gloss, abbreviation, common))
            if not common and not abbreviation:
                # Surface forms such as 'banked' often omit the lemma's ranks.
                lemma = re.search(r"(?:^|/)0:([^/]+)", row.get("exchange") or "")
                if lemma:
                    variants.append((word, lemma[1]))
        db.executemany("UPDATE entries SET common = 1 WHERE word = ?"
                       " AND EXISTS (SELECT 1 FROM entries WHERE word = ? AND common = 1)", variants)
        db.execute("CREATE TABLE source (digest TEXT NOT NULL)")
        db.execute("INSERT INTO source VALUES (?)", (ECDICT_SHA,))
        db.commit()


def _lexicon_ready(path):
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            return (db.execute("SELECT digest FROM source").fetchone() == (ECDICT_SHA,)
                    and db.execute("SELECT word, gloss, abbreviation, common FROM entries LIMIT 1").fetchone() is not None
                    and db.execute("PRAGMA quick_check(1)").fetchone() == ("ok",))
    except sqlite3.Error:
        return False


def install_lexicon(source=None) -> Path:
    if _lexicon_ready(LEXICON):
        return LEXICON
    LEXICON.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=LEXICON.parent) as stage:
        if source is None:
            print("Downloading the English-Chinese dictionary (63 MiB)...", flush=True)
            source = Path(stage) / "ecdict.csv"
            with urllib.request.urlopen(ECDICT_URL, timeout=90) as response, source.open("wb") as output:
                shutil.copyfileobj(response, output)
        with Path(source).open("rb") as data:
            if hashlib.file_digest(data, "sha256").hexdigest() != ECDICT_SHA:
                raise ValueError("ECDICT checksum mismatch.")
        pending = Path(stage) / LEXICON.name
        _build_lexicon(Path(source), pending)
        try:
            os.replace(pending, LEXICON)
        except PermissionError:
            # A concurrent installer may already have published the same index
            # and a reader may have it open on Windows.
            if not _lexicon_ready(LEXICON):
                raise
    return LEXICON


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
    install_lexicon()
    print(f"Model ready at {MODEL}")
