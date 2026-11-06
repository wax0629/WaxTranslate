import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
import sqlite3
from pathlib import Path
import sys

from PySide6.QtCore import QPoint, QPointF, QProcess, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QPlainTextEdit, QStackedWidget, QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget)

from gestures import LOOKUP_HINT, REGION_HINT
from notebook import Notebook
from library import Library
from reader import Passage, recognize
from theme import APP_NAME, apply_theme, label, nav_icon
from translation import translate


def plain(text):
    return escape(text).replace("\n", "<br>")


def image_point(point, logical_size, image_size):
    return QPointF(point.x() * image_size.width() / logical_size.width(),
                   point.y() * image_size.height() / logical_size.height())


def image_rect(rect, logical_size, image_size):
    top = image_point(rect.topLeft(), logical_size, image_size).toPoint()
    end = image_point(QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                      logical_size, image_size).toPoint()
    return QRect(top.x(), top.y(), end.x() - top.x(), end.y() - top.y())


def app_icon():
    return QIcon(str(Path(__file__).with_name("waxtranslate.ico")))


class Card(QWidget):
    dismissed = Signal()
    save_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"{APP_NAME} · 翻译结果")
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        shell = QFrame(objectName="cardShell")
        outer.addWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(18, 10, 14, 13)
        layout.setSpacing(4)
        bar = QHBoxLayout()
        self.caption = label("", "meta")
        self.caption.setWordWrap(True)
        bar.addWidget(self.caption)
        bar.addStretch()
        close = QPushButton("×")
        close.setProperty("role", "close")
        close.setAccessibleName("关闭翻译结果")
        close.setFixedSize(26, 26)
        close.setToolTip("关闭浮窗 (Esc)")
        close.clicked.connect(self.close)
        bar.addWidget(close)
        layout.addLayout(bar)
        self.text = QTextBrowser(objectName="result")
        self.text.document().setDocumentMargin(0)
        self.text.setFrameShape(QTextBrowser.NoFrame)
        self.text.setOpenLinks(False)
        layout.addWidget(self.text)
        self.divider = QFrame(objectName="hairline")
        self.divider.setFixedHeight(1)
        layout.addWidget(self.divider)
        buttons = QHBoxLayout()
        self.copy = QPushButton("复制译文")
        self.save = QPushButton("收藏生词")
        self.copy.setProperty("role", "quiet")
        buttons.addWidget(self.copy)
        buttons.addStretch()
        buttons.addWidget(self.save)
        layout.addLayout(buttons)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.translation))
        self.save.clicked.connect(self.save_requested)
        self.translation = ""

    def present(self, caption, content, point, translation="", can_save=False):
        self.translation = translation
        self.divider.setVisible(bool(translation))
        self.copy.setVisible(bool(translation))
        self.save.setVisible(can_save)
        self.save.setText("收藏生词")
        self.save.setEnabled(True)
        self.caption.setText(caption)
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(395, area.width())
        self.text.setHtml(content)
        self.text.verticalScrollBar().setValue(0)
        self.text.document().setTextWidth(width - 48)
        height = min(area.height(), max(106, min(400, int(self.text.document().size().height()) + (112 if translation else 76))))
        self.resize(width, height)
        x = max(area.left(), min(point.x() + 16, area.right() - width + 1))
        y = point.y() + 22
        if y + height > area.bottom() + 1:
            y = max(area.top(), point.y() - height - 12)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.dismissed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class Selection(QWidget):
    selected = Signal(object, object)

    def __init__(self, screen, screenshot, from_ctrl=False):
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if from_ctrl:
            flags |= Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
        super().__init__(None, flags)
        self.from_ctrl = from_ctrl
        self.setAttribute(Qt.WA_ShowWithoutActivating, from_ctrl)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("框选英文 · Esc 取消")
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.screenshot = screenshot
        self.start = None
        self.selection = QRect()
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.screenshot)
        p.fillRect(self.rect(), QColor(12, 24, 23, 88))
        if self.start is not None:
            p.save()
            p.setClipRect(self.selection)
            p.drawPixmap(self.rect(), self.screenshot)
            p.restore()
            p.setPen(QPen(QColor("#9af7c8"), 2))
            p.drawRect(self.selection.adjusted(0, 0, -1, -1))
        else:
            p.fillRect(16, 16, 234, 38, QColor("#193b33"))
            p.setPen(Qt.white)
            p.drawText(QRect(16, 16, 234, 38), Qt.AlignCenter, "拖动框选英文  ·  Esc 取消")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = event.position().toPoint()
            self.selection = QRect(self.start, self.start)
            self.update()

    def mouseMoveEvent(self, event):
        self.extend_to(event.position().toPoint())

    def extend_to(self, point):
        if self.start is not None:
            self.selection = QRect(self.start, point).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.start is None:
            return
        self.finish_at(event.position().toPoint())

    def finish_at(self, point):
        self.extend_to(point)
        if self.selection.width() >= 4 and self.selection.height() >= 4:
            # Selection is in logical coordinates; OCR operates on image pixels.
            r = self.selection
            crop = image_rect(r, self.size(), self.screenshot.size())
            self.hide()
            self.selected.emit(self.screenshot.copy(crop).toImage(), self.mapToGlobal(r.bottomRight()))
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


