"""Regression matrix for automatic OCR routing. Images and recognition stay local."""
import asyncio
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from app import analyze
import reader
from languages import detect_source
from reader import Passage, read_from_pack, recognize


# One-letter labels through long words, plus identifiers, punctuation, repeated occurrences and a sentence.
# Text size and foreground/background contrast vary independently of the selected word length.
LABELS = (
    ("A", "A", 20), ("Go", "Go", 16), ("Up", "Up", 17), ("it", "it", 18),
    ("OK", "OK", 24), ("VR", "VR", 18), ("the", "the", 14), ("OCR", "OCR", 16),
    ("B2B", "B2B", 17), ("C++", "C++", 20), ("warehouse", "warehouse", 14),
    ("extraordinarily", "extraordinarily", 17), ("electromagnetism", "electromagnetism", 17),
    ("conjoined (interlude)", "interlude", 15), ("Midnight (Live 2024)", "Midnight", 15),
    ("Echo Echo", "Echo", 16), ("re-entry", "re-entry", 20), ("don't stop", "don't", 19),
    ("Track 07 - Voyager", "Voyager", 14), ("The Sound of Silence", "Silence", 17),
    ("A quiet river runs through the valley.", "valley", 16),
    ("antidisestablishmentarianism", "antidisestablishmentarianism", 20),
    ("internationalization", "internationalization", 19),
)
COLORS = (("#333333", "#ffffff"), ("#e2e2e2", "#24262a"), ("#888888", "#dbdbdb"))


def render_label(text, target, pixels, colors):
    font = QFont("Segoe UI")
    font.setPixelSize(pixels)
    metrics = QFontMetrics(font)
    image = QImage(metrics.horizontalAdvance(text) + 18, metrics.height() + 12, QImage.Format_RGB32)
    ink, paper = colors
    image.fill(QColor(paper))
    baseline = 6 + metrics.ascent()
    with QPainter(image) as painter:
        painter.setFont(font)
        painter.setPen(QColor(ink))
        painter.drawText(9, baseline, text)
    start = text.rindex(target)
    x = 9 + metrics.horizontalAdvance(text[:start]) + metrics.horizontalAdvance(target) / 2
    return image, QPointF(x, baseline - metrics.capHeight() / 2)


def packs_only():
    # Disable the system recognizers only. Every installed OCR pack still reads real pixels.
    return patch("reader.OcrEngine", SimpleNamespace(available_recognizer_languages=[],
                                                    try_create_from_language=lambda lang: None))


@contextmanager
def report_reads_on_failure(image, point):
    """Make differences between Windows OCR configurations visible in the CI failure."""
    try:
        yield
    except (AssertionError, ValueError) as error:
        for code in ("en", "ja", "ko", "ru"):
            try:
                native = reader.OcrEngine.try_create_from_language(reader.Language(reader.OCR_TAGS[code]))
                if native:
                    p = asyncio.run(reader.read_passage(native, image, point))
                    error.add_note(f"Windows {code}: {p!r}, hit line {p.ocr_line!r}")
            except (OSError, ValueError) as reason:
                error.add_note(f"Windows {code}: {reason}")
            try:
                p, confidence = read_from_pack(image, point, code)
                error.add_note(f"Pack {code}: {p!r}, confidence {confidence:.1f}")
            except (OSError, ValueError) as reason:
                error.add_note(f"Pack {code}: {reason}")
        raise


