from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from notebook import Notebook


class HomeStatsTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.book = Notebook(directory / "profile" / "notebook.sqlite3")

    def test_lookup_counter_persists_and_rolls_at_local_midnight(self):
        before = datetime(2030, 8, 5, 23, 59, 59).timestamp()
        midnight = datetime(2030, 8, 6).timestamp()
        self.assertEqual(self.book.home_stats(before), (0, 0, 0))
        self.assertFalse(self.book.path.exists())
        self.assertEqual(self.book.record_lookup(before), 1)
        reopened = Notebook(self.book.path)
        self.assertEqual(reopened.record_lookup(before), 2)
        self.assertEqual(reopened.home_stats(before), (2, 0, 0))
        self.assertEqual(reopened.home_stats(midnight), (0, 0, 0))
        with reopened.connection() as db:
            self.assertEqual([tuple(r) for r in db.execute("SELECT * FROM lookup_counter")],
                             [(1, "2030-08-05", 2)])
        self.assertEqual(reopened.record_lookup(midnight), 1)
        with reopened.connection() as db:
            self.assertEqual([tuple(r) for r in db.execute("SELECT * FROM lookup_counter")],
                             [(1, "2030-08-06", 1)])

    def test_concurrent_completed_queries(self):
        stamp = datetime(2030, 8, 5, 12).timestamp()
        with ThreadPoolExecutor(max_workers=4) as pool:
            counts = list(pool.map(self.book.record_lookup, [stamp] * 32))
        self.assertEqual(sorted(counts), list(range(1, 33)))
        self.assertEqual(self.book.home_stats(stamp), (32, 0, 0))

    def test_old_notebook_and_review_schedule(self):
        # Only the entries table exists in a notebook from the previous release.
        self.book.path.parent.mkdir(parents=True)
        db = sqlite3.connect(self.book.path)
        with db:
            db.execute("""CREATE TABLE entries (
                id INTEGER PRIMARY KEY, word TEXT NOT NULL, context TEXT NOT NULL,
                position INTEGER NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL,
                translation TEXT NOT NULL, due INTEGER NOT NULL, streak INTEGER NOT NULL DEFAULT 0,
                UNIQUE(word, context, position))""")
            db.execute("""INSERT INTO entries VALUES (7, 'bank', 'the bank', 4, '词典', '银行', '', 100, 2)""")
        db.close()
        self.assertEqual(self.book.home_stats(99), (0, 1, 0))
        self.assertEqual(self.book.home_stats(100), (0, 1, 1))
        self.assertEqual(self.book.entries()[0]["streak"], 2)
        self.book.record_lookup(100)
        second = SimpleNamespace(word="bank", text="river bank", selection=(6, 10))
        with patch("notebook.time.time", return_value=100):
            self.book.save(second, ("词典", "岸", ""))
            self.book.save(second, ("词典", "河岸", ""))
        self.assertEqual(self.book.home_stats(100), (1, 2, 2))
        self.book.review(7, False, now=100)
        self.assertEqual(self.book.home_stats(699), (1, 2, 1))
        self.assertEqual(self.book.home_stats(700), (1, 2, 2))
        self.book.remove(7)
        self.assertEqual(self.book.home_stats(700), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
