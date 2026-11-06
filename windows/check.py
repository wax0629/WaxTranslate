"""Regression checks. Pass --desktop to also exercise real screen capture and the UI."""

import asyncio
import ctypes
import os
import sys
import time
import unittest

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app import Window, image_point, image_rect
from reader import Passage, Word, passage_from_lines, recognize
from translation import translate


RIVER = "They sat on the river bank and watched the water."
MONEY = "She deposited her paycheck at the bank."
DESKTOP = "--desktop" in sys.argv
if DESKTOP:
    sys.argv.remove("--desktop")
else:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def word_in(text):
    start = text.index("bank")
    return Passage(text, (start, start + 4))


def wait_until(predicate):
    deadline = time.monotonic() + 12
    while not predicate():
        QApplication.processEvents()
        time.sleep(0.015)
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for desktop state")


class Checks(unittest.TestCase):
    def test_words_on_each_side_of_slash(self):
        for scale in (1, 1.5):
            font = QFont("Segoe UI")
            font.setPixelSize(28)
            for pair in ("read/write", "input/output", "TCP/IP"):
                left, right = pair.split("/")
                text = f"Choose {pair} or {pair}."
                image = QImage(int(680 * scale), int(70 * scale), QImage.Format_ARGB32)
                image.setDevicePixelRatio(scale)
                image.fill(Qt.white)
                painter = QPainter(image)
                painter.setFont(font)
                painter.drawText(10, 48, text)
                metrics = painter.fontMetrics()
                painter.end()
                start = text.rindex(pair)
                for part, offset in ((left, start), ("/", start + len(left)), (right, start + len(left) + 1)):
                    with self.subTest(scale=scale, pair=pair, part=part):
                        x = 10 + metrics.horizontalAdvance(text[:offset]) + metrics.horizontalAdvance(part) / 2
                        point = QPointF(x * scale, (48 - metrics.capHeight() / 2) * scale)
                        if part == "/":
                            with self.assertRaises(ValueError):
                                asyncio.run(recognize(image, point))
                        else:
                            read = asyncio.run(recognize(image, point))
                            self.assertEqual(read, Passage(text, (offset, offset + len(part))))

        for token in ("read-only", "don't"):
            word = Word(token, QRectF(10, 5, 120, 25))
            read = passage_from_lines([[word]], word.rect.center())
            self.assertEqual(read.word, token)

    def test_scaled_capture(self):
        logical, physical = QSize(520, 100), QSize(780, 150)
        image = QImage(physical, QImage.Format_ARGB32)
        image.setDevicePixelRatio(1.5)
        image.fill(Qt.white)
        painter = QPainter(image)
        font = QFont("Segoe UI")
        font.setPixelSize(19)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        painter.drawText(8, 34, RIVER)
        painter.drawText(8, 84, MONEY)
        painter.end()
        local = QPointF(8 + metrics.horizontalAdvance(RIVER.split("bank")[0] + "ba"), 28)
        hit = image_point(local, logical, physical)
        self.assertEqual(asyncio.run(recognize(image, hit)), word_in(RIVER))
        crop = image_rect(QRect(0, 53, 520, 47), logical, physical)
        self.assertEqual(asyncio.run(recognize(image.copy(crop))), Passage(MONEY))

    def test_exact_hit_in_wrapped_column(self):
        def row(text, left, top):
            result = []
            for token in text.split():
                box = QRectF(left, top, len(token) * 10, 18)
                result.append(Word(token, box))
                left += box.width() + 6
            return result
        first = row("Outside. The first bank and", 10, 10)
        second = row("the second bank are different.", 10, 37)
        side = row("Another column.", 360, 35)
        lines = [first, side, second]
        read = passage_from_lines(lines, second[2].rect.center())
        self.assertEqual(read.text, "The first bank and the second bank are different.")
        self.assertEqual(read.selection, (read.text.rindex("bank"), read.text.rindex("bank") + 4))
        with self.assertRaisesRegex(ValueError, "光标"):
            passage_from_lines(lines, QPointF(0, 0))

    def test_real_ocr_and_local_translation(self):
        font = QFont("Segoe UI", 20)
        metrics = QFontMetrics(font)
        for text, expected in [(RIVER, "岸"), (MONEY, "银行")]:
            image = QImage(metrics.horizontalAdvance(text) + 30, 90, QImage.Format_ARGB32)
            image.fill(Qt.white)
            painter = QPainter(image)
            painter.setFont(font)
            painter.drawText(10, 55, text)
            painter.end()
            hit = QPointF(10 + metrics.horizontalAdvance(text[:text.index("bank")]) +
                          metrics.horizontalAdvance("ba"), 55 - metrics.capHeight() / 2)
            read = asyncio.run(recognize(image, hit))
            self.assertEqual(read, word_in(text))
            origin, gloss, sentence = translate(read)
            self.assertEqual(origin, "句中释义")
            self.assertIn(expected, gloss)
            self.assertIn(expected, sentence)
            region = asyncio.run(recognize(image))
            self.assertEqual(region, Passage(text))
            self.assertIn(expected, translate(region)[1])

    @unittest.skipUnless(DESKTOP, "use --desktop with an unlocked Windows desktop")
    def test_desktop_flow(self):
        previous = QCursor.pos()
        window = Window()
        clicks = []

        class Sample(QLabel):
            def mouseReleaseEvent(self, event):
                clicks.append(event.modifiers())
                super().mouseReleaseEvent(event)

        sample = Sample(RIVER)
        sample.setFont(QFont("Segoe UI", 20))
        sample.setMargin(16)
        sample.setStyleSheet("color:black;background:white")
        sample.setWindowFlag(Qt.WindowStaysOnTopHint)
        sample.adjustSize()
        area = QApplication.primaryScreen().availableGeometry()
        sample.move(area.center() - sample.rect().center())
        sample.show()
        app = QApplication.instance()
        app.processEvents()
        metrics = sample.fontMetrics()
        point = sample.mapToGlobal(QPoint(16 + metrics.horizontalAdvance(RIVER.split("bank")[0] + "ba"),
                                          sample.height() // 2))
        QCursor.setPos(point)
        user = ctypes.windll.user32
        ctrl = 0xA2
        copies = []
        copy_shortcut = QShortcut("Ctrl+C", sample)
        copy_shortcut.activated.connect(lambda: copies.append(True))

        def key(code, down):
            user.keybd_event(code, user.MapVirtualKeyW(code, 0), 0 if down else 2, 0)

        def focus_sample():
            sample.raise_()
            sample.activateWindow()
            wait_until(sample.isActiveWindow)

        def begin_drag():
            focus_sample()
            QCursor.setPos(sample.mapToGlobal(sample.rect().bottomRight() - QPoint(4, 4)))
            key(ctrl, True)
            user.mouse_event(2, 0, 0, 0, 0)
            wait_until(lambda: window.gestures.owns_button)
            QCursor.setPos(sample.mapToGlobal(QPoint(4, 4)))
            user.mouse_event(1, 0, 0, 0, 0)  # move at the new cursor position
            wait_until(lambda: window.overlay is not None)

        try:
            self.assertIsNone(window.gestures.error)
            self.assertTrue(QTest.qWaitForWindowExposed(sample), "Sample window was never exposed")
            focus_sample()
            previous_ticket = window.ticket
            key(ctrl, True)
            key(ord("C"), True)
            key(ord("C"), False)
            key(ctrl, False)
            wait_until(lambda: copies and not window.gestures.ctrl_down)
            key(ctrl, True)
            user.mouse_event(2, 0, 0, 0, 0)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: bool(clicks))
            self.assertEqual(clicks, [Qt.ControlModifier])
            key(ctrl, False)
            wait_until(lambda: not window.gestures.ctrl_down)
            app.processEvents()
            self.assertEqual(window.ticket, previous_ticket, "Ctrl chord or Ctrl+click opened a card")
            key(ctrl, True)
            key(ctrl, False)
            wait_until(lambda: window.ticket != previous_ticket)
            # Moving after the shortcut must not retarget the delayed capture.
            QCursor.setPos(sample.mapToGlobal(QPoint(5, 5)))
            wait_until(lambda: window.card.isVisible() and window.card.caption.text() not in ("", "本机英译中"))
            self.assertEqual(window.card.caption.text(), "句中释义")
            self.assertIn("岸", window.card.text.toPlainText())
            QTest.keyClick(window.card, Qt.Key_Escape)
            self.assertFalse(window.card.isVisible())
            begin_drag()
            key(0x1B, True)
            key(0x1B, False)
            user.mouse_event(4, 0, 0, 0, 0)
            key(ctrl, False)
            wait_until(lambda: window.overlay is None)
            self.assertFalse(window.card.isVisible())
            begin_drag()
            user.mouse_event(4, 0, 0, 0, 0)
            key(ctrl, False)
            wait_until(lambda: window.card.caption.text() == "选区译文")
            self.assertIn("河岸", window.card.text.toPlainText())
            self.assertEqual(len(clicks), 1, "Capture drag reached the foreground window")
            window.demo()
            window.card.close()
            wait_until(lambda: window.pending.done())
            app.processEvents()
            self.assertFalse(window.card.isVisible(), "A dismissed request reopened its card")
        finally:
            if window.gestures.owns_button:
                key(0x1B, True)
                key(0x1B, False)
                user.mouse_event(4, 0, 0, 0, 0)
            if window.gestures.ctrl_down:
                key(ctrl, False)
            window.shutdown()
            sample.close()
            QCursor.setPos(previous)


if __name__ == "__main__":
    app = QApplication([])
    if not DESKTOP:
        # Qt's offscreen plugin has no system font database on Windows.
        font = os.path.join(os.environ["WINDIR"], "Fonts", "segoeui.ttf")
        if QFontDatabase.addApplicationFont(font) == -1:
            raise RuntimeError(f"Cannot load Windows test font: {font}")
    unittest.main()
