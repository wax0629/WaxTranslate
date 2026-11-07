import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from pathlib import Path
import sys

from PySide6.QtCore import QPoint, QPointF, QProcess, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QBoxLayout, QButtonGroup, QFrame, QHBoxLayout, QMenu, QPushButton,
                               QStackedWidget, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget)

from gestures import LOOKUP_HINT, REGION_HINT
from notebook import Notebook
from popup import Card
from library import Library
from reader import Passage, recognize
from theme import APP_NAME, apply_theme, label, nav_icon
from translation import translate_lookup
from workspace import TextWorkspace


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
    result, excerpt = translate_lookup(passage)
    return passage, result, excerpt


class Window(QWidget):
    finished = Signal(int, object, object)

    def __init__(self, notebook=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setObjectName("desk")
        self.card = Card()
        self.card.dismissed.connect(self.invalidate)
        self.card.presented.connect(self.watch_card)
        self.card.save_requested.connect(self.save_word)
        self.saved_result = None
        self.notebook = notebook or Notebook()
        self.overlay = None
        self.ticket = 0
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.finished.connect(self.show_result)
        self.compact = None
        outer = self.shell = QBoxLayout(QBoxLayout.LeftToRight, self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = self.sidebar = QFrame(objectName="sidebar")
        outer.addWidget(sidebar)
        rail = self.rail = QBoxLayout(QBoxLayout.TopToBottom, sidebar)
        rail.setContentsMargins(12, 24, 12, 17)
        rail.setSpacing(5)
        brand = QHBoxLayout()
        brand.setContentsMargins(2, 0, 0, 0)
        avatar = QSvgWidget(str(Path(__file__).resolve().parents[1] / "Assets/Brand/barrette.svg"))
        avatar.setObjectName("brandMark")
        avatar.setAccessibleName(APP_NAME)
        avatar.setFixedSize(31, 31)
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
        self.engine_label = label("本地英译中", "meta")
        rail.addWidget(self.engine_label)

        home = QWidget(objectName="home")
        layout = QVBoxLayout(home)
        layout.setContentsMargins(27, 22, 27, 20)
        layout.setSpacing(12)
        self.tabs.addWidget(home)
        self.library = Library(self.notebook)
        self.tabs.addWidget(self.library)
        layout.addWidget(label("文本翻译", "heading"))
        self.workspace = TextWorkspace(self.pool)
        layout.addWidget(self.workspace, 1)
        quick = QHBoxLayout()
        self.hint_button = QPushButton("屏幕翻译")
        self.hint_button.setIconSize(QSize(11, 11))
        self.hint_button.setProperty("role", "disclosure")
        self.hint_button.setCheckable(True)
        self.hint_button.setToolTip("显示或收起取词与框选手势")
        quick.addWidget(self.hint_button)
        quick.addStretch()
        example = QPushButton("取词示例")
        example.setProperty("role", "quiet")
        example.clicked.connect(self.demo)
        quick.addWidget(example)
        region = QPushButton("开始框选")
        region.setProperty("role", "quiet")
        region.clicked.connect(lambda: self.begin(True))
        quick.addWidget(region)
        layout.addLayout(quick)
        self.hints = QWidget()
        hints = QVBoxLayout(self.hints)
        hints.setContentsMargins(0, 0, 0, 0)
        hints.setSpacing(7)
        for description, keys in (("指向单词", LOOKUP_HINT), ("拖选一段文字", REGION_HINT)):
            row = QHBoxLayout()
            row.addWidget(label(description, "meta"))
            row.addStretch()
            row.addWidget(label(keys, "key"))
            hints.addLayout(row)
        layout.addWidget(self.hints)
        self.hint_button.toggled.connect(self.show_hints)
        self.hint_button.setChecked(True)
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
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(872, area.width() - 24), min(535, area.height() - 48))
        self.workspace.input.setFocus()
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = event.size().width() < 700
        if self.compact == compact:
            return
        self.compact = compact
        self.shell.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self.rail.setDirection(QBoxLayout.LeftToRight if compact else QBoxLayout.TopToBottom)
        self.sidebar.setMinimumSize(0, 0)
        self.sidebar.setMaximumSize(16777215, 16777215)
        if compact:
            self.sidebar.setFixedHeight(56)
            self.rail.setContentsMargins(13, 6, 13, 6)
        else:
            self.sidebar.setFixedWidth(172)
            self.rail.setContentsMargins(12, 24, 12, 17)
        self.engine_label.setVisible(not compact)
        self.hint_button.setChecked(not compact)
        self.sidebar.setProperty("compact", compact)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)

    def show_hints(self, expanded):
        self.hints.setVisible(expanded)
        arrow = QStyle.SP_ArrowDown if expanded else QStyle.SP_ArrowRight
        self.hint_button.setIcon(self.style().standardIcon(arrow))

    def open_home(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_library(self):
        self.tabs.setCurrentWidget(self.library)
        self.open_home()
        if self.library.review.isEnabled():
            self.library.review.setFocus()

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
        self.card.dismiss_on_deactivate = True
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
                self.card.dismiss_on_deactivate = False
                self.watch_card()
            elif action == "error":
                self.gesture_failed(f"Windows 错误 {origin}")
            else:
                self.on_gesture(action, origin, end)

    def watch_card(self):
        if self.gesture_ready and not self.stopping:
            hwnd = int(self.card.winId()) if self.card.isVisible() else 0
            self.gestures.write((json.dumps((self.ticket, hwnd)) + "\n").encode("ascii"))

    def on_gesture(self, action, origin, end):
        if action == "dismiss":
            if origin == self.ticket and self.card.isVisible():
                self.card.close()
            return
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
        self.watch_card()
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
            self.card.show_message("截图失败", "请返回普通桌面后重试。", point)
            return
        logical = screen.size()
        logical.setHeight(band)
        hit = image_point(QPointF(local.x(), local.y() - top), logical, shot.size())
        self.submit(point, image=shot.toImage(), hit=hit)

    def open_selection(self, screen, point, from_ctrl=False):
        shot = screen.grabWindow(0)
        if shot.isNull():
            self.card.show_message("截图失败", "请返回普通桌面后重试。", point)
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
        self.card.show_message("本机英译中", "正在读取并翻译…", point)
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
            passage, result, excerpt = job.result()
        except Exception as error:
            self.card.show_message("需要处理", str(error), point)
            return
        self.saved_result = (passage, result) if passage.selection else None
        self.card.show_result(passage, *result, point, excerpt=excerpt)

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
        self.workspace.reset_result()
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
