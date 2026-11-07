import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter
from winrt.windows.globalization import Language
from winrt.windows.media.ocr import OcrEngine

from app import analyze
from languages import NAMES, OCR_TAGS, UnsupportedLanguage, detect_source
from notebook import Notebook
from reader import Passage, recognize, sentence_at
from translation import translate_text


SAMPLES = {
    "fr": ("Le chat dort dans la maison de ma sœur.", "chat"),
    "de": ("Die Katze schläft auf dem Sofa im Wohnzimmer.", "Katze"),
    "es": ("El gato duerme en la casa de mi hermana.", "gato"),
}


class LanguageTests(unittest.TestCase):
    def test_automatic_paragraphs_and_word_alignment(self):
        paragraphs = "\n\n".join(sentence for sentence, _ in SAMPLES.values())
        result = translate_text(paragraphs, Event()).split("\n\n")
        self.assertEqual(len(result), 3)
        for (code, (source, word)), chinese in zip(SAMPLES.items(), result):
            with self.subTest(code=code):
                self.assertIn("猫", chinese)
                self.assertEqual(detect_source(source), code)
                start = source.index(word)
                read, (origin, gloss, sentence), _, language, pos = analyze(
                    None, None, sentence_at(source, start, start + len(word)))
                self.assertEqual((read.word, language, pos), (word, NAMES[code], ""))
                self.assertIn(origin, ("句中释义", "单词参考"))
                self.assertIn("猫", gloss)
                self.assertEqual(chinese, sentence)
        with self.assertRaises(UnsupportedLanguage):
            translate_text("Il metodo proposto permette di misurare la temperatura in questo ambiente.", Event())

    def test_short_words_and_saved_languages(self):
        for code, word in (("fr", "pain"), ("de", "Brot"), ("es", "pan")):
            with self.subTest(code=code):
                self.assertFalse(detect_source(word))
                self.assertIn("面包", translate_text(word, Event(), code))
        with TemporaryDirectory() as tmp:
            book = Notebook(Path(tmp) / "words.sqlite3")
            for code in ("fr", "en"):
                passage = Passage("pain", (0, 4))
                read, result, _, _, _ = analyze(None, None, passage, code)
                book.save(read, result)
            rows = {row["language"]: row for row in book.entries()}
            self.assertIn("面包", rows["fr"]["gloss"])
            self.assertNotEqual(rows["en"]["gloss"], rows["fr"]["gloss"])

    def test_repeated_accented_word_uses_its_byte_range_in_first_model(self):
        source = "Près du café, le deuxième café est fermé."
        start = source.rindex("café")
        passage = sentence_at(source, start, start + 4)
        from translation import aligned_selection
        with patch("translation.aligned_selection", wraps=aligned_selection) as align:
            analyze(None, None, passage, "fr")
        _, indices, _, tokenizer = align.call_args_list[0].args
        pieces = tokenizer.encode(source, return_type="proto").pieces
        selected_start = len(source[:start].encode())
        self.assertEqual(indices, [i for i, p in enumerate(pieces)
                                   if p.begin < selected_start + len("café".encode()) and p.end > selected_start])

    def test_screen_word_and_region_with_installed_ocr(self):
        font = QFont("Segoe UI")
        font.setPixelSize(26)
        metrics = QFontMetrics(font)
        for code, (text, word) in SAMPLES.items():
            with self.subTest(code=code):
                image = QImage(metrics.horizontalAdvance(text) + 40, 90, QImage.Format_RGB32)
                image.fill(0xffffffff)
                painter = QPainter(image)
                painter.setFont(font)
                painter.drawText(10, 55, text)
                painter.end()
                hit = QPointF(10 + metrics.horizontalAdvance(text[:text.index(word)]) +
                              metrics.horizontalAdvance(word) / 2, 55 - metrics.capHeight() / 2)
                installed = OcrEngine.try_create_from_language(Language(OCR_TAGS[code]))
                if installed is None:
                    with self.assertRaisesRegex(ValueError, NAMES[code] + "安装文字识别"):
                        asyncio.run(recognize(image, hit, code))
                for setting in (("", code) if installed else ("",)):
                    read, result, _, language, _ = analyze(image, hit, None, setting)
                    self.assertEqual((read.word.casefold(), language), (word.casefold(), NAMES[code]))
                    self.assertIn("猫", result[1])
                    _, region, _, _, _ = analyze(image, None, None, setting)
                    self.assertIn("猫", region[1])
