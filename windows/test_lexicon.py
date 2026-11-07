import csv
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import install_model
import lexicon


class LexiconTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source = root / "test.csv"
        self.index = root / "test-lexicon.sqlite3"
        with self.source.open("w", encoding="utf-8", newline="") as source:
            rows = csv.writer(source)
            rows.writerow(["word", "translation", "bnc", "frq", "tag", "oxford", "exchange"])
            rows.writerows([
                ("bank", r"n. 银行, 堤, 岸\n[医] 库"), ("us", "pron. 我们"),
                ("cli", "abbr. 命令行界面"), ("café", "n. 咖啡馆"), ("reader's", "读者的"),
                ("code", r"[网络] code\n[计] 代码"), ("noise", "[网络] noise"),
                ("wordy", "释义" * 80),
                ("sail", "航行", 50), ("sailed", "航行过", 0, 0, "", "", "0:sail/1:d"),
                ("course", "课程", 0, 8000), ("core", "核心", 0, 0, "gk toefl"),
                ("rare", "罕见的", 8001, 90000, "gre"), ("basic", "基本的", 0, 0, "", 1),
            ])
        self.enterContext(patch.object(install_model, "LEXICON", self.index))
        self.enterContext(patch.object(lexicon, "LEXICON", self.index))
        self.enterContext(patch.object(install_model, "ECDICT_SHA", hashlib.sha256(
            self.source.read_bytes()).hexdigest()))

    def test_gloss_case_and_index(self):
        install_model.install_lexicon(self.source)
        self.assertEqual(lexicon.lookup_entry("Bank"), "银行, 堤, 岸")
        self.assertEqual(lexicon.lookup_entry("Us"), "我们")
        self.assertEqual(lexicon.lookup_entry("US"), "")
        self.assertEqual(lexicon.lookup_entry("CLI"), "命令行界面")
        self.assertEqual(lexicon.lookup_entry("Cli"), "")
        self.assertEqual(lexicon.lookup_entry("café"), "咖啡馆")
        self.assertEqual(lexicon.lookup_entry("reader’s"), "读者的")
        self.assertEqual(lexicon.lookup_entry("code"), "[计] 代码")
        self.assertEqual(lexicon.lookup_entry("noise"), "")
        self.assertLessEqual(len(lexicon.lookup_entry("wordy")), 96)
        for unknown in ("", "x" * 300, "' OR 1=1 --", "UnknownPrivateWord"):
            self.assertEqual(lexicon.lookup_entry(unknown), "")
        with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network request")):
            self.assertEqual(install_model.install_lexicon(), self.index)

    def test_incomplete_or_missing_index(self):
        self.assertEqual(lexicon.lookup_entry("bank"), "")
        self.assertFalse(self.index.exists())
        self.index.write_bytes(b"incomplete")
        self.assertEqual(lexicon.lookup_entry("bank"), "")
        with patch.object(install_model, "ECDICT_SHA", "wrong-digest"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                install_model.install_lexicon(self.source)
        self.assertEqual(self.index.read_bytes(), b"incomplete")
        install_model.install_lexicon(self.source)
        self.assertEqual(lexicon.lookup_entry("bank"), "银行, 堤, 岸")

    def test_portable_uses_bundled_index(self):
        install_model.install_lexicon(self.source)
        bundle = self.index.parent / "bundle #1"
        (bundle / "models").mkdir(parents=True)
        shutil.copy2(self.index, bundle / "models" / self.index.name)
        self.index.write_bytes(b"incomplete")
        with patch.object(lexicon, "__file__", str(bundle / "windows" / "lexicon.py")):
            self.assertEqual(lexicon.lookup_entry("bank"), "银行, 堤, 岸")

    def test_frequency_and_common_inflections(self):
        install_model.install_lexicon(self.source)
        for word in ("sail", "sailed", "Course", "core", "basic"):
            with self.subTest(word=word):
                gloss, common = lexicon.lookup_info(word)
                self.assertTrue(gloss and common)
        self.assertEqual(lexicon.lookup_info("rare"), ("罕见的", False))
        self.assertEqual(lexicon.lookup_info("missing"), ("", False))


if __name__ == "__main__":
    unittest.main()
