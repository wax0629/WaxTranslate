import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter
from winrt.windows.globalization import Language
from winrt.windows.media.ocr import OcrEngine

from app import analyze
from languages import NAMES, OCR_TAGS, UnsupportedLanguage, detect_source
from notebook import Notebook
from reader import Passage, WORD_TOKEN, Word, passage_from_lines, recognize, sentence_at, word_spans
from translation import japanese_fragment, translate_text
from workspace import ReadingEditor, utf16_length


SAMPLES = {
    "fr": ("Le chat dort dans la maison de ma sœur.", "chat"),
    "de": ("Die Katze schläft auf dem Sofa im Wohnzimmer.", "Katze"),
    "es": ("El gato duerme en la casa de mi hermana.", "gato"),
    "ja": ("猫は椅子の上で寝ています。", "猫"),
    "ko": ("고양이가 소파에서 자고 있습니다.", "고양이"),
    "it": ("Il gatto dorme sul divano in salotto.", "gatto"),
    "pt": ("O gato da minha irmã está dormindo no sofá da sala.", "gato"),
    "ru": ("Кошка спит на диване в гостиной.", "Кошка"),
}


class LanguageTests(unittest.TestCase):
    def test_automatic_paragraphs_and_word_alignment(self):
        paragraphs = "\n\n".join(sentence for sentence, _ in SAMPLES.values())
        result = translate_text(paragraphs, Event()).split("\n\n")
        self.assertEqual(len(result), len(SAMPLES))
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
            translate_text("De voorgestelde methode maakt het mogelijk om de temperatuur in deze omgeving te meten.", Event())

    def test_east_asian_editor_and_ocr_word_offsets(self):
        for code, text, word in (("ja", "🐾猫がいる。図書館で図書館の本を読む。", "図書館"),
                                 ("ko", "🐾 고양이가 잔다. 도서관에서 도서관으로 간다.", "도서관")):
            with self.subTest(code=code):
                editor = ReadingEditor()
                self.addCleanup(editor.deleteLater)
                editor.setPlainText(text)
                reads = []
                editor.lookup_requested.connect(lambda passage, _: reads.append(passage))
                start = text.rindex(word)
                self.assertTrue(editor.lookup_at(utf16_length(text[:start + 1])))
                read = reads.pop()
                self.assertEqual(read.word, word)
                self.assertEqual(read.selection[0], read.text.rindex(word))
                self.assertNotIn("🐾", read.text)
                self.assertIn("图书馆", analyze(None, None, Passage(word), code)[1][1])

        # Japanese OCR may give each character its own box. Korean OCR often
        # includes a noun and particle in one box. Both must retain occurrence.
        for code, chunks, hit in (("ja", ["図", "書", "館", "で", "図", "書", "館", "の", "本"], 5),
                                  ("ko", ["도서관에서", "도서관으로", "간다."], 1)):
            words = [Word(t, QRectF(i * 60, 0, 60, 20)) for i, t in enumerate(chunks)]
            p = passage_from_lines([words], QPointF(60 * hit + 12, 10), code)
            self.assertEqual(p.word, "図書館" if code == "ja" else "도서관")
            self.assertEqual(p.selection[0], p.text.rindex(p.word))
        korean = "고양이가"
        self.assertEqual([korean[a:b] for a, b in word_spans(korean)], ["고양이", "가"])

    def test_short_words_and_saved_languages(self):
        for word, expected in (("ありがとう", "谢"), ("감사합니다", "谢"), ("고양이", "猫"), ("Привет", "好|哈[罗啰]")):
            with self.subTest(word=word):
                self.assertRegex(translate_text(word, Event()), expected)
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
        word = "cafe\u0301"
        source = f"Près du {word}, le deuxième {word} est fermé."
        match = [m for m in WORD_TOKEN.finditer(source) if m.group() == word][1]
        passage = sentence_at(source, *match.span())
        from translation import aligned_selection
        with patch("translation.aligned_selection", wraps=aligned_selection) as align:
            analyze(None, None, passage, "fr")
        _, indices, _, tokenizer = align.call_args_list[0].args
        pieces = tokenizer.encode(source, return_type="proto").pieces
        selected_start = len(source[:match.start()].encode())
        self.assertEqual(indices, [i for i, p in enumerate(pieces)
                                   if p.begin < selected_start + len(word.encode()) and p.end > selected_start])

    def test_screen_word_and_region_with_installed_ocr(self):
        font = QFont("Segoe UI")
        font.setPixelSize(26)
        metrics = QFontMetrics(font)
        for code, (text, word) in SAMPLES.items():
            with self.subTest(code=code):
                if code in ("ja", "ko"):
                    # Rendered source glyphs stay the same on runners without CJK display fonts.
                    image = QImage(str(Path(__file__).parent / "testdata" / f"ocr-{code}.png"))
                    self.assertFalse(image.isNull())
                    hit = QPointF(28 if code == "ja" else 56, 44)
                else:
                    image = QImage(metrics.horizontalAdvance(text) + 40, 90, QImage.Format_RGB32)
                    image.fill(0xffffffff)
                    painter = QPainter(image)
                    painter.setFont(font)
                    painter.drawText(10, 55, text)
                    painter.end()
                    hit = QPointF(10 + metrics.horizontalAdvance(text[:text.index(word)]) +
                                  metrics.horizontalAdvance(word) / 2, 55 - metrics.capHeight() / 2)
                for setting in ("", code):
                    read, result, _, language, _ = analyze(image, hit, None, setting)
                    self.assertEqual((read.word.casefold(), language), (word.casefold(), NAMES[code]), (setting, read))
                    self.assertIn("猫", result[1], (read, result))
                    region = asyncio.run(recognize(image, None, setting))
                    with self.subTest(setting=setting or "auto", raw=region.text, detected=region.source_code):
                        _, result, _, name, _ = analyze(None, None, region, setting)
                        self.assertEqual(name, NAMES[code])
                        self.assertIn("猫", result[1])

    def test_screen_word_and_region_on_small_japanese_titles_without_system_pack(self):
        image = QImage(str(Path(__file__).parent / "testdata/ocr-japanese-list.png"))
        self.assertFalse(image.isNull())
        english = Language("en-US")
        engines = SimpleNamespace(available_recognizer_languages=[english],
                                  try_create_from_language=lambda lang: OcrEngine.try_create_from_language(lang)
                                  if lang.language_tag == english.language_tag else None,
                                  max_image_dimension=OcrEngine.max_image_dimension)
        with patch("reader.OcrEngine", engines):
            passage, result, _, language, _ = analyze(image, QPointF(64, 18), None)
            self.assertEqual((language, passage.word, passage.text), ("日语", "傷", "誰かが傷を負うその瞬間を"))
            self.assertIn("伤", result[1])
            phrase = japanese_fragment(passage)
            self.assertEqual((phrase.text, phrase.selection), ("誰かが傷を負うその瞬間", passage.selection))
            self.assertRegex(result[2], r"[\u3400-\u9fff]")
            passage, result, _, language, _ = analyze(image.copy(12, 57, 70, 24), None, None)
            self.assertEqual((language, passage.text), ("日语", "祝おう"))
            self.assertIn("庆祝", result[1])

    def test_auto_ocr_retries_an_installed_script_after_empty_latin_pass(self):
        image, point = object(), QPointF(18, 12)
        for code in ("ja", "ko", "ru"):
            with self.subTest(code=code):
                source, word = SAMPLES[code]
                start = source.index(word)
                expected = Passage(source, (start, start + len(word)))
                engines = SimpleNamespace(
                    available_recognizer_languages=[Language("en-US"), Language(OCR_TAGS[code])],
                    try_create_from_language=lambda lang: lang.language_tag)
                with patch("reader.OcrEngine", engines), patch("reader.read_from_pack", side_effect=ValueError()), patch("reader.read_passage", side_effect=[
                        ValueError("未识别到文字"), expected]) as read:
                    result = asyncio.run(recognize(image, point))
                self.assertEqual(result.source_code, code)
                self.assertEqual(result.word, word)
                self.assertEqual([c.args for c in read.await_args_list],
                                 [(Language("en-US").language_tag, image, point),
                                  (Language(OCR_TAGS[code]).language_tag, image, point)])

    def test_partial_kana_does_not_win_over_a_complete_korean_region(self):
        engines = SimpleNamespace(
            available_recognizer_languages=[Language(tag) for tag in ("en-US", "ja-JP", "ko-KR")],
            try_create_from_language=lambda lang: lang.language_tag)
        with patch("reader.OcrEngine", engines), patch("reader.read_from_pack", side_effect=ValueError()), patch("reader.read_passage", side_effect=[
                ValueError("未识别到文字"), Passage("ノ"), Passage(SAMPLES["ko"][0])]):
            result = asyncio.run(recognize(object()))
        self.assertEqual((result.source_code, result.text), ("ko", SAMPLES["ko"][0]))

    def test_short_latin_title_recovers_after_native_ocr_misses(self):
        font = QFont("Segoe UI")
        font.setPixelSize(15)
        image = QImage(160, 24, QImage.Format_RGB32)
        image.fill(0xfff2f6fb)
        with QPainter(image) as painter:
            painter.setFont(font)
            painter.drawText(5, 17, "conjoined (interlude)")
        with patch("reader.read_passage", side_effect=ValueError("no native hit")):
            for hit in (None, QPointF(38, 12)):
                result = asyncio.run(recognize(image, hit))
                self.assertEqual(result.text.casefold(), "conjoined (interlude)")
                self.assertNotEqual(result.source_code, "ko")
                if hit:
                    self.assertEqual(result.word.casefold(), "conjoined")

    def test_korean_fragments_among_misread_digits_do_not_establish_language(self):
        noise = "00미이060 (10160ㅁ406)"
        english = Language("en-US")
        engines = SimpleNamespace(available_recognizer_languages=[english],
                                  try_create_from_language=lambda lang: lang.language_tag)
        def only_noisy_read(image, point, code):
            if code == "ko":
                return Passage(noise, (2, 4) if point else None, source_code="ko"), 62
            raise ValueError("no confident Latin read")
        with (patch("reader.OcrEngine", engines), patch("reader.read_passage", side_effect=ValueError("未识别")),
              patch("reader.read_from_pack", side_effect=only_noisy_read)):
            for hit in (None, QPointF(5, 12)):
                with self.assertRaisesRegex(ValueError, "未识别"):
                    asyncio.run(recognize(object(), hit))
