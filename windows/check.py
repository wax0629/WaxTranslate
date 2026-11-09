"""Regression checks. Pass --desktop to also exercise real screen capture and the UI."""

import asyncio
import ctypes
from ctypes import wintypes
import faulthandler
import io
import importlib.util
import json
import os
import sys
import time
import unittest
import wave
from types import SimpleNamespace
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QProcess, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QFontMetrics, QImage, QMouseEvent, QPainter, QRegion, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from app import Window, app_icon, image_point, image_rect
from home import HomePage
from notebook import Dashboard, Notebook
from popup import Card
from reader import Passage, Word, context_excerpt, passage_from_lines, recognize
from theme import apply_theme
from translation import translate, translate_lookup
from word_details import part_of_speech
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
    def test_home_background_is_independent_of_lookup_history(self):
        home = HomePage()
        home.setAttribute(Qt.WA_DontShowOnScreen)
        home.show()
        rows = [(f"word-{n}", "en", "释义", 1700000000) for n in range(6)]
        try:
            for width, height in ((1000, 582), (728, 529), (540, 764)):
                home.resize(width, height)
                baseline = None
                for snapshot in (Dashboard(0, 0, 0, 0, 0, []), Dashboard(6, 0, 0, 0, 0, []), Dashboard(7, 1, 0, 0, 0, rows[:1]),
                                 Dashboard(12, 6, 0, 0, 0, rows), None):
                    home.set_stats(snapshot)
                    QApplication.processEvents()
                    # Render the page layer without its foreground text and controls.
                    layer = QImage(home.size(), QImage.Format_ARGB32_Premultiplied)
                    layer.fill(Qt.transparent)
                    with QPainter(layer) as painter:
                        home.render(painter, QPoint(), QRegion(), QWidget.RenderFlag(0))
                    if baseline is None:
                        baseline = layer
                    else:
                        self.assertEqual(layer, baseline, (width, height, snapshot))
        finally:
            home.close()
            home.deleteLater()

    @unittest.skipUnless(DESKTOP, "sample the composited edges on an isolated desktop")
    def test_desktop_visible_window_edges(self):
        user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        user.GetDC.argtypes, user.GetDC.restype = (wintypes.HWND,), wintypes.HDC
        user.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
        user.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        gdi.GetPixel.argtypes, gdi.GetPixel.restype = (wintypes.HDC, ctypes.c_int, ctypes.c_int), wintypes.DWORD

        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            window = Window(Notebook(Path(tmp) / "frame.sqlite"))
            dc = user.GetDC(None)
            try:
                area = window.screen().availableGeometry()
                window.setGeometry(area.x() + 12, area.y() + 12,
                                   min(728, area.width() - 24), min(565, area.height() - 24))
                window.open_home()

                def verify_pixels(active=True):
                    wait_until(lambda: window.isActiveWindow() == active)
                    QTest.qWait(250)  # Allow the compositor's restore/activation animation to finish.
                    ctypes.windll.dwmapi.DwmFlush()
                    expected = window.grab().toImage()
                    w, h = expected.width(), expected.height()
                    # The app's hairline occupies one device pixel at either scaling.
                    self.assertEqual(expected.pixelColor(w * 3 // 5, 0) == expected.pixelColor(w * 3 // 5, 1),
                                     window.isMaximized())
                    origin = wintypes.POINT()
                    self.assertTrue(user.ClientToScreen(int(window.winId()), ctypes.byref(origin)))
                    for inset in (1, 3, 5):
                        for x, y in ((w * 3 // 5, inset), (inset, h // 2),
                                     (w - 1 - inset, h // 4), (w // 8, h - 1 - inset)):
                            rgb = gdi.GetPixel(dc, origin.x + x, origin.y + y)
                            actual = tuple((rgb >> shift) & 255 for shift in (0, 8, 16))
                            wanted = expected.pixelColor(x, y).getRgb()[:3]
                            self.assertLessEqual(max(abs(a - b) for a, b in zip(actual, wanted)), 12,
                                                 (x, y, actual, wanted, window.windowState()))

                verify_pixels()
                focus_target = QLabel("桌面边缘测试")
                try:
                    focus_target.move(window.geometry().center())
                    focus_target.show()
                    focus_target.activateWindow()
                    verify_pixels(active=False)
                finally:
                    focus_target.close()
                window.open_home()
                window.maximize_button.click()
                self.assertTrue(window.isMaximized())
                verify_pixels()
                window.maximize_button.click()
                verify_pixels()
                window.showMinimized()
                wait_until(lambda: not window.isVisible() or window.isMinimized())
                window.open_home()
                verify_pixels()
            finally:
                user.ReleaseDC(None, dc)
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_shell_reflows_on_first_show_and_resize(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            window = Window(Notebook(Path(tmp) / "book.sqlite"))
            try:
                window.resize(570, 485)
                window.show()
                wait_until(lambda: window.compact is True)
                self.assertLessEqual(window.width(), 572)
                window.resize(872, 535)
                wait_until(window.wordmark.isVisible)
                self.assertTrue(QFontDatabase.hasFamily("Spectral"))
                self.assertGreaterEqual(window.wordmark.width(), window.wordmark.fontMetrics().horizontalAdvance("WaxTranslate"))
                home = window.home
                self.assertFalse(window.backdrop.isNull())
                nav = [b for b in window.sidebar.findChildren(QPushButton) if b.property("role") == "nav"]
                self.assertEqual([b.text() for b in nav], ["首页", "对照翻译", "生词本", "设置"])
                wait_until(lambda: home.values["次取词"].text() == "0")
                for width, height in ((1080, 675), (820, 500), (740, 480), (570, 485), (540, 610), (540, 800)):
                    window.resize(width, height)
                    QApplication.processEvents()
                    self.assertGreaterEqual(window.sidebar.height(), 44)
                    self.assertLessEqual(window.sidebar.height(), 56)
                    self.assertGreaterEqual(window.wordmark.width(), window.wordmark.sizeHint().width())
                    for button in nav:
                        self.assertTrue(window.sidebar.rect().contains(button.geometry()))
                        self.assertGreaterEqual(button.width(), button.sizeHint().width())
                    self.assertGreater(nav[-1].x(), nav[-2].geometry().right())
                    self.assertTrue(all(v.isVisible() and v.text() == "0" for v in home.values.values()))
                    self.assertTrue(home.heading.isVisible())
                    for control in (home.heading, home.instructions):
                        bounds = QRect(control.mapTo(home, QPoint()), control.size())
                        self.assertTrue(home.rect().contains(bounds), (width, height, bounds))
                    self.assertGreaterEqual(home.instructions.width(), home.instructions.layout().sizeHint().width())
                    self.assertLessEqual(abs(home.instructions.y() - home.page.contentsMargins().top()), 2)
                    self.assertLess(home.instructions.geometry().bottom(), home.heading.y())
                # Migrated profiles and a read failure must not look like a fresh notebook.
                window.resize(540, 390)
                QApplication.processEvents()
                short_window_size = window.size()
                heading_at = home.heading.y()
                for snapshot in (Dashboard(17, 0, 2, 1, 0, []), Dashboard(6, 0, 0, 0, 0, [])):
                    home.set_stats(snapshot)
                    QApplication.processEvents()
                    self.assertEqual(home.values["次取词"].text(), str(snapshot.total))
                    self.assertTrue(home.notice.isVisible())
                    self.assertEqual(home.heading.y(), heading_at)
                home.set_stats(None)
                self.assertIn("无法读取", home.notice.text())
                self.assertTrue(all(v.text() == "—" for v in home.values.values()))
                rows = [(f"word-{i}", "en", "释义", 1700000000) for i in range(6)]
                home.set_stats(Dashboard(18, 1, 2, 1, 1, rows))
                QApplication.processEvents()
                self.assertEqual(home.heading.y(), heading_at)
                self.assertFalse(home.notice.isVisible())
                self.assertEqual([v.text() for v in home.values.values()], ["18", "2", "1", "1"])
                self.assertTrue(home.table.isVisible())
                self.assertEqual(home.table.rowCount(), 6)
                for width, height in ((1000, 620), (540, 800), (540, 390)):
                    window.resize(width, height)
                    QApplication.processEvents()
                    self.assertFalse(any(b.text() == "框选翻译" for b in home.findChildren(QPushButton)))
                    self.assertTrue(window.app_menu.isVisible())
                    self.assertIs(window.app_menu.menu(), window.tray.contextMenu())
                    self.assertLessEqual(abs(home.instructions.y() - home.page.contentsMargins().top()), 2)
                    if height >= 620:
                        self.assertEqual(home.table.verticalScrollBar().maximum(), 0)
                    else:
                        self.assertEqual(window.size(), short_window_size)
                        home.table.scrollToBottom()
                        self.assertGreaterEqual(home.table.rowAt(home.table.viewport().height() - 2), 5)
                window.resize(570, 485)
                self.assertLessEqual(window.width(), 572)
                for index, button in enumerate(nav):
                    button.setFocus()
                    QTest.keyClick(button, Qt.Key_Space)
                    self.assertEqual(window.tabs.currentIndex(), index)
                    self.assertTrue(button.isChecked())
                nav[2].click()
                self.assertIs(window.tabs.currentWidget(), window.library)
                self.assertFalse(any(button.text() == "打开对照翻译" for button in window.library.empty.findChildren(QPushButton)))
                nav[1].setFocus()
                QTest.keyClick(nav[1], Qt.Key_Space)
                self.assertIs(window.tabs.currentWidget(), window.reader_page)
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_read_from_editor(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            window = Window(notebook=Notebook(Path(tmp) / "book.sqlite"))
            ui = window.workspace
            editor = ui.input
            try:
                window.resize(870, 530)
                window.show()
                window.activateWindow()
                next(b for b in window.sidebar.findChildren(QPushButton) if b.text() == "对照翻译").click()
                wait_until(ui.example.isVisible)
                ui.example.click()
                wait_until(window.card.save.isVisible)
                self.assertEqual(window.saved_result[0], word_in(RIVER))
                self.assertIn(MONEY, editor.toPlainText())
                window.card.close()
                source = "📖 Notes.\n\nThey record the first record, then\nreview the second record."
                editor.setPlainText(source)
                self.assertFalse(ui.example.isVisible())
                word = editor.document().find("second record")
                word.setPosition(word.selectionEnd() - 3)
                editor.setTextCursor(word)
                editor.setFocus()
                point = editor.cursorRect().center()
                QTest.mouseDClick(editor.viewport(), Qt.LeftButton, pos=point)
                wait_until(window.card.save.isVisible)
                expected = "They record the first record, then review the second record."
                selected = Passage(expected, (expected.rindex("record"), len(expected) - 1))
                self.assertEqual(window.saved_result[0], selected)
                self.assertEqual(editor.textCursor().selectedText(), "record")
                window.card.save.click()
                self.assertEqual(window.notebook.entries()[0]["position"], selected.selection[0])
                window.card.close()
                editor.setTextCursor(editor.document().find("first"))
                editor.setFocus()
                window.activateWindow()
                wait_until(lambda: window.isActiveWindow() and editor.hasFocus())
                QTest.keyClick(editor, Qt.Key_Return, Qt.AltModifier)
                wait_until(window.card.save.isVisible)
                self.assertEqual(window.saved_result[0].word, "first")
                editor.setPlainText("Use the read/write switch.")
                self.assertFalse(window.card.isVisible())
                editor.setTextCursor(editor.document().find("write"))
                editor.lookup_cursor()
                wait_until(window.card.save.isVisible)
                self.assertEqual(window.saved_result[0].word, "write")
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_trigger_preference(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            book = Notebook(Path(tmp) / "words.sqlite")
            first = Window(notebook=book)
            try:
                self.assertEqual(first.trigger.currentData(), "left")
                first.trigger.setCurrentIndex(first.trigger.findData("off"))
                self.assertIn("双击单词", first.home.instructions.accessibleName())
            finally:
                first.shutdown()
                first.deleteLater()
            reopened = Window(notebook=book)
            try:
                self.assertEqual(reopened.trigger.currentData(), "off")
                reopened.demo()
                wait_until(reopened.card.save.isVisible)
                self.assertEqual(reopened.saved_result[0], word_in(RIVER))
            finally:
                reopened.shutdown()
                reopened.deleteLater()

    def test_home_lookup_and_dashboard(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            book = Notebook(Path(tmp) / "book.sqlite")
            window = Window(notebook=book)
            home = window.home
            try:
                window.show()
                self.assertIs(window.tabs.currentWidget(), home)
                wait_until(lambda: home.values["次取词"].text() == "0" and home.heading.isVisible())
                self.assertTrue(home.notice.isVisible())
                self.assertTrue(home.heading.isVisible())
                self.assertEqual(home.table.rowCount(), 0)
                self.assertEqual(home.key.text(), "左 Ctrl")
                self.assertTrue(home.key.isVisible())
                self.assertFalse(any(b.text() == "对照翻译" for b in home.findChildren(QPushButton)))
                window.navigation.button(window.tabs.indexOf(window.reader_page)).click()
                self.assertIs(window.tabs.currentWidget(), window.reader_page)
                editor = window.workspace.input
                editor.setPlainText(RIVER)
                editor.setTextCursor(editor.document().find("bank"))
                editor.lookup_cursor()
                wait_until(window.card.save.isVisible)
                self.assertEqual(window.saved_result[0], word_in(RIVER))
                window.card.save.click()
                window.card.close()
                window.tabs.setCurrentWidget(home)
                wait_until(lambda: home.values["次取词"].text() == "1" and home.table.isVisible()
                           and home.values["已保存"].text() == "1")
                self.assertEqual(home.table.item(0, 0).text(), "bank")
                self.assertIn("岸", home.table.item(0, 1).text())
                self.assertEqual(home.table.item(0, 2).text(), "刚刚")
                self.assertEqual(home.values["待复习"].text(), "1")
                window.open_library()
                window.library.review.click()
                window.library.reveal.click()
                window.library.known.click()
                window.tabs.setCurrentWidget(home)
                wait_until(lambda: home.values["已保存"].text() == "1" and home.values["待复习"].text() == "0")
                window.trigger.setCurrentIndex(window.trigger.findData("right"))
                self.assertEqual(home.key.text(), "右 Ctrl")
                window.trigger.setCurrentIndex(window.trigger.findData("off"))
                self.assertIn("双击单词", home.instructions.accessibleName())
                self.assertFalse(home.key.isVisible())
                self.assertEqual(editor.toPlainText(), RIVER)
                with patch.object(window, "begin") as begin:
                    next(a for a in window.tray.contextMenu().actions() if a.text() == "框选翻译").trigger()
                    begin.assert_called_once_with(True)

                # Neither a completed region nor a superseded word is a new word lookup.
                job = Future()
                job.set_result((Passage(RIVER), ("选区译文", "译文", ""), None, "英语", ""))
                window.show_result(window.ticket, QPoint(10, 10), job)
                word = Future()
                word.set_result((word_in(RIVER), ("句中释义", "岸", "译文"), None, "英语", "名词"))
                window.show_result(window.ticket - 1, QPoint(10, 10), word)
                window.stats_pool.submit(lambda: None).result(timeout=5)
                self.assertEqual(book.home_stats(), (1, 1, 0))
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_lookup_during_paragraph_translation(self):
        translating, release = Event(), Event()

        def long_translation(_text, _stop, _source):
            translating.set()
            release.wait(10)
            return "段落译文"

        with patch.object(QProcess, "start"), patch("workspace.translate_text", side_effect=long_translation):
            window = Window()
            try:
                window.workspace.input.setPlainText(RIVER)
                window.workspace.translate_text()
                self.assertTrue(translating.wait(3))
                window.lookup_text(word_in(RIVER), QPoint(20, 20))
                wait_until(lambda: window.saved_result is not None)
                self.assertFalse(window.workspace.pending.done())
                release.set()
                wait_until(window.workspace.copy.isEnabled)
                self.assertEqual(window.workspace.output.toPlainText(), "段落译文")
            finally:
                release.set()
                window.shutdown()
                window.deleteLater()

    def test_speech_controls_and_review(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            worker = folder / "test_voice.py"
            log = folder / "last.json"
            worker.write_text(
                "import json, sys, time\nfrom pathlib import Path\n"
                "text, slow, language = json.loads(sys.stdin.buffer.read())\n"
                "assert language == 'en'\n"
                "Path(__file__).with_name('last.json').write_text(json.dumps([text,slow]))\n"
                "if text == 'failure':\n"
                "    sys.stdout.buffer.write('请检查声音输出设备'.encode('utf-8'))\n    sys.exit(1)\n"
                "time.sleep(20)\n", encoding="utf-8")
            with patch.object(QProcess, "start"):
                window = Window(notebook=Notebook(folder / "words.sqlite"))
            def played(expected):
                wait_until(lambda: log.exists() and log.read_text() == json.dumps(expected))
                log.unlink()
            with patch("speech.WORKER", worker):
                try:
                    window.demo()
                    wait_until(window.card.save.isVisible)
                    card = window.card
                    card.listen.click()
                    played(["bank", False])
                    self.assertEqual(card.listen.text(), "停止")
                    card.listen.slow.trigger()
                    played(["bank", True])
                    self.assertIs(window.player.owner, card.listen)
                    card.listen.read.trigger()
                    played([RIVER, False])
                    card.listen.click()
                    self.assertIsNone(window.player.owner)
                    card.listen.play("failure")
                    wait_until(card.speech_error.isVisible)
                    self.assertTrue(card.save.isEnabled())
                    card.listen.slow_sentence.trigger()
                    played([RIVER, True])
                    self.assertFalse(card.speech_error.isVisible())
                    card.save.click()
                    card.close()
                    self.assertIsNone(window.player.owner)
                    window.open_library()
                    library = window.library
                    library.review.click()
                    self.assertNotIn("河岸", library.detail.toPlainText())
                    library.listen.read.trigger()
                    played([RIVER, False])
                    library.reveal.click()
                    library.again.click()
                    self.assertIsNone(window.player.owner)
                    self.assertIn("本轮已复习 1 条", library.status.text())
                    self.assertIn("下次复习", library.status.text())
                    window.tabs.setCurrentIndex(0)
                    self.assertIsNone(window.player.owner)
                finally:
                    window.shutdown()
                    window.hide()
                    window.deleteLater()

    def test_local_english_voice(self):
        from speech_worker import SpeechUnavailable, modern_voice_audio, synthesize

        with patch("winrt.windows.media.speechsynthesis.SpeechSynthesizer",
                   SimpleNamespace(all_voices=[SimpleNamespace(language="zh-CN")])):
            with self.assertRaisesRegex(SpeechUnavailable, "添加英语声音"):
                asyncio.run(modern_voice_audio("record", False))

        durations = []
        for slow in (False, True):
            try:
                wav = synthesize("They record a record.", slow)
            except SpeechUnavailable as error:
                self.assertIn("英语声音", str(error))
                self.skipTest("No English system voice on this machine")
            with wave.open(io.BytesIO(wav)) as clip:
                self.assertGreater(clip.getframerate(), 8000)
                durations.append(clip.getnframes() / clip.getframerate())
                self.assertGreater(len(set(clip.readframes(clip.getnframes()))), 8)
        self.assertGreater(durations[1], durations[0] * 1.15)

    @unittest.skipUnless(DESKTOP, "exercise the real playback endpoint only on an isolated desktop")
    def test_desktop_playback(self):
        card = Card()
        errors = []
        card.listen.notice.connect(lambda text: errors.append(text) if text else None)
        try:
            card.show_result(word_in(RIVER), "句中释义", "岸", "河岸", QPoint(24, 24), language="英语", pos="名词")
            card.listen.click()
            wait_until(lambda: card.listen.player.owner is None)
            if errors:
                if "添加英语声音" in errors[-1]:
                    self.skipTest("English voice unavailable: " + errors[-1])
                self.assertEqual(ctypes.windll.winmm.waveOutGetNumDevs(), 0, errors[-1])
                self.assertIn("声音输出设备", errors[-1])
            print("No audio output endpoint; recovery message verified." if errors else "System playback completed.")
        finally:
            card.listen.player.shutdown()
            card.close()

    def test_word_details_in_context(self):
        source = "They record a record."
        for start, expected in [(source.index("record"), "动词"), (source.rindex("record"), "名词")]:
            self.assertEqual(part_of_speech(Passage(source, (start, start + 6))), expected)
        self.assertEqual(part_of_speech(Passage("record", (0, 6))), "")
        with patch.object(QProcess, "start"):
            window = Window()
            card = window.card
            point = QApplication.primaryScreen().availableGeometry().topLeft() + QPoint(5, 5)
            try:
                window.submit(point, passage=word_in(RIVER))
                wait_until(card.save.isVisible)
                self.assertIn("名词 · 英语", card.text.toPlainText())
                window.invalidate()
                source = "De voorgestelde methode maakt het mogelijk om de temperatuur in deze omgeving te meten."
                window.submit(point, passage=Passage(source))
                wait_until(lambda: card.copy.isVisible() and card.copy.text() == "复制原文")
                self.assertEqual(card.caption.text(), "荷兰语原文")
                self.assertFalse(card.save.isVisible())
                card.copy.click()
                self.assertEqual(QApplication.clipboard().text(), source)
                window.invalidate()
                window.submit(point, passage=Passage("record", (0, 6)))
                wait_until(card.save.isVisible)
                self.assertIn("英语", card.text.toPlainText())
                self.assertNotIn("词性待定", card.text.toPlainText())
                window.invalidate()
                window.submit(point, passage=Passage(RIVER))
                wait_until(card.copy.isVisible)
                self.assertIn("英语 → 简体中文", card.text.toPlainText())
                self.assertNotIn("词性", card.text.toPlainText())
            finally:
                window.shutdown()
                window.deleteLater()

    def test_dragged_position_survives_result_and_expand(self):
        card = Card()
        area = QApplication.primaryScreen().availableGeometry()
        point = area.topLeft() + QPoint(3, 4)
        try:
            card.show_message("本机翻译", "正在读取并翻译…", point)
            QApplication.processEvents()
            start = card.pos()
            press = card.grip.mapToGlobal(card.grip.rect().center())
            # Leave the full screen height for the expanded card. At 150%
            # scaling a downward drag can legitimately trigger edge clamping.
            delta = QPoint(32, area.top() - start.y())
            for kind, location, button, buttons in [
                (QEvent.MouseButtonPress, press, Qt.LeftButton, Qt.LeftButton),
                (QEvent.MouseMove, press + delta, Qt.NoButton, Qt.LeftButton),
                (QEvent.MouseButtonRelease, press + delta, Qt.LeftButton, Qt.NoButton),
            ]:
                event = QMouseEvent(kind, QPointF(card.grip.mapFromGlobal(location)), QPointF(location),
                                    button, buttons, Qt.NoModifier)
                QApplication.sendEvent(card.grip, event)
            self.assertEqual(card.pos(), start + delta)
            passage = word_in(RIVER[:-1] + "; meanwhile the rest of the group returned home.")
            full, excerpt = translate_lookup(passage)
            card.show_result(passage, *full, point, excerpt=excerpt, language="英语", pos="名词")
            self.assertEqual(card.pos(), start + delta)
            card.expand.click()
            self.assertEqual(card.pos(), start + delta)
            self.assertIn(passage.text, card.text.toPlainText())
            # Selecting actual printed letters must not arm dragging.
            cursor = card.text.document().find("bank")
            cursor.setPosition(cursor.selectionStart())
            first = card.text.cursorRect(cursor).center() + QPoint(1, 0)
            cursor.setPosition(cursor.position() + 3)
            last = card.text.cursorRect(cursor).center()
            view = card.text.viewport()
            for kind, location, button, buttons in [
                (QEvent.MouseButtonPress, first, Qt.LeftButton, Qt.LeftButton),
                (QEvent.MouseMove, last, Qt.NoButton, Qt.LeftButton),
                (QEvent.MouseButtonRelease, last, Qt.LeftButton, Qt.NoButton),
            ]:
                event = QMouseEvent(kind, QPointF(location), QPointF(view.mapToGlobal(location)),
                                    button, buttons, Qt.NoModifier)
                QApplication.sendEvent(view, event)
            self.assertIn("an", card.text.textCursor().selectedText())
            self.assertEqual(card.pos(), start + delta)
            card.close()
            card.show_message("本机翻译", "正在读取并翻译…", point)
            self.assertEqual(card.pos(), start)
        finally:
            card.close()

    def test_lookup_context(self):
        for source, word, short, meaning in [
            ("The Code Review plugin shows a pull request’s description, changed files, comments, and checks.",
             "description", "The Code Review plugin shows a pull request’s description", "描述"),
            (RIVER[:-1] + "; meanwhile the rest of the group returned to the village for lunch.",
             "bank", RIVER[:-1], "岸"),
            ("After a long meeting with her colleagues, she deposited her paycheck at the bank before she drove home to make dinner.",
             "bank", "she deposited her paycheck at the bank", "银行"),
        ]:
            with self.subTest(source=source):
                start = source.index(word)
                passage = Passage(source, (start, start + len(word)))
                full, short_result = translate_lookup(passage)
                self.assertIsNotNone(short_result, (full, translate(context_excerpt(passage))))
                excerpt, sentence = short_result
                self.assertEqual(full, translate(passage))
                self.assertIn(meaning, full[1])
                self.assertEqual(excerpt.text, short)
                self.assertEqual(excerpt.word, word)
                self.assertEqual(sentence, translate(excerpt)[2])

        for source in (RIVER, "We would walk home from the bank, unless the flood closed the only road out.",
                       "If it rains during the trip, they will sit on the river bank and wait."):
            self.assertIsNone(context_excerpt(word_in(source)))
        negative = "The team did not rule out infection, although several other possibilities were also under discussion."
        excerpt = context_excerpt(Passage(negative, (negative.index("out"), negative.index("out") + 3)))
        self.assertEqual(excerpt.text, "The team did not rule out infection")
        # The second bank must keep its exact position even after removing the lead-in.
        source = "After they had met at the bank, they walked along the river bank before they went home for dinner."
        start = source.rindex("bank")
        passage = Passage(source, (start, start + 4))
        excerpt = context_excerpt(passage)
        self.assertEqual(excerpt.text, "they walked along the river bank")
        self.assertEqual(excerpt.selection[0], excerpt.text.index("bank"))
        with patch("translation.translate", side_effect=[
            ("句中释义", "岸", "全句"), ("句中释义", "银行", "短句")
        ]):
            self.assertIsNone(translate_lookup(passage)[1])

    def test_context_actions(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            book = Notebook(Path(tmp) / "notebook.sqlite3")
            window = Window(notebook=book)
            card = window.card
            source = RIVER[:-1] + "; meanwhile the rest of the group returned to the village for lunch."
            point = QApplication.primaryScreen().availableGeometry().center()
            try:
                window.submit(point, passage=word_in(source))
                wait_until(card.expand.isVisible)
                self.assertNotIn("meanwhile", card.text.toPlainText())
                card.copy.click()
                short_translation = QApplication.clipboard().text()
                card.save.click()
                card.expand.click()
                self.assertIn(source, card.text.toPlainText())
                self.assertFalse(card.save.isEnabled())
                card.copy.click()
                entry, = book.entries()
                self.assertEqual(entry["context"], source)
                self.assertEqual(entry["position"], source.index("bank"))
                self.assertEqual(entry["translation"], QApplication.clipboard().text())
                self.assertNotEqual(entry["translation"], short_translation)
                card.expand.click()
                self.assertNotIn("meanwhile", card.text.toPlainText())
                card.copy.click()
                self.assertEqual(QApplication.clipboard().text(), short_translation)
                window.demo()
                ticket = window.ticket
                window.on_gesture("dismiss", ticket - 1, None)
                self.assertTrue(card.isVisible())
                self.assertFalse(card.expand.isVisible())
                window.on_gesture("dismiss", ticket, None)
                wait_until(window.pending.done)
                QApplication.processEvents()
                self.assertFalse(card.isVisible())
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

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
            self.assertEqual(card.headword.text(), "bank")
            first = doc.find("bank")
            second = doc.find("bank", first)
            self.assertEqual(first.charFormat().background().style(), Qt.NoBrush)
            self.assertGreater(second.charFormat().fontWeight(), first.charFormat().fontWeight())

            word = "inter" * 110
            card.show_result(Passage(word, (0, len(word))), "单词参考", "很长的释义" * 120, "译文", point)
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
                window.open_reader()
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
                self.assertIn("西班牙语", ui.output.toPlainText())
                self.assertFalse(ui.copy.isEnabled())
                ui.input.setPlainText(RIVER)
                QTest.keyClick(ui.input, Qt.Key_Enter, Qt.ControlModifier)
                wait_until(ui.copy.isEnabled)
                self.assertIn("岸", ui.output.toPlainText())
                window.resize(610, 490)
                wait_until(lambda: ui.output.mapTo(ui, QPoint()).y() > ui.input.mapTo(ui, QPoint()).y())
                window.tabs.setCurrentWidget(window.home)
                self.assertTrue(any(a.text() == "框选翻译" for a in window.tray.contextMenu().actions()))
                self.assertEqual(ui.input.toPlainText(), RIVER)
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
            self.assertEqual(window.wordmark.text(), "WaxTranslate")
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

        profile = TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        window = TestWindow(notebook=Notebook(Path(profile.name) / "words.sqlite"))
        clicks = []

        class Sample(QLabel):
            def mouseReleaseEvent(self, event):
                clicks.append(event.modifiers())
                super().mouseReleaseEvent(event)

        sample = Sample(RIVER)
        sample.setMargin(16)
        # This window represents another app. Keep its OCR sample independent
        # of WaxTranslate's application-wide font rules.
        sample.setStyleSheet("font:20pt 'Segoe UI'; color:black; background:white;")
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
            QTest.qWait(550)
            key(ctrl, False)
            QTest.qWait(100)
            self.assertEqual(window.ticket, previous_ticket, "A long Ctrl hold opened a card")
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
            wait_until(window.card.save.isVisible)
            self.assertEqual(window.card.caption.text(), "句中释义")
            self.assertIn("岸", window.card.text.toPlainText())
            self.assertFalse(window.isVisible(), "A background lookup opened the main window")
            self.assertEqual(window.card.windowType(), Qt.Tool)
            # Real mouse presses. The inside action works; the first outside
            # click dismisses the card and still reaches the original window.
            # A layered window publishes its input surface after painting.
            # Also let the absolute mouse move reach the hardware input queue
            # before pressing; mouse_event can return before that move arrives.
            user.WindowFromPhysicalPoint.argtypes = (wintypes.POINT,)
            user.WindowFromPhysicalPoint.restype = wintypes.HWND
            user.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
            user.GetAncestor.restype = wintypes.HWND
            def native_target():
                cursor = wintypes.POINT()
                user.GetPhysicalCursorPos(ctypes.byref(cursor))
                return user.GetAncestor(user.WindowFromPhysicalPoint(cursor), 2)

            card = window.card
            before_drag = card.pos()
            grip = card.grip.mapToGlobal(card.grip.rect().center())
            dy = -45 if before_drag.y() - area.top() > 60 else 45
            move_cursor(grip)
            wait_until(lambda: native_target() == int(card.winId()) and QApplication.widgetAt(QCursor.pos()) is card.grip)
            user.mouse_event(2, 0, 0, 0, 0)
            wait_until(lambda: card.press_position is not None)
            move_cursor(grip + QPoint(0, dy))
            wait_until(lambda: abs(card.y() - before_drag.y()) > 20)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: card.press_position is None)
            self.assertTrue(card.isVisible())
            with patch.object(window.player, "play") as speak:
                menu = card.listen.menu()
                menu.popup(card.listen.mapToGlobal(card.listen.rect().bottomLeft()))
                wait_until(menu.isVisible)
                slow = menu.mapToGlobal(menu.actionGeometry(card.listen.slow).center())
                move_cursor(slow)
                wait_until(lambda: native_target() == int(menu.winId()))
                user.mouse_event(2, 0, 0, 0, 0)
                user.mouse_event(4, 0, 0, 0, 0)
                wait_until(lambda: speak.called)
                speak.assert_called_once_with(card.listen, "bank", True, "en")
                self.assertTrue(card.isVisible())
            menu = card.more.menu()
            menu.popup(card.more.mapToGlobal(card.more.rect().bottomLeft()))
            wait_until(menu.isVisible)
            copy_action = next(a for a in menu.actions() if a.text() == card.copy.accessibleName())
            move_cursor(menu.mapToGlobal(menu.actionGeometry(copy_action).center()))
            wait_until(lambda: native_target() == int(menu.winId()))
            user.mouse_event(2, 0, 0, 0, 0)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: card.copy.toolTip() == "已复制")
            button = window.card.pin
            center = button.mapToGlobal(button.rect().center())
            move_cursor(center)
            wait_until(lambda: native_target() == int(window.card.winId())
                       and QApplication.widgetAt(QCursor.pos()) is button)
            user.mouse_event(2, 0, 0, 0, 0)
            wait_until(button.isDown)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(button.isChecked)
            self.assertTrue(window.card.isVisible())
            outside = sample.mapToGlobal(QPoint(6, sample.height() // 2))
            self.assertFalse(window.card.geometry().contains(outside))
            move_cursor(outside)
            wait_until(lambda: QApplication.widgetAt(QCursor.pos()) is sample and native_target() == int(sample.winId()))
            user.mouse_event(2, 0, 0, 0, 0)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: len(clicks) == 2)
            self.assertTrue(card.isVisible())
            button.click()
            user.mouse_event(2, 0, 0, 0, 0)
            user.mouse_event(4, 0, 0, 0, 0)
            wait_until(lambda: not card.isVisible() and len(clicks) == 3)
            self.assertEqual(clicks[-1], Qt.NoModifier)
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
            wait_until(lambda: window.card.caption.text() in ("选区译文", "需要处理"))
            self.assertEqual(window.card.caption.text(), "选区译文", window.card.text.toPlainText())
            self.assertIn("河岸", window.card.text.toPlainText())
            self.assertEqual(len(clicks), 3, "Capture drag reached the foreground window")
            window.trigger.setCurrentIndex(window.trigger.findData("right"))
            wait_until(lambda: window.active_mode == "right")
            sample.setText("MVP validates our product hypothesis.")
            sample.repaint()
            focus_sample()
            # The actual pointer is outside the first glyph's left edge.
            move_cursor(sample.mapToGlobal(QPoint(sample.margin() - 1, sample.height() // 2)))
            count = sum(action == "lookup" for action, _, _ in gestures)
            key(ctrl, True)
            key(ctrl, False)
            right_ctrl = 0xA3
            # Right Ctrl is an extended key. Preserve that bit on press and release.
            user.keybd_event(right_ctrl, 0x1D, 1, 0)
            user.keybd_event(right_ctrl, 0x1D, 3, 0)
            wait_until(lambda: window.card.save.isVisible())
            self.assertEqual(window.saved_result[0].word, "MVP")
            self.assertIn("最小可行产品", window.saved_result[1][1])
            self.assertEqual(sum(action == "lookup" for action, _, _ in gestures), count + 1)
            # Completed screen lookups should appear when returning from the tray.
            window.card.close()
            sample.hide()
            window.open_home()
            self.assertTrue(QTest.qWaitForWindowExposed(window))
            wait_until(lambda: window.isActiveWindow() and window.home.values["次取词"].text() == "2")
            self.assertEqual([window.home.table.item(i, 0).text() for i in range(2)], ["MVP", "bank"])
            self.assertIn("最小可行产品", window.home.table.item(0, 1).text())
            window.trigger.setCurrentIndex(window.trigger.findData("off"))
            wait_until(lambda: window.active_mode == "off")
            ticket = window.ticket
            key(ctrl, True)
            key(ctrl, False)
            user.keybd_event(right_ctrl, 0x1D, 1, 0)
            user.keybd_event(right_ctrl, 0x1D, 3, 0)
            QTest.qWait(160)
            self.assertEqual(window.ticket, ticket)
            self.assertFalse(window.card.isVisible())
            window.demo()
            window.card.close()
            wait_until(lambda: window.pending.done())
            app.processEvents()
            self.assertFalse(window.card.isVisible(), "A dismissed request reopened its card")
        except AssertionError as error:
            future = window.pending
            pos = QCursor.pos()
            native = native_target() if "native_target" in locals() else None
            self.fail(f"{error}; recent gestures={gestures[-8:]}, ticket={window.ticket}, "
                      f"cursor={pos.toTuple()}, widget={QApplication.widgetAt(pos)}, native target={native}, "
                      f"card hwnd={int(window.card.winId())}, bounds={window.card.geometry()}, "
                      f"card=({window.card.isVisible()}, {window.card.caption.text()!r}), "
                      f"worker={future}, overlay={window.overlay is not None}")
        finally:
            window.shutdown()
            window.hide()
            window.deleteLater()
            if user.GetAsyncKeyState(1) & 0x8000:
                user.mouse_event(4, 0, 0, 0, 0)
            if user.GetAsyncKeyState(ctrl) & 0x8000:
                key(ctrl, False)
            sample.close()
            QCursor.setPos(previous)


def load_tests(loader, tests, pattern):
    # Run the repository fixtures against the *packaged* application modules
    # when invoked by the embedded interpreter on the independent runner.
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


class DesktopResult(unittest.TextTestResult):
    def startTest(self, test):
        # A native input stall can bypass wait_until. Time each test, since
        # cold-loading nine models can take longer than one gesture timeout.
        super().startTest(test)
        faulthandler.dump_traceback_later(75, exit=True)

    def stopTest(self, test):
        faulthandler.cancel_dump_traceback_later()
        super().stopTest(test)


class DesktopRunner(unittest.TextTestRunner):
    resultclass = DesktopResult


if __name__ == "__main__":
    app = QApplication([])
    if not DESKTOP:
        # Qt's offscreen plugin has no system font database on Windows.
        font = os.path.join(os.environ["WINDIR"], "Fonts", "segoeui.ttf")
        if QFontDatabase.addApplicationFont(font) == -1:
            raise RuntimeError(f"Cannot load Windows test font: {font}")
    apply_theme(app)
    # A developer's lookup count, notebook and preferences are personal data.
    # The model installer paths are already resolved, so source runs can still use the real models.
    with TemporaryDirectory() as profile, patch.dict(os.environ, {"LOCALAPPDATA": profile}):
        unittest.main(testRunner=DesktopRunner if DESKTOP else None)
