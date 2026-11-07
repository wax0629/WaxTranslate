"""Look up a brief Chinese dictionary reference in the bundled ECDICT index."""
from contextlib import closing
from pathlib import Path
import sqlite3

from install_model import LEXICON


def lookup_info(word: str) -> tuple[str, bool]:
    """Keep acronym and ordinary-word spellings distinct when resolving case."""
    word = word.strip().replace("’", "'")
    if not word or len(word) > 256:
        return "", False
    bundled = Path(__file__).resolve().parents[1] / "models" / LEXICON.name
    path = bundled if bundled.is_file() else LEXICON
    try:
        # Separate short-lived read-only handles work across the lookup pool and
        # leave no Windows file lock between queries or during a model upgrade.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
            query = "SELECT gloss, common FROM entries WHERE word = ?"
            entry = database.execute(query, (word,)).fetchone()
            if entry:
                return entry[0], bool(entry[1])
            if word.istitle() and not word.isupper():
                entry = database.execute(
                    query + " AND abbreviation = 0", (word.lower(),)
                ).fetchone()
            elif word.isupper():
                # ECDICT prints some initialisms in lowercase ('cli'). Only an
                # explicitly abbreviated headword can supply the uppercase form.
                entry = database.execute(
                    query + " AND abbreviation = 1", (word.lower(),)
                ).fetchone()
    except sqlite3.Error:
        return "", False
    return (entry[0], bool(entry[1])) if entry else ("", False)


def lookup_entry(word: str) -> str:
    return lookup_info(word)[0]
