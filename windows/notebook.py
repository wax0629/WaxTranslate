"""Saved vocabulary, lookup counts and a bounded list of recent words."""
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from typing import NamedTuple
import os
import sqlite3
import time

INTERVALS = (1, 3, 7, 14, 30, 60)
RECENT_LIMIT = 6
MASTERED_STREAK = 3


class Dashboard(NamedTuple):
    total: int
    today: int
    saved: int
    due: int
    mastered: int
    recent: list

ENTRIES_SCHEMA = """CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY, word TEXT NOT NULL, context TEXT NOT NULL,
    position INTEGER NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL,
    translation TEXT NOT NULL, due INTEGER NOT NULL, streak INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'en', UNIQUE(word, context, position, language))"""


def prepare_dashboard(db):
    # The singleton is also written by older portable builds sharing this notebook.
    # Archive its count whenever either build replaces the day, including at first upgrade.
    db.execute("""CREATE TABLE IF NOT EXISTS lookup_counter (
        id INTEGER PRIMARY KEY CHECK (id = 1), day TEXT NOT NULL, total INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS prior_lookup_days (
        day TEXT PRIMARY KEY, total INTEGER NOT NULL)""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS archive_lookup_day BEFORE UPDATE OF day ON lookup_counter
        WHEN OLD.day <> NEW.day BEGIN
            INSERT INTO prior_lookup_days(day, total) VALUES(OLD.day, OLD.total)
            ON CONFLICT(day) DO UPDATE SET total=prior_lookup_days.total+excluded.total;
        END""")
    db.execute("""CREATE TABLE IF NOT EXISTS recent_lookups (
        id INTEGER PRIMARY KEY, word TEXT NOT NULL, language TEXT NOT NULL, gloss TEXT NOT NULL, looked_up_at INTEGER,
        UNIQUE(word, language))""")
    db.execute("CREATE INDEX IF NOT EXISTS entries_due ON entries(due)")


def short_gloss(gloss):
    lines = gloss.strip().splitlines()
    return lines[0][:120] if lines else ""


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
            if not db.execute("SELECT 1 FROM pragma_table_info('recent_lookups') WHERE name='looked_up_at'").fetchone():
                db.execute("BEGIN IMMEDIATE")
                prepare_dashboard(db)
                if not db.execute("SELECT 1 FROM pragma_table_info('recent_lookups') WHERE name='looked_up_at'").fetchone():
                    db.execute("ALTER TABLE recent_lookups ADD COLUMN looked_up_at INTEGER")
                db.commit()
            if not db.execute("SELECT 1 FROM pragma_table_info('entries') WHERE name='structure'").fetchone():
                try:
                    db.execute("ALTER TABLE entries ADD COLUMN structure TEXT NOT NULL DEFAULT 'sentence'")
                    db.commit()
                except sqlite3.OperationalError:
                    if not db.execute("SELECT 1 FROM pragma_table_info('entries') WHERE name='structure'").fetchone():
                        raise
            yield db

    def record_lookup(self, now=None, *, word="", language="", gloss=""):
        """Count one completion and keep only the most recent word/meaning pairs."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time() if now is None else now
            day = date.fromtimestamp(now).isoformat()
            row = db.execute("""INSERT INTO lookup_counter(id, day, total) VALUES(1, ?, 1)
                                ON CONFLICT(id) DO UPDATE SET day=excluded.day,
                                    total=CASE WHEN day=excluded.day THEN total+1 ELSE 1 END
                                RETURNING total""", (day,)).fetchone()
            if word:
                # A new rowid moves a repeated word to the front even with identical timestamps.
                db.execute("INSERT OR REPLACE INTO recent_lookups(word, language, gloss, looked_up_at) VALUES(?, ?, ?, ?)",
                           (word, language, short_gloss(gloss), int(now)))
                db.execute("""DELETE FROM recent_lookups WHERE id NOT IN
                              (SELECT id FROM recent_lookups ORDER BY id DESC LIMIT ?)""", (RECENT_LIMIT,))
            prior = db.execute("SELECT total FROM prior_lookup_days WHERE day=?", (day,)).fetchone()
            return row["total"] + (prior["total"] if prior else 0)

    def update_recent_gloss(self, word, language, gloss):
        """A later dictionary response can fill in a visible word without recording a lookup."""
        if not self.path.exists():
            return
        with self.connection() as db:
            db.execute("UPDATE recent_lookups SET gloss=? WHERE word=? AND language=?",
                       (short_gloss(gloss), word, language))

    def activity_snapshot(self, now=None):
        if not self.path.exists():
            return Dashboard(0, 0, 0, 0, 0, [])
        now = time.time() if now is None else now
        day = date.fromtimestamp(now).isoformat()
        with self.connection() as db:
            db.execute("BEGIN")
            total, today = db.execute("""WITH days AS (
                SELECT day, total FROM prior_lookup_days UNION ALL SELECT day, total FROM lookup_counter)
                SELECT COALESCE(sum(total), 0), COALESCE(sum(total) FILTER (WHERE day=?), 0) FROM days""",
                                      (day,)).fetchone()
            saved, due, mastered = db.execute("""SELECT count(*), count(*) FILTER (WHERE due <= ?),
                                                 count(*) FILTER (WHERE streak >= ?) FROM entries""",
                                               (now, MASTERED_STREAK)).fetchone()
            recent = [tuple(row) for row in db.execute(
                "SELECT word, language, gloss, looked_up_at FROM recent_lookups ORDER BY id DESC LIMIT ?", (RECENT_LIMIT,))]
            return Dashboard(total, today, saved, due, mastered, recent)

    def dashboard(self, now=None):
        stats = self.activity_snapshot(now)
        return stats.total, stats.today, stats.saved, stats.due, [row[:3] for row in stats.recent]

    def home_stats(self, now=None):
        """Return today's lookups, saved entries and entries currently due."""
        return self.dashboard(now)[1:4]

    def save(self, passage, result):
        source, gloss, translation = result
        with self.connection() as db:
            db.execute("""INSERT INTO entries(word, context, position, source, gloss, translation, due, language, structure)
                          VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(word, context, position, language) DO UPDATE SET
                          source=excluded.source, gloss=excluded.gloss, translation=excluded.translation, structure=excluded.structure""",
                       (passage.word, passage.text, passage.selection[0], source, gloss, translation,
                        int(time.time()), passage.source_code or "en", getattr(passage,"structure","sentence")))

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
