"""Word targeting regressions run by windows/check.py with a QApplication."""
import asyncio
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from reader import WORD_TOKEN, Word, ocr_lines, passage_from_lines, recognize, sentence_at
from workspace import TextWorkspace


class HitTests(unittest.TestCase):
    def test_near_word_boxes(self):
        for scale in (0.75, 1, 1.5, 2):
            def word(text, x, y, width):
                return Word(text, QRectF(x * scale, y * scale, width * scale, 20 * scale))

            first = [word("first", 10, 10, 34), word("PRD", 50, 10, 40), word("later", 100, 10, 45)]
            second = [word("second", 10, 40, 45), word("PRD", 61, 40, 40)]
            column = [word("Outside.", 200, 10, 70)]
            lines = [first, column, second]

            def lookup(x, y):
                return passage_from_lines(lines, QPointF(x * scale, y * scale))

            expected = lookup(74, 19)
            for x, y in ((74, 5), (74, 33), (49, 20), (92, 20), (49, 7), (50, 29)):
                with self.subTest(scale=scale, x=x, y=y):
                    result = lookup(x, y)
                    self.assertEqual(result, expected)
                    self.assertEqual(result.word, "PRD")
            self.assertNotIn("Outside", expected.context)
            repeat = lookup(72, 62)
            self.assertEqual(repeat.word, "PRD")
            self.assertGreater(repeat.selection[0], expected.selection[0])
            self.assertEqual(repeat.context_offset, repeat.context.rindex("PRD"))
            self.assertEqual(lookup(99, 20).word, "later")
            for x, y in ((47, 20), (47.4, 20), (48, 7), (95, 20), (72, 35), (163, 20), (75, 80)):
                with self.subTest(scale=scale, blank=(x, y)), self.assertRaisesRegex(ValueError, "光标"):
                    lookup(x, y)

    def test_original_spelling_and_context(self):
        words = ["C++", "C#", ".NET", "node.js", "GPT-4o", "C++17", "F#", "snake_case", "UTF-8",
                 "read-only", "don't", "naïve", "GPT‑4o", "GPT‐4o"]
        for word in words:
            with self.subTest(word=word):
                source = f"({word}),"
                self.assertEqual(WORD_TOKEN.findall(source), [word])
                item = Word(source, QRectF(10, 10, 100, 20))
                self.assertEqual(passage_from_lines([[item]], item.rect.center()).word, word)
        self.assertEqual(WORD_TOKEN.findall("在ChatGPT里读C++/C#。"), ["在", "ChatGPT", "里读", "C++", "C#"])
        article = "x. " * 1600 + "Project review dossier (PRD).\n\nCheck PRD and PRD." + " Fin." * 850
        start = article.index(" and PRD") + 5
        result = sentence_at(article, start, start + 3)
        self.assertEqual(result.text, "Check PRD and PRD.")
        self.assertEqual(result.selection, (14, 17))
        self.assertEqual(result.context[result.context_offset:result.context_offset + 3], "PRD")
        self.assertIn("dossier (PRD).\n\nCheck", result.context)
        self.assertEqual(len(result.context), 8003)

    def test_real_ocr_slightly_above_technical_word(self):
        for scale in (1, 1.5):
            image = QImage(int(570 * scale), int(80 * scale), QImage.Format_ARGB32)
            image.setDevicePixelRatio(scale)
            image.fill(Qt.white)
            painter = QPainter(image)
            font = QFont("Segoe UI")
            font.setPixelSize(28)
            painter.setFont(font)
            painter.drawText(10, 48, "Use C++ and Node.js with .NET.")
            painter.end()
            # Measure the boxes supplied by this system's English OCR.
            with patch("reader.passage_from_lines", wraps=passage_from_lines) as record:
                asyncio.run(recognize(image))
                lines, _ = record.call_args.args
            for token in ("C++", "Node.js", ".NET"):
                word = next(word for line in lines for word in line if token in word.text)
                point = QPointF(word.rect.center().x(), word.rect.top() - 0.25 * word.rect.height())
                self.assertFalse(word.rect.contains(point))
                with self.subTest(scale=scale, token=token):
                    self.assertEqual(asyncio.run(recognize(image, point)).word, token)

    def test_real_small_ocr_and_bounded_second_pass(self):
        text = "Use C++, C#, .NET and Node.js with GPT-4o."
        image = QImage(1700, 380, QImage.Format_ARGB32)
        image.fill(Qt.white)
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        painter = QPainter(image)
        painter.setFont(font)
        painter.drawText(1130, 320, text)
        metrics = painter.fontMetrics()
        painter.end()
        point = QPointF(1130 + metrics.horizontalAdvance("Use C++, C"), 320 - metrics.capHeight() / 2)
        # A short tooltip/label can fall below Windows OCR's minimum text size.
        label = image.copy(1120, 294, metrics.horizontalAdvance(text) + 40, 39)
        self.assertEqual(asyncio.run(recognize(label, point - QPointF(1120, 294))).word, "C#")
        point = QPointF(1130 + metrics.horizontalAdvance("Use C++, C#, .N"), point.y())
        frames = []

        async def miss_first(engine, frame):
            frames.append(frame.size())
            return [] if len(frames) == 1 else await ocr_lines(engine, frame)

        with patch("reader.ocr_lines", side_effect=miss_first):
            result = asyncio.run(recognize(image, point))
        self.assertEqual(result.word, ".NET")
        self.assertIn("Node.js", result.text)
        self.assertEqual((frames[1].width(), frames[1].height()), (2400, 640))
        with self.assertRaises(ValueError):
            asyncio.run(recognize(image, QPointF(point.x(), point.y() - 45)))

    def test_click_to_read_or_drag_to_select(self):
        ui = TextWorkspace(pool=None)
        self.addCleanup(ui.deleteLater)
        self.addCleanup(ui.close)
        ui.resize(460, 350)
        ui.show()
        QApplication.processEvents()
        editor = ui.input
        read = []
        editor.lookup_requested.connect(lambda passage, _: read.append(passage))
        source = QMimeData()
        source.setText("📖 Use C++ or C#.\nCheck Node.js then Node.js.")
        editor.insertFromMimeData(source)
        QApplication.processEvents()
        self.assertTrue(ui.lookup_hint.isVisible())
        self.assertTrue(ui.lookup_hint.isChecked())
        self.assertEqual(ui.panes.direction(), QBoxLayout.TopToBottom)
        term = editor.document().find("then Node.js")
        term.setPosition(term.selectionEnd() - 3)
        point = editor.cursorRect(term).center()
        QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual([p.word for p in read], ["Node.js"])
        self.assertEqual(read[0].selection[0], read[0].text.rindex("Node.js"))
        self.assertEqual(editor.textCursor().selectedText(), "Node.js")
        # Start a selection away from the previously selected text.
        start = editor.document().find("Use")
        start.setPosition(start.selectionStart())
        end = editor.document().find("C#")
        end.setPosition(end.selectionEnd())
        QTest.mousePress(editor.viewport(), Qt.LeftButton, pos=editor.cursorRect(start).center())
        QTest.mouseMove(editor.viewport(), editor.cursorRect(end).center())
        QTest.mouseRelease(editor.viewport(), Qt.LeftButton, pos=editor.cursorRect(end).center())
        self.assertIn("C++", editor.textCursor().selectedText())
        QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=editor.viewport().rect().bottomRight() - QPoint(2, 2))
        self.assertEqual(len(read), 1)
        ui.lookup_hint.click()
        editor.clear()
        editor.insertFromMimeData(source)
        self.assertFalse(ui.lookup_hint.isChecked())
        QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(len(read), 1)
        QTest.mouseDClick(editor.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(len(read), 2)
        self.assertEqual(read[-1].word, "Node.js")

    def test_editor_near_line_end(self):
        ui = TextWorkspace(pool=None)
        self.addCleanup(ui.deleteLater)
        self.addCleanup(ui.close)
        ui.show()
        editor = ui.input
        editor.setPlainText("First word.\nSecond line ends with ChatGPT")
        QApplication.processEvents()
        read = []
        editor.lookup_requested.connect(lambda passage, _: read.append(passage))
        cursor = editor.document().find("ChatGPT")
        cursor.setPosition(cursor.selectionEnd())
        edge = QPointF(editor.cursorRect(cursor).center())
        self.assertTrue(editor.lookup_point(edge + QPointF(3, 0)))
        self.assertEqual(read[0].word, "ChatGPT")
        self.assertFalse(editor.lookup_point(edge + QPointF(20, 0)))
