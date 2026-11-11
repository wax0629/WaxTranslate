"""Install the pinned offline models and English-Chinese dictionary."""

import argparse
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import closing
import csv
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from http.client import IncompleteRead
import os
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from urllib.error import URLError
import urllib.request
import zipfile


MODEL_DIR = Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "models"


@dataclass(frozen=True)
class ModelPackage:
    name: str
    digest: str
    archive_root: str = ""
    files: tuple = ("model/model.bin", "model/config.json", "model/shared_vocabulary.json",
                    "sentencepiece.model", "README.md", "metadata.json")


LEGACY_FILES = ("model/model.bin", "model/shared_vocabulary.txt", "sentencepiece.model", "README.md", "metadata.json")
MODELS = {
    "zh": ModelPackage("translate-zh_en-1_9", "62e7af5a3a48b530e47b7b3e5c78c2de79073ecd815750d2bf3ab35b4a67da2d"),
    "en": ModelPackage("translate-en_zh-1_9", "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab"),
    "fr": ModelPackage("translate-fr_en-1_9", "3b3052fee6bb1e8e8e632a26a723eb2a2c7710dfe73ba61ffd9b83e85d4f14c1"),
    "de": ModelPackage("translate-de_en-1_3", "becc2b0011f8249fcb89be9ecb75ba0d876b1fab93c28ee6ff0420936897d637"),
    # The compact Spanish SentencePiece release uses CT2's legacy text vocabulary.
    "es": ModelPackage("translate-es_en-1_0", "1b963aa0e0cb6e5ce874f0aa1a1949a19bc4d762e833532239a8834340f6b378",
                       "es_en", LEGACY_FILES),
    "ja": ModelPackage("translate-ja_en-1_1", "623e3477959a815eb0a5ef53e09079ae8f1f9d3bbcd230473baf28c03fb83335",
                       "ja_en", LEGACY_FILES),
    "ko": ModelPackage("translate-ko_en-1_1", "6da8f3db6ca40f42b1875570a1c06856f6e17c7ef62845d85de217ba548c1471",
                       "ko_en", LEGACY_FILES),
    "it": ModelPackage("translate-it_en-1_0", "d2dd23b8b702f612b8127f07c7a0391f5f2a8b93344e6ddc9dd93c81824e85cb",
                       "it_en", LEGACY_FILES),
    "pt": ModelPackage("translate-pt_en-1_9", "ae76df6f650895c16f2b582065014fab496755ca846ecb19fae81d51f332a38e"),
    "ru": ModelPackage("translate-ru_en-1_9", "e9ba8bf722d10a4a4c39f74289d5938fd47eac08dbe4ed0afd22d89445a5c3ac"),
}
DEFAULT_LANGUAGES = ("en", "ja", "ko", "zh")
BUNDLED_MODELS = Path(__file__).resolve().parents[1] / "models"
OCR_REV = "87416418657359cb625c412a48b6e1d6d41c29bd"
OCR_MODELS = {
    "zh": ModelPackage("translate-zh_en-1_9", "62e7af5a3a48b530e47b7b3e5c78c2de79073ecd815750d2bf3ab35b4a67da2d"),
    "de": ("deu", 1525436, "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d"),
    "en": ("eng", 4113088, "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"),
    "es": ("spa", 2294433, "6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464"),
    "fr": ("fra", 1130365, "ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca"),
    "it": ("ita", 2701314, "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827"),
    "ja": ("jpn", 2471260, "1f5de9236d2e85f5fdf4b3c500f2d4926f8d9449f28f5394472d9e8d83b91b4d"),
    "ko": ("kor", 1677415, "6b85e11d9bbf07863b97b3523b1b112844c43e713df8b66418a081fd1060b3b2"),
    "pt": ("por", 1982756, "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"),
    "ru": ("rus", 3861738, "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225"),
}


MODEL_MANIFEST = "wax-integrity.json"


def file_identity(path):
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


