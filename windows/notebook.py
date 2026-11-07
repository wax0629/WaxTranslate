"""User-selected vocabulary and the current local day's aggregate lookup count."""
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
import os
import sqlite3
import time

INTERVALS = (1, 3, 7, 14, 30, 60)

ENTRIES_SCHEMA = """CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY, word TEXT NOT NULL, context TEXT NOT NULL,
    position INTEGER NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL,
    translation TEXT NOT NULL, due INTEGER NOT NULL, streak INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'en', UNIQUE(word, context, position, language))"""


class Notebook:
    def __init__(self, path=None):
        self.path = path or Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "notebook.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute(ENTRIES_SCHEMA)
            if not db.execute("SELECT 1 FROM pragma_table_info('entries') WHERE name='language'").fetchone():
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM pragma_table_info('entries') WHERE name='language'").fetchone():
                    fields = "id, word, context, position, source, gloss, translation, due, streak"
                    db.execute("ALTER TABLE entries RENAME TO entries_english")
                    db.execute(ENTRIES_SCHEMA)
                    db.execute(f"INSERT INTO entries({fields}) SELECT {fields} FROM entries_english")
                    db.execute("DROP TABLE entries_english")
                    db.execute("CREATE INDEX entries_due ON entries(due)")
                db.commit()
            yield db

    def record_lookup(self, now=None):
        """Count one completed word lookup without storing its text or occurrence."""
        with self.connection() as db:
            # Assign the local day after preceding writers, including at midnight.
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS lookup_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1), day TEXT NOT NULL, total INTEGER NOT NULL)""")
            # Subsequent dashboard refreshes can count the schedule directly,
            # without scanning saved sentences or their translations.
            db.execute("CREATE INDEX IF NOT EXISTS entries_due ON entries(due)")
            day = date.fromtimestamp(time.time() if now is None else now).isoformat()
            row = db.execute("""INSERT INTO lookup_counter(id, day, total) VALUES(1, ?, 1)
                                ON CONFLICT(id) DO UPDATE SET day=excluded.day,
                                    total=CASE WHEN day=excluded.day THEN total+1 ELSE 1 END
                                RETURNING total""", (day,)).fetchone()
            return row["total"]

    def home_stats(self, now=None):
        """Return today's lookups, saved entries and entries currently due."""
        if not self.path.exists():
            return 0, 0, 0
        now = time.time() if now is None else now
        day = date.fromtimestamp(now).isoformat()
        with self.connection() as db:
            # Read one snapshot if a save or a new lookup happens concurrently.
            db.execute("BEGIN")
            saved, due = db.execute("""SELECT (SELECT count(*) FROM entries),
                                              (SELECT count(*) FROM entries WHERE due <= ?)""", (now,)).fetchone()
            # Pre-dashboard notebooks may have vocabulary but no counter.
            exists = db.execute("""SELECT 1 FROM sqlite_master
                                   WHERE type='table' AND name='lookup_counter'""").fetchone()
            if not exists:
                return 0, saved, due
            row = db.execute("SELECT total FROM lookup_counter WHERE id=1 AND day=?", (day,)).fetchone()
            return (row["total"] if row else 0), saved, due

    def save(self, passage, result):
        source, gloss, translation = result
        with self.connection() as db:
            db.execute("""INSERT INTO entries(word, context, position, source, gloss, translation, due, language)
                          VALUES(?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(word, context, position, language) DO UPDATE SET
                          source=excluded.source, gloss=excluded.gloss, translation=excluded.translation""",
                       (passage.word, passage.text, passage.selection[0], source, gloss, translation,
                        int(time.time()), passage.source_code or "en"))

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