def analyze(image, point, passage):
    if passage is None:
        passage = asyncio.run(recognize(image, point))
    return passage, translate(passage)


class Window(QWidget):
    finished = Signal(int, object, object)

    def __init__(self, notebook=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setObjectName("desk")
        self.card = Card()
        self.card.dismissed.connect(self.invalidate)
        self.card.save_requested.connect(self.save_word)
        self.saved_result = None
        self.notebook = notebook or Notebook()
        self.overlay = None
        self.ticket = 0
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.finished.connect(self.show_result)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(172)
        outer.addWidget(sidebar)
        rail = QVBoxLayout(sidebar)
        rail.setContentsMargins(12, 24, 12, 17)
        rail.setSpacing(5)
        brand = QHBoxLayout()
        brand.setContentsMargins(2, 0, 0, 0)
        avatar = QLabel()
        avatar.setPixmap(app_icon().pixmap(31, 31))
        brand.addWidget(avatar)
        brand.addWidget(label(APP_NAME, "brand"))
        brand.addStretch()
        rail.addLayout(brand)
        rail.addSpacing(26)
        self.tabs = QStackedWidget()
        outer.addWidget(self.tabs, 1)
        group = QButtonGroup(self)
        for index, name in enumerate(("翻译", "生词本")):
            nav = QPushButton(nav_icon(book=bool(index)), name)
            nav.setCheckable(True)
            nav.setProperty("role", "nav")
            nav.setIconSize(QSize(21, 21))
            group.addButton(nav, index)
            rail.addWidget(nav)
        group.idClicked.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(lambda index: group.button(index).setChecked(True))
        rail.addStretch()
        rail.addWidget(label("本地英译中", "meta"))

        home = QWidget(objectName="home")
        layout = QVBoxLayout(home)
        layout.setContentsMargins(27, 22, 27, 20)
        layout.setSpacing(12)
        self.tabs.addWidget(home)
        self.library = Library(self.notebook)
        self.tabs.addWidget(self.library)
        layout.addWidget(label("文本翻译", "heading"))
        editor = QFrame(objectName="editor")
        box = QVBoxLayout(editor)
        box.setContentsMargins(16, 13, 16, 12)
        box.setSpacing(7)
        box.addWidget(label("英语   →   简体中文", "meta"))
        self.input = QPlainTextEdit(objectName="input")
        self.input.setPlaceholderText("输入或粘贴英文…")
        self.input.setAccessibleName("待翻译的英文")
        self.input.setFocus()
        box.addWidget(self.input, 1)
        actions = QHBoxLayout()
        example = QPushButton("试译示例")
        example.setProperty("role", "quiet")
        example.clicked.connect(self.demo)
        actions.addWidget(example)
        actions.addStretch()
        self.submit_text = QPushButton("翻译")
        self.submit_text.setProperty("role", "primary")
        self.submit_text.setToolTip("翻译文本 (Ctrl+Enter)")
        self.submit_text.setEnabled(False)
        self.input.textChanged.connect(lambda: self.submit_text.setEnabled(bool(self.input.toPlainText().strip())))
        self.submit_text.clicked.connect(self.translate_text)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.input)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.translate_text)
        actions.addWidget(self.submit_text)
        box.addLayout(actions)
        layout.addWidget(editor, 1)
        quick = QHBoxLayout()
        quick.addWidget(label("屏幕取词", "subhead"))
        quick.addStretch()
        region = QPushButton("开始框选")
        region.setProperty("role", "quiet")
        region.clicked.connect(lambda: self.begin(True))
        quick.addWidget(region)
        layout.addLayout(quick)
        for description, keys in (("指向单词", LOOKUP_HINT), ("拖选一段文字", REGION_HINT)):
            row = QHBoxLayout()
            row.addWidget(label(description, "meta"))
            row.addStretch()
            row.addWidget(label(keys, "key"))
            layout.addLayout(row)
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.tray.setToolTip(f"{APP_NAME} · {LOOKUP_HINT} 取词")
        menu = QMenu(self)
        menu.addAction(f"打开 {APP_NAME}", self.open_home)
        menu.addAction("生词本", self.open_library)
        menu.addAction("框选翻译", lambda: self.begin(True))
        menu.addSeparator()
        menu.addAction("退出", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        if self.tray.isSystemTrayAvailable():
            self.tray.show()
        self.gesture_warning = label("", "warning")
        self.gesture_warning.setWordWrap(True)
        layout.addWidget(self.gesture_warning)
        self.gesture_warning.hide()
        self.gesture_ready = False
        self.stopping = False
        self.gestures = QProcess(self)
        self.gestures.readyReadStandardOutput.connect(self.read_gestures)
        self.gestures.errorOccurred.connect(lambda error: self.gesture_failed(self.gestures.errorString()))
        self.gestures.finished.connect(lambda: self.gesture_failed("监听进程已退出"))
        self.gestures.start(str(Path(sys.executable).with_name("pythonw.exe")),
                            ["-u", str(Path(__file__).with_name("gestures.py").resolve())])
        self.resize(720, 462)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def open_home(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_library(self):
        self.tabs.setCurrentWidget(self.library)
        self.open_home()
        if self.library.review.isEnabled():
            self.library.review.setFocus()

    def translate_text(self):
        text = self.input.toPlainText().strip()
        if text:
            self.invalidate()
            self.submit(QCursor.pos(), passage=Passage(text))

    def save_word(self):
        if self.saved_result is None:
            return
        try:
            self.notebook.save(*self.saved_result)
        except (sqlite3.Error, OSError) as error:
            self.card.caption.setText(f"收藏失败：{error}")
            return
        self.card.save.setText("已收藏")
        self.card.save.setEnabled(False)
        if self.library.isVisible():
            self.library.refresh()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.open_home()

    def gesture_failed(self, reason):
        self.gesture_ready = False
        if not self.stopping and self.gesture_warning.isHidden():
            self.gesture_warning.setText(f"无法监听左 Ctrl（{reason}）。可点击「框选英文」。")
            self.gesture_warning.show()
            if self.overlay is not None and self.overlay.from_ctrl:
                self.overlay.close()

    def read_gestures(self):
        while self.gestures.canReadLine() and not self.stopping:
            action, origin, end = json.loads(bytes(self.gestures.readLine()))
            if action == "ready":
                self.gesture_ready = True
            elif action == "error":
                self.gesture_failed(f"Windows 错误 {origin}")
            else:
                self.on_gesture(action, origin, end)

    def on_gesture(self, action, origin, end):
        if action in ("lookup", "start"):
            native = QPoint(*origin)
            # On Windows Qt keeps each screen's native origin but scales its size.
            for screen in QApplication.screens():
                geometry = screen.geometry()
                ratio = screen.devicePixelRatio()
                if QRect(geometry.topLeft(), geometry.size() * ratio).contains(native):
                    point = geometry.topLeft() + (native - geometry.topLeft()) / ratio
                    break
            else:
                return
            if action == "lookup":
                self.begin(False, point)
                return
            self.invalidate()
            if not self.open_selection(screen, point, from_ctrl=True):
                return
            self.overlay.start = point - geometry.topLeft()
        overlay = self.overlay
        if overlay is None or not overlay.from_ctrl:
            return
        if action == "cancel":
            overlay.close()
            return
        screen = overlay.screen()
        local = (QPoint(*end) - screen.geometry().topLeft()) / screen.devicePixelRatio()
        if action == "finish":
            overlay.finish_at(local)
        else:
            overlay.extend_to(local)

    def invalidate(self):
        self.ticket += 1
        self.saved_result = None
        if self.pending is not None:
            self.pending.cancel()
        self.card.hide()
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None

    def demo(self):
        self.invalidate()
        text = "They sat on the river bank and watched the water."
        start = text.index("bank")
        self.submit(QCursor.pos(), passage=Passage(text, (start, start + 4)))

    def begin(self, region, point=None):
        if point is None:
            point = QCursor.pos()
        self.invalidate()
        ticket = self.ticket
        QTimer.singleShot(80, lambda: self.capture(ticket, point, region))

    def capture(self, ticket, point, region):
        if ticket != self.ticket:
            return
        screen = QApplication.screenAt(point)
        if not screen:
            return
        local = point - screen.geometry().topLeft()
        height = screen.size().height()
        if region:
            self.open_selection(screen, point)
            return
        band = max(1, height // 4)
        top = max(0, min(local.y() - band // 2, height - band))
        shot = screen.grabWindow(0, 0, top, screen.size().width(), band)
        if shot.isNull():
            self.card.present("截图失败", "请返回普通桌面后重试。", point)
            return
        logical = screen.size()
        logical.setHeight(band)
        hit = image_point(QPointF(local.x(), local.y() - top), logical, shot.size())
        self.submit(point, image=shot.toImage(), hit=hit)

    def open_selection(self, screen, point, from_ctrl=False):
        shot = screen.grabWindow(0)
        if shot.isNull():
            self.card.present("截图失败", "请返回普通桌面后重试。", point)
            return False
        overlay = Selection(screen, shot, from_ctrl)
        self.overlay = overlay
        overlay.destroyed.connect(lambda: self.clear_overlay(overlay))
        overlay.selected.connect(lambda image, pos: self.submit(pos, image=image))
        overlay.show()
        overlay.raise_()
        if not from_ctrl:
            overlay.activateWindow()
        return True

    def clear_overlay(self, closed):
        if self.overlay is closed:
            self.overlay = None

    def submit(self, point, image=None, hit=None, passage=None):
        ticket = self.ticket
        self.card.present("本机英译中", "正在读取并翻译…", point)
        future = self.pool.submit(analyze, image, hit, passage)
        self.pending = future

        def completed(job):
            if not job.cancelled():
                self.finished.emit(ticket, point, job)
        future.add_done_callback(completed)

    def show_result(self, ticket, point, job):
        if ticket != self.ticket:
            return
        try:
            passage, (origin, gloss, sentence) = job.result()
        except Exception as error:
            self.card.present("需要处理", plain(str(error)), point)
            return
        content = ""
        if passage.word:
            content += f"<p style='margin:2px 0 6px; font: bold 25pt Georgia; color:#24231f'>{plain(passage.word)}</p>"
        content += f"<p style='margin:0 0 12px;font-size:14pt;color:#272721'>{plain(gloss)}</p>"
        context = plain(passage.text)
        if passage.selection:
            a, b = passage.selection
            context = plain(passage.text[:a]) + "<b>" + plain(passage.word) + "</b>" + plain(passage.text[b:])
        content += f"<p style='margin:6px 0 3px;color:#4b4c45;font-size:11pt'>{context}</p>"
        if sentence:
            content += f"<p style='margin:2px 0 4px;color:#63635d;font-size:10pt'>{plain(sentence)}</p>"
        self.saved_result = (passage, (origin, gloss, sentence)) if passage.selection else None
        self.card.present(origin, content, point, translation=sentence or gloss, can_save=bool(passage.selection))

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            QApplication.quit()

    def shutdown(self):
        self.stopping = True
        self.gestures.closeWriteChannel()
        if self.gestures.state() != QProcess.NotRunning and not self.gestures.waitForFinished(2000):
            self.gestures.kill()
            self.gestures.waitForFinished(2000)
        self.invalidate()
        self.tray.hide()
        self.pool.shutdown(wait=True, cancel_futures=True)


def main():
    from instance import activation_event
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WaxTranslate.Desktop")
    app = QApplication(sys.argv)
    activation = activation_event(app)
    if activation is None:
        return 0
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    window = Window()
    activation.activated.connect(window.open_home)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