@lru_cache(maxsize=128)
def checked_digest(path, size, modified, changed, inode):
    # The file identity invalidates this cache even for same-size overwrites.
    # Do not rehash hundreds of MB on every lookup/settings refresh.
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@lru_cache(maxsize=32)
def legacy_model_valid(directory, identities):
    """Old portable packages lack manifests; validate them with the real readers."""
    try:
        import ctranslate2
        import sentencepiece
        root = Path(directory)
        sentencepiece.SentencePieceProcessor(model_proto=(root / "sentencepiece.model").read_bytes())
        ctranslate2.Translator(str(root / "model"), device="cpu", compute_type="int8",
                              inter_threads=1, intra_threads=1)
        return True
    except (ImportError, OSError, RuntimeError, ValueError):
        return False


def write_model_manifest(directory, package):
    contents = {name: checked_digest(*file_identity(directory / name)) for name in package.files}
    (directory / MODEL_MANIFEST).write_text(json.dumps({"version": 1, "archive": package.digest,
                                                       "files": contents}), encoding="utf-8")


def complete_model(directory, package):
    try:
        identities = tuple(file_identity(directory / name) for name in package.files)
        if not all(item[1] for item in identities):
            return False
        manifest_path = directory / MODEL_MANIFEST
        if not manifest_path.exists():
            return legacy_model_valid(str(directory), identities)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return (manifest.get("version") == 1 and manifest.get("archive") == package.digest
                and isinstance(manifest.get("files"), dict) and set(manifest["files"]) == set(package.files)
                and all(checked_digest(*identity) == manifest["files"][name]
                        for name, identity in zip(package.files, identities)))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def translation_dir(code):
    package = MODELS[code]
    return next((base / package.name for base in (MODEL_DIR, BUNDLED_MODELS)
                 if complete_model(base / package.name, package)), None)


def ocr_file(code):
    if code == "zh": return None
    lang, size, digest = OCR_MODELS[code]
    for base in (MODEL_DIR, BUNDLED_MODELS):
        path = base / "tessdata" / f"{lang}.traineddata"
        try:
            identity = file_identity(path)
            if identity[1] == size and checked_digest(*identity) == digest:
                return path
        except OSError:
            pass
    return None


def language_ready(code):
    return (code == "zh" or ocr_file(code) is not None) and translation_dir(code) is not None


POS_PACKAGE = "averaged_perceptron_tagger_eng"
POS_ARCHIVE = MODEL_DIR / f"{POS_PACKAGE}.zip"
POS_SHA = "6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b"
POS_URL = ("https://raw.githubusercontent.com/nltk/nltk_data/"
           f"304a3c5432dd2fe08ae8b436dc6eec54c3593445/packages/taggers/{POS_ARCHIVE.name}")
ECDICT_REV = "39cfb9672c0906b63569e0453c2e6abfb9ab182a"
ECDICT_URL = f"https://raw.githubusercontent.com/skywind3000/ECDICT/{ECDICT_REV}/ecdict.csv"
ECDICT_SHA = "d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc"
LEXICON = MODEL_DIR / f"ecdict-{ECDICT_REV[:8]}-v3.sqlite3"

_LINES = re.compile(r"\\r\\n|\\n|\r?\n")
_POS = re.compile(r"^(a|adj|adv|abbr|art|aux|conj|det|int|interj|n|num|p|pl|prep|pron|v|vi|vt)\.\s*", re.I)
_LABEL = re.compile(r"\[[^\]]{1,24}\]")
_CHINESE = re.compile(r"[\u3400-\u9fff]")


def _first_sense(translation):
    for line in _LINES.split(translation):
        line = line.strip()
        pos = _POS.match(line)
        line = line[pos.end():].strip() if pos else line
        # A label such as "[网络]" alone does not make an echoed headword a gloss.
        if not _CHINESE.search(_LABEL.sub("", line)):
            continue
        if len(line) > 96:
            separators = list(re.finditer(r"[;,，；。]", line[:96]))
            end = separators[-1].start() if separators and separators[-1].start() >= 12 else 95
            line = line[:end].rstrip() + "…"
        return line, pos[1].lower() if pos else ""
    return "", ""


def _common_word(row):
    # BNC and contemporary rank 1 denote the most frequent word; 0 means
    # unranked. Core learner lists rescue common words underrepresented in one corpus.
    ranks = (int(row.get(field) or 0) for field in ("bnc", "frq"))
    return (any(0 < rank <= 8000 for rank in ranks) or row.get("oxford") == "1"
            or bool({"zk", "gk", "cet4", "cet6"} & set((row.get("tag") or "").split())))


