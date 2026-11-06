"""Persistent user-selected vocabulary. Due times are Unix timestamps."""
from contextlib import closing, contextmanager
from pathlib import Path
import os
import sqlite3
import time

INTERVALS = (1, 3, 7, 14, 30, 60)


class Notebook:
    def __init__(self, path=None):
        self.path = path or Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "notebook.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("""CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY, word TEXT NOT NULL, context TEXT NOT NULL,
                position INTEGER NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL,
                translation TEXT NOT NULL, due INTEGER NOT NULL, streak INTEGER NOT NULL DEFAULT 0,
                UNIQUE(word, context, position))""")
            yield db

    def save(self, passage, result):
        source, gloss, translation = result
        with self.connection() as db:
            db.execute("""INSERT INTO entries(word, context, position, source, gloss, translation, due)
                          VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(word, context, position) DO NOTHING""",
                       (passage.word, passage.text, passage.selection[0], source, gloss, translation, int(time.time())))

    def entries(self):
        with self.connection() as db:
            return db.execute("SELECT * FROM entries ORDER BY due, id DESC").fetchall()

    def review(self, entry_id, remembered, now=None):
        now = int(time.time()) if now is None else now
        with self.connection() as db:
            row = db.execute("SELECT streak FROM entries WHERE id=?", (entry_id,)).fetchone()
            if row is None:
                return
            streak = min(row["streak"] + 1, len(INTERVALS)) if remembered else 0
            delay = INTERVALS[streak - 1] * 86400 if streak else 600
            db.execute("UPDATE entries SET due=?, streak=? WHERE id=?", (now + delay, streak, entry_id))

    def remove(self, entry_id):
        with self.connection() as db:
            db.execute("DELETE FROM entries WHERE id=?", (entry_id,))