class RoutingTests(unittest.TestCase):
    def check_latin_labels(self, offline):
        with packs_only() if offline else nullcontext():
            for i, (text, target, size) in enumerate(LABELS):
                image, hit = render_label(text, target, size, COLORS[i % len(COLORS)])
                for point in (hit, None):
                    with self.subTest(text=text, hover=point is not None, offline=offline), report_reads_on_failure(image, point):
                        result = asyncio.run(recognize(image, point))
                        self.assertEqual(result.text.casefold(), text.casefold())
                        self.assertIn(result.source_code, ("", "en"))
                        if point is not None:
                            start = text.rindex(target)
                            self.assertEqual(result.selection, (start, start + len(target)))
                            self.assertEqual(result.word.casefold(), target.casefold())

    def test_latin_labels_system_and_pack_fallback(self):
        self.check_latin_labels(False)

    def test_latin_labels_offline_packs_only(self):
        self.check_latin_labels(True)

    def test_ambiguous_glyphs_and_non_text_do_not_invent_foreign_words(self):
        for offline in (False, True):
            with packs_only() if offline else nullcontext():
                for text, allowed in (("I", {"i", "l", "|"}), ("AI", {"ai", "al"}),
                                      ("---", {"---"}), ("12345", {"12345"}), ("", {""})):
                    image, hit = render_label(text, text, 16, COLORS[0])
                    for point in (hit, None):
                        with self.subTest(text=text, offline=offline, hover=point is not None):
                            try:
                                result = asyncio.run(recognize(image, point))
                            except ValueError:
                                continue  # Indistinguishable ink may be rejected.
                            self.assertIn(result.source_code, ("", "en"))
                            self.assertIn((result.word if point is not None else result.text).casefold(), allowed)

    def test_short_non_latin_titles(self):
        # Fixed glyph pixels work on Windows installations without CJK display fonts.
        image = QImage(str(Path(__file__).parent / "testdata/ocr-short-labels.png"))
        self.assertFalse(image.isNull())
        samples = (("봄", "ko"), ("하루", "ko"), ("안녕", "ko"), ("봄날 2024", "ko"),
                   ("ねこ", "ja"), ("あした", "ja"), ("そして", "ja"), ("Привет", "ru"), ("дом", "ru"))
        for i, (text, code) in enumerate(samples):
            line = image.copy(0, 34 * i, image.width(), 34)
            for point in (QPointF(19, 18), None):
                with self.subTest(text=text, hover=point is not None), report_reads_on_failure(line, point):
                    result = asyncio.run(recognize(line, point))
                    self.assertEqual((result.source_code, result.text.casefold()), (code, text.casefold()))
                    if point is not None:
                        self.assertTrue(result.word and text.startswith(result.word))

    def test_latin_recognition_reaches_chinese_translation(self):
        for source, target, expected in (("warehouse", "warehouse", "仓库"),
                                         ("conjoined (interlude)", "interlude", "插曲")):
            image, hit = render_label(source, target, 19, COLORS[0])
            for point in (hit, None):
                with self.subTest(source=source, hover=point is not None):
                    read, (_, gloss, _), _, _, _ = analyze(image, point, None)
                    self.assertEqual(read.text.casefold(), source)
                    self.assertIn(read.source_code, ("", "en"))
                    self.assertRegex(gloss, r"[\u3400-\u9fff]")
                    if point is not None:
                        self.assertIn(expected, gloss)

    def test_resampled_dark_title_keeps_second_occurrence(self):
        image, hit = render_label("Echo (Echo 2024)", "Echo", 19, COLORS[1])
        for factor in (0.8, 1.5, 2):
            scaled = image.scaled(round(image.width() * factor), round(image.height() * factor),
                                  Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            point = QPointF(hit.x() * scaled.width() / image.width(), hit.y() * scaled.height() / image.height())
            with self.subTest(scale=factor):
                result = asyncio.run(recognize(scaled, point))
                self.assertEqual((result.word.casefold(), result.selection), ("echo", (6, 10)))
                self.assertIn(result.source_code, ("", "en"))

    def test_antialiased_low_contrast_labels(self):
        for target in ("Go", "interlude", "warehouse"):
            image, hit = render_label(target, target, 17, ("#777777", "#bbbbbb"))
            small = image.scaled(round(image.width() * 0.75), round(image.height() * 0.75),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            blurred = small.scaled(image.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            for point in (hit, None):
                with self.subTest(target=target, hover=point is not None), report_reads_on_failure(blurred, point):
                    result = asyncio.run(recognize(blurred, point))
                    self.assertEqual(result.text.casefold(), target.casefold())
                    self.assertIn(result.source_code, ("", "en"))

    def test_pointer_in_multilingual_track_list(self):
        sheet = QImage(str(Path(__file__).parent / "testdata/ocr-short-labels.png"))
        for hit, word, allowed in ((QPointF(41, 324), "Midnight", ("en", "")),
                                   (QPointF(22, 289), "дом", ("ru",)), (QPointF(21, 52), "하루", ("ko",))):
            for offline in (False, True):
                with (self.subTest(word=word, offline=offline), packs_only() if offline else nullcontext(),
                      report_reads_on_failure(sheet, hit)):
                    result = asyncio.run(recognize(sheet, hit))
                    self.assertEqual(result.word.casefold(), word.casefold())
                    self.assertIn(result.source_code, allowed)
        # A pointer in empty space to the right must not select a neighbouring title.
        with self.assertRaises(ValueError):
            asyncio.run(recognize(sheet, QPointF(210, 289)))

    def test_pinned_latin_language_overrides_short_word_ambiguity(self):
        for code, word in (("fr", "pain"), ("de", "Brot"), ("es", "pan")):
            image, hit = render_label(word, word, 22, COLORS[0])
            for point in (hit, None):
                with self.subTest(code=code, hover=point is not None):
                    read, (_, gloss, _), _, _, _ = analyze(image, point, None, code)
                    self.assertEqual((read.text.casefold(), read.source_code), (word.casefold(), code))
                    self.assertIn("面包", gloss)

    def test_mixed_script_reread_preserves_the_actual_hit(self):
        engines = SimpleNamespace(available_recognizer_languages=[SimpleNamespace(language_tag=tag)
                                  for tag in ("en-US", "ko-KR")], try_create_from_language=lambda lang: lang.language_tag)
        original = Passage("Live 오늘의 노래", (0, 4))
        for korean, expected_text, code in ((Passage("라이브 오늘의 노래", (0, 3)), "Live", ""),
                                            (Passage("Live 오늘의 노래", (0, 4)), "Live 오늘의 노래", "ko")):
            with (self.subTest(reread=korean.word), patch("reader.OcrEngine", engines),
                  patch("reader.read_passage", side_effect=[original, korean]),
                  patch("reader.read_from_pack", return_value=(Passage("Live", (0, 4)), 97))):
                result = asyncio.run(recognize(object(), QPointF(20, 10)))
                self.assertEqual((result.word, result.text, result.source_code), ("Live", expected_text, code))

    def test_noise_is_rejected_even_when_korean_is_the_first_engine(self):
        engines = SimpleNamespace(available_recognizer_languages=[SimpleNamespace(language_tag="ko-KR")],
                                  try_create_from_language=lambda lang: lang.language_tag)
        noise = Passage("00미이060 (10160ㅁ406)", (2, 4))
        with (patch("reader.OcrEngine", engines), patch("reader.ocr_file", return_value=None),
              patch("reader.read_passage", return_value=noise)):
            for hit in (None, QPointF(20, 10)):
                with self.assertRaisesRegex(ValueError, "未识别"):
                    asyncio.run(recognize(object(), hit))

    def test_missing_english_pack_and_native_engine_failure(self):
        tags = [SimpleNamespace(language_tag=t) for t in ("en-US", "ko-KR")]
        engines = SimpleNamespace(available_recognizer_languages=tags,
                                  try_create_from_language=lambda lang: lang.language_tag)
        english = Passage("Go", (0, 2))
        with (patch("reader.OcrEngine", engines), patch("reader.ocr_file", side_effect=lambda c: c == "ja"),
              patch("reader.read_passage", side_effect=[english, Passage("고", (0, 1))]),
              patch("reader.read_from_pack", return_value=(Passage("Go", (0, 2)), 90)) as pack):
            self.assertIs(asyncio.run(recognize(object(), QPointF(5, 12))), english)
            self.assertEqual(pack.call_args.args[-1], "ja")
        with (patch("reader.OcrEngine", engines), patch("reader.read_passage", side_effect=OSError("native OCR failed")),
              patch("reader.ocr_file", return_value=True), patch("reader.read_from_pack", return_value=(english, 99))):
            self.assertEqual(asyncio.run(recognize(object(), QPointF(5, 12))).word, "Go")

    def test_detached_kana_stroke_needs_a_second_read_of_the_pixels(self):
        native = Passage("ーそして", (0, 4))
        for second in ("ーそして", "そして"):
            packed = Passage(second, (0, len(second)), source_code="ja")
            with (self.subTest(second=second), patch("reader.OcrEngine.try_create_from_language", return_value="ja"),
                  patch("reader.read_passage", return_value=native), patch("reader.ocr_file", return_value=True),
                  patch("reader.read_from_pack", return_value=(packed, 94))):
                result = asyncio.run(recognize(object(), QPointF(19, 18), "ja"))
                self.assertEqual((result.text, result.word), (second, second))

    def test_conflicting_latin_read_on_a_cyrillic_row(self):
        tags = [SimpleNamespace(language_tag=t) for t in ("en-US", "ja-JP", "ru-RU")]
        engines = SimpleNamespace(available_recognizer_languages=tags,
                                  try_create_from_language=lambda lang: lang.language_tag)
        reads = {"en-US": Passage("npner AOM Midnight (Live)", (6, 9), ocr_line="AOM"),
                 "ja-JP": Passage("AOM", (0, 3)), "ru-RU": Passage("дом", (0, 3))}
        with (patch("reader.OcrEngine", engines), patch("reader.ocr_file", return_value=True),
              patch("reader.read_passage", side_effect=lambda engine, *_: reads[engine]),
              patch("reader.read_from_pack", return_value=(Passage("JOM", (0, 3)), 49))):
            result = asyncio.run(recognize(object(), QPointF(22, 289)))
            self.assertEqual((result.word, result.source_code), ("дом", "ru"))

    def test_statistical_language_predictions_must_match_the_written_script(self):
        for code in ("ja", "ko", "ru"):
            matches = [(code, code, 99, 100)]
            for reliable in (True, False):
                with (self.subTest(candidate=code, reliable=reliable),
                      patch("languages.pycld2.detect", return_value=(reliable, 30, matches)),
                      patch("languages._sentence_identifier") as identifier):
                    identifier.return_value.classify.return_value = code, 0.99
                    self.assertEqual(detect_source("Light in the dark"), "")

    def test_weak_hover_hit_does_not_inherit_its_neighbors_confidence(self):
        frame = QImage(250, 60, QImage.Format_RGB32)
        frame.fill(Qt.white)
        tokens = [(word, [x, 10, x + 40, 38], score, 1) for x, word, score
                  in ((10, "intro", 97), (65, "Al", 22), (120, "finale", 96))]
        output = json.dumps([([10, 10, 160, 38], tokens)]).encode()
        with patch("reader.subprocess.run", return_value=SimpleNamespace(stdout=output)):
            for x, word, confidence in ((12, "intro", 97), (40, "Al", 22), (70, "finale", 96)):
                hit, score = read_from_pack(frame, QPointF(x, 10), "en")
                self.assertEqual((hit.word, score), (word, confidence))