def _build_lexicon(source, dest):
    with source.open(encoding="utf-8-sig", newline="") as data, closing(sqlite3.connect(dest)) as db:
        db.execute("CREATE TABLE entries (word TEXT PRIMARY KEY, gloss TEXT NOT NULL,"
                   " abbreviation INTEGER NOT NULL, common INTEGER NOT NULL, phonetic TEXT, pos TEXT) WITHOUT ROWID")
        variants = []
        for row in csv.DictReader(data):
            word = row["word"].strip()
            gloss, pos = _first_sense(row["translation"])
            if not word or not gloss:
                continue
            common = _common_word(row)
            abbreviation = row["translation"].lstrip().startswith("abbr.")
            db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)",
                       (word, gloss, abbreviation, common, (row.get("phonetic") or "").strip(), pos))
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
                    and db.execute("SELECT word, gloss, abbreviation, common, phonetic, pos FROM entries LIMIT 1").fetchone() is not None
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


def download_resource(url, destination, cancel):
    with urllib.request.urlopen(url, timeout=30) as response, destination.open("wb") as output:
        while True:
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            chunk = response.read(512 * 1024)
            if not chunk:
                break
            output.write(chunk)


def install_model(package, archive=None, cancel=None, *, repair=False):
    model = MODEL_DIR / package.name
    if not repair and complete_model(model, package):
        return
    if cancel is not None and cancel.is_set():
        raise CancelledError()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL_DIR) as stage:
        if archive is None:
            print(f"Downloading {package.name}...", flush=True)
            archive = Path(stage) / "download.zip"
            mirrors = ("https://argos-net.com/v1", "https://data.argosopentech.com/argospm/v1")
            for base in mirrors:
                url = f"{base}/{package.name}.argosmodel"
                try:
                    download_resource(url, archive, cancel)
                    break
                except (URLError, TimeoutError, IncompleteRead) as error:
                    if base == mirrors[-1]:
                        raise
                    print(f"Download failed ({error}); trying the Argos model archive.", flush=True)
        with open(archive, "rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != package.digest:
                raise ValueError("Model checksum mismatch. Please download the package again.")
        extracted = Path(stage) / package.name
        with zipfile.ZipFile(archive) as bundle:
            for name in package.files:
                if cancel is not None and cancel.is_set():
                    raise CancelledError()
                path = extracted / name
                path.parent.mkdir(exist_ok=True, parents=True)
                with bundle.open(f"{package.archive_root or package.name}/{name}") as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output)
        write_model_manifest(extracted, package)
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        # Publish only the entire verified model. A failed replacement must
        # restore the previous directory, including its nonempty files.
        previous = Path(stage) / "previous"
        if model.exists():
            model.rename(previous)
        try:
            extracted.rename(model)
        except OSError:
            if previous.exists():
                previous.rename(model)
            raise


def install_language(code, archive=None, *, cancel=None, repair=False):
    if cancel is not None and cancel.is_set():
        raise CancelledError()
    if code != "zh" and (repair or not ocr_file(code)):
        lang, _, digest = OCR_MODELS[code]
        dest = MODEL_DIR / "tessdata" / f"{lang}.traineddata"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent) as stage:
            pending = Path(stage) / dest.name
            url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{OCR_REV}/{dest.name}"
            download_resource(url, pending, cancel)
            with pending.open("rb") as data:
                if hashlib.file_digest(data, "sha256").hexdigest() != digest:
                    raise ValueError("OCR model checksum mismatch.")
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            os.replace(pending, dest)
    if repair or not translation_dir(code):
        install_model(MODELS[code], archive, cancel, repair=repair)


def install(archive=None, codes=DEFAULT_LANGUAGES):
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(install_language, code, archive if code == "en" else None) for code in codes]
        for job in jobs:
            job.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="use an already downloaded English-Chinese .argosmodel")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--language", choices=MODELS, help="install one language's translation and OCR resources")
    group.add_argument("--all-languages", action="store_true", help="install all supported languages for development")
    args = parser.parse_args()
    if args.language:
        install_language(args.language)
    else:
        install(args.archive, MODELS if args.all_languages else DEFAULT_LANGUAGES)
        if not args.all_languages:
            install_word_tags()
            install_lexicon()
    print("Models ready.", flush=True)
