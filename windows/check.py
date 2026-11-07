"""Regression checks. Pass --desktop to also exercise real screen capture and the UI."""

import asyncio
import ctypes
import faulthandler
import os
import sys
import time
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, QProcess, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QApplication, QLabel

from app import Window, app_icon, image_point, image_rect
from notebook import Notebook
from popup import Card
from reader import Passage, Word, passage_from_lines, recognize
from theme import apply_theme
from translation import translate
from workspace import TextWorkspace


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
    deadline = time.monotonic() + 30
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for desktop state")
        QApplication.processEvents()
        time.sleep(0.015)


class Checks(unittest.TestCase):
    def test_reading_card_layout(self):
        card = Card()
        area = QApplication.primaryScreen().availableGeometry()
        point = area.bottomRight()
        try:
            source = "A bank near the <river> bank."
            a = source.rindex("bank")
            card.show_result(Passage(source, (a, a + 4)), "句中释义", "岸", "河岸边有一家银行。", point)
            QApplication.processEvents()
            short = card.height()
            self.assertTrue(area.contains(card.geometry()))
            self.assertEqual(card.text.verticalScrollBar().maximum(), 0)
            self.assertIn(source, card.text.toPlainText())
            doc = card.text.document()
            first = doc.find("bank", doc.find("bank"))
            second = doc.find("bank", first)
            self.assertEqual(first.charFormat().background().style(), Qt.NoBrush)
            self.assertNotEqual(second.charFormat().background().style(), Qt.NoBrush)

            word = "inter" * 110
            card.show_result(Passage(word, (0, len(word))), "单词参考", "参考", "译文", point)
            QApplication.processEvents()
            self.assertEqual(card.caption.text(), "单词参考")
            self.assertGreater(card.text.verticalScrollBar().maximum(), 0)
            self.assertEqual(card.text.horizontalScrollBar().maximum(), 0)
            self.assertTrue(card.save.isVisibleTo(card))
            card.text.verticalScrollBar().setValue(card.text.verticalScrollBar().maximum())
            card.show_result(Passage("Example. " * 150), "选区译文", "示例。" * 150, "", point)
            QApplication.processEvents()
            self.assertTrue(area.contains(card.geometry()))
            self.assertEqual(card.text.verticalScrollBar().value(), 0)
            self.assertTrue(card.copy.isVisibleTo(card))
            self.assertFalse(card.save.isVisibleTo(card))
            self.assertTrue(card.rect().contains(card.copy.mapTo(card, card.copy.rect().center())))

            card.show_message("需要处理", "未识别到 <text>。", point)
            QApplication.processEvents()
            self.assertLess(card.height(), short)
            self.assertEqual(card.text.toPlainText(), "未识别到 <text>。")
            self.assertFalse(card.copy.isVisibleTo(card))
            QTest.keyClick(card.text, Qt.Key_Escape)
            self.assertFalse(card.isVisible())
        finally:
            card.close()

    def test_inline_keyboard_translation(self):
        with patch.object(QProcess, "start"):
            window = Window()
            ui = window.workspace
            try:
                window.resize(880, 510)
                window.show()
                window.activateWindow()
                wait_until(ui.input.hasFocus)
                self.assertGreater(ui.output.mapTo(ui, QPoint()).x(), ui.input.mapTo(ui, QPoint()).x())
                ui.input.setPlainText(RIVER + "\n\n" + MONEY)
                QTest.keyClick(ui.input, Qt.Key_Return, Qt.ControlModifier)
                wait_until(ui.copy.isEnabled)
                river, money = ui.output.toPlainText().split("\n\n")
                self.assertIn("岸", river)
                self.assertIn("银行", money)
                self.assertTrue(ui.input.hasFocus())
                self.assertFalse(window.card.isVisible())
                QTest.keyClick(ui.input, Qt.Key_C, Qt.ControlModifier | Qt.ShiftModifier)
                self.assertEqual(QApplication.clipboard().text(), ui.output.toPlainText())
                ui.input.setPlainText("仅中文")
                self.assertFalse(ui.copy.isEnabled())
                ui.submit.click()
                wait_until(lambda: ui.pending is None)
                self.assertIn("英文", ui.output.toPlainText())
                self.assertFalse(ui.copy.isEnabled())
                ui.input.setPlainText(RIVER)
                QTest.keyClick(ui.input, Qt.Key_Enter, Qt.ControlModifier)
                wait_until(ui.copy.isEnabled)
                self.assertIn("岸", ui.output.toPlainText())
                window.resize(610, 490)
                wait_until(lambda: ui.output.mapTo(ui, QPoint()).y() > ui.input.mapTo(ui, QPoint()).y())
                self.assertTrue(window.hints.isHidden())
                window.hint_button.click()
                self.assertFalse(window.hints.isHidden())
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_superseded_inline_result(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            old, new, cancelled = Future(), Future(), Future()
            old.set_running_or_notify_cancel()
            cancelled.set_running_or_notify_cancel()
            ui = TextWorkspace(pool)
            with patch.object(pool, "submit", side_effect=[old, new, cancelled]):
                ui.input.setPlainText(RIVER)
                ui.submit.click()
                stop_old = ui.stop
                ui.input.setPlainText(MONEY)
                self.assertTrue(stop_old.is_set())
                ui.submit.click()
                new.set_result("银行")
                old.set_result("河岸")
                QApplication.processEvents()
                self.assertEqual(ui.output.toPlainText(), "银行")
                self.assertTrue(ui.copy.isEnabled())
                ui.submit.click()
                stop_cancelled = ui.stop
                ui.submit.click()
                self.assertTrue(stop_cancelled.is_set())
                cancelled.set_result("过期结果")
                QApplication.processEvents()
                self.assertFalse(ui.copy.isEnabled())
                self.assertEqual(ui.output.toPlainText(), "")

    def test_save_copy_review_and_reopen(self):
        from PySide6.QtWidgets import QMessageBox

        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            path = Path(tmp) / "notebook.sqlite3"
            book = Notebook(path)
            window = Window(notebook=book)
            self.assertFalse(app_icon().isNull())
            self.assertTrue(window.findChild(QSvgWidget, "brandMark").renderer().isValid())
            try:
                window.demo()
                wait_until(lambda: window.card.save.isVisible())
                window.card.copy.click()
                self.assertIn("岸", QApplication.clipboard().text())
                window.card.save.click()
                self.assertEqual(window.card.save.text(), "已收藏")
                window.save_word()
                self.assertEqual(len(Notebook(path).entries()), 1)
                second = word_in(MONEY)
                book.save(second, translate(second))
                window.card.close()
                window.open_library()
                wait_until(lambda: window.library.list.count() == 2)
                ui = window.library
                ui.search.setText("PAYCHECK")
                self.assertEqual(ui.current()["context"], MONEY)
                ui.search.setText("岸")
                self.assertEqual(ui.current()["context"], RIVER)
                ui.search.setText("no matching sentence")
                self.assertIsNone(ui.current())
                self.assertTrue(ui.no_matches.isVisible())
                ui.review.click()
                self.assertTrue(ui.testing)
                self.assertFalse(ui.list.isVisible())
                self.assertFalse(ui.known.isVisible())
                entry = ui.current()
                ui.reveal.click()
                self.assertIn(entry["gloss"], ui.detail.toPlainText())
                ui.known.click()
                ui.reveal.click()
                ui.again.click()
                self.assertFalse(ui.testing)
                self.assertTrue(ui.no_matches.isVisible())
                ui.search.clear()
                self.assertIsNotNone(ui.current())
                rows = Notebook(path).entries()
                now = time.time()
                self.assertTrue(590 < rows[0]["due"] - now <= 600)
                self.assertTrue(86390 < rows[1]["due"] - now <= 86400)
                with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                    ui.remove.click()
                self.assertEqual(len(Notebook(path).entries()), 1)
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

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
        gestures = []

        class TestWindow(Window):
            def on_gesture(self, action, origin, end):
                gestures.append((action, origin, end))
                super().on_gesture(action, origin, end)

        window = TestWindow()
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
        user = ctypes.windll.user32
        ctrl = 0xA2
        copies = []
        copy_shortcut = QShortcut("Ctrl+C", sample)
        copy_shortcut.activated.connect(lambda: copies.append(True))

        def key(code, down):
            user.keybd_event(code, user.MapVirtualKeyW(code, 0), 0 if down else 2, 0)

        def move_cursor(global_point):
            screen = sample.screen()
            origin = screen.geometry().topLeft()
            native = origin + (global_point - origin) * screen.devicePixelRatio()
            x, y, w, h = (user.GetSystemMetrics(metric) for metric in (76, 77, 78, 79))
            user.mouse_event(0xC001, round((native.x() - x) * 65535 / (w - 1)),
                             round((native.y() - y) * 65535 / (h - 1)), 0, 0)

        def focus_sample():
            sample.raise_()
            sample.activateWindow()
            wait_until(sample.isActiveWindow)

        def begin_drag():
            focus_sample()
            move_cursor(sample.mapToGlobal(sample.rect().bottomRight() - QPoint(4, 4)))
            key(ctrl, True)
            user.mouse_event(2, 0, 0, 0, 0)
            move_cursor(sample.mapToGlobal(QPoint(4, 4)))
            wait_until(lambda: window.overlay is not None)

        try:
            wait_until(lambda: window.gesture_ready or not window.gesture_warning.isHidden())
            self.assertTrue(window.gesture_ready, window.gesture_warning.text())
            self.assertTrue(QTest.qWaitForWindowExposed(sample), "Sample window was never exposed")
            focus_sample()
            move_cursor(point)
            previous_ticket = window.ticket
            key(ctrl, True)
            key(ord("C"), True)
            key(ord("C"), False)
            key(ctrl, False)
            wait_until(lambda: bool(copies))
            key(ctrl, True)
            user.mouse_event(2, 0, 0, 0, 0)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: bool(clicks))
            self.assertEqual(clicks, [Qt.ControlModifier])
            key(ctrl, False)
            app.processEvents()
            self.assertEqual(window.ticket, previous_ticket, "Ctrl chord or Ctrl+click opened a card")
            key(ctrl, True)
            key(ctrl, False)
            wait_until(lambda: window.ticket != previous_ticket)
            # Moving after the shortcut must not retarget the delayed capture.
            move_cursor(sample.mapToGlobal(QPoint(5, 5)))
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
        except AssertionError as error:
            future = window.pending
            self.fail(f"{error}; recent gestures={gestures[-8:]}, ticket={window.ticket}, "
                      f"card=({window.card.isVisible()}, {window.card.caption.text()!r}), "
                      f"worker={future}, overlay={window.overlay is not None}")
        finally:
            window.shutdown()
            if user.GetAsyncKeyState(1) & 0x8000:
                user.mouse_event(4, 0, 0, 0, 0)
            if user.GetAsyncKeyState(ctrl) & 0x8000:
                key(ctrl, False)
            sample.close()
            QCursor.setPos(previous)


if __name__ == "__main__":
    if DESKTOP:
        # A native input stall can block the event loop itself, bypassing
        # wait_until's timeout. Preserve the stack in the runner log.
        faulthandler.dump_traceback_later(75, exit=True)
    app = QApplication([])
    if not DESKTOP:
        # Qt's offscreen plugin has no system font database on Windows.
        font = os.path.join(os.environ["WINDIR"], "Fonts", "segoeui.ttf")
        if QFontDatabase.addApplicationFont(font) == -1:
            raise RuntimeError(f"Cannot load Windows test font: {font}")
    apply_theme(app)
    unittest.main()
