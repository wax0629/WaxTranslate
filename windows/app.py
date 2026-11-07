import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from pathlib import Path
import sys
import time

from PySide6.QtCore import QEvent, QPoint, QPointF, QProcess, QRect, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QIcon, QPainter, QPen
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLayout,
                               QMenu, QPushButton, QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from notebook import Notebook
from home import HOME_EXAMPLE, HomePage
from lookup import UNKNOWN, explain, reference_word, sentence_translation
from online_terms import search_entities
from popup import Card
from speech import SpeechPlayer
from library import Library
from reader import Passage, recognize
from settings_page import SettingsPage
from startup import LoginStartup
from theme import APP_NAME, apply_theme, label, ui_icon
from languages import UnsupportedLanguage
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
        self.setWindowTitle("框选原文 · Esc 取消")
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.screenshot = screenshot
        self.start = None
        self.selection = QRect()
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.screenshot)
        p.fillRect(self.rect(), QColor(18, 31, 26, 88))
        if self.start is not None:
            p.save()
            p.setClipRect(self.selection)
            p.drawPixmap(self.rect(), self.screenshot)
            p.restore()
            p.setPen(QPen(QColor("#ffb895"), 2))
            p.drawRect(self.selection.adjusted(0, 0, -1, -1))
        else:
            p.fillRect(16, 16, 234, 38, QColor("#20322a"))
            p.setPen(Qt.white)
            p.drawText(QRect(16, 16, 234, 38), Qt.AlignCenter, "拖动框选原文  ·  Esc 取消")
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


def analyze(image, point, passage, source_code=""):
    if passage is None:
        passage = asyncio.run(recognize(image, point, source_code))
    passage.source_code = passage.source_code or source_code
    return passage, *explain(passage)


def online_meanings(word):
    entries = []
    for identity, description, language in search_entities(reference_word(word)):
        if language == "en":
            description = sentence_translation(description).rstrip("。") or description
        entries.append((identity, description))
    return entries


class Window(QWidget):
    finished = Signal(int, object, object)
    online_finished = Signal(int, object)
    stats_ready = Signal(object, object, object)

    def __init__(self, notebook=None, login_startup=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setObjectName("desk")
        self.setAttribute(Qt.WA_StyledBackground)
        self.player = SpeechPlayer(self)
        self.card = Card(self.player)
        self.card.dismissed.connect(self.invalidate)
        self.card.presented.connect(self.watch_card)
        self.card.save_requested.connect(self.save_word)
        self.card.online.clicked.connect(self.search_online)
        self.online_finished.connect(self.show_online)
        self.search_context = None
        self.online_job = None
        self.online_pool = ThreadPoolExecutor(max_workers=2)
        self.saved_result = None
        self.reading_from_editor = False
        self.notebook = notebook or Notebook()
        self.settings = QSettings(str(self.notebook.path.with_name("preferences.ini")), QSettings.IniFormat)
        self.login_startup = login_startup if login_startup is not None else LoginStartup()
        self.overlay = None
        self.ticket = 0
        self.stopping = False
        # A paragraph translation can continue while the reader looks up a word.
        self.pool = ThreadPoolExecutor(max_workers=2)
        # Serialize dashboard reads and writes without delaying the reading card.
        self.stats_pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.finished.connect(self.show_result)
        self.compact = None
        outer = self.shell = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = self.sidebar = QFrame(objectName="sidebar")
        outer.addWidget(sidebar)
        rail = self.rail = QHBoxLayout(sidebar)
        rail.setSpacing(5)
        lockup = self.brand_lockup = QWidget()
        lockup.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        brand = QHBoxLayout(lockup)
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(8)
        badge = QFrame(objectName="brandBadge")
        badge.setFixedSize(32, 32)
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(4, 4, 4, 4)
        avatar = QSvgWidget(str(Path(__file__).resolve().parents[1] / "Assets/Brand/barrette.svg"))
        avatar.setObjectName("brandMark")
        avatar.setAccessibleName(APP_NAME)
        badge_layout.addWidget(avatar)
        brand.addWidget(badge)
        self.wordmark = label(APP_NAME + "<span style='color:#bd5036'>.</span>", "brand")
        self.wordmark.setAccessibleName(APP_NAME)
        self.wordmark.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        brand.addWidget(self.wordmark)
        rail.addWidget(lockup)
        rail.addStretch()
        self.tabs = QStackedWidget()
        outer.addWidget(self.tabs, 1)
        group = QButtonGroup(self)
        for index, name in enumerate(("首页", "阅读", "生词本", "设置")):
            if index == 3:
                rail.addStretch()
                self.engine_dot = QFrame(objectName="engineDot")
                self.engine_dot.setFixedSize(6, 6)
                rail.addWidget(self.engine_dot)
                self.engine_label = label("本地翻译", "engine")
                self.engine_label.setContentsMargins(0, 0, 15, 0)
                rail.addWidget(self.engine_label)
            nav = QPushButton(name)
            if index == 3:
                nav.setIcon(ui_icon("settings"))
            nav.setCheckable(True)
            nav.setProperty("role", "nav")
            nav.setCursor(Qt.PointingHandCursor)
            nav.setIconSize(QSize(17, 17))
            group.addButton(nav, index)
            rail.addWidget(nav)
        group.idClicked.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(lambda index: group.button(index).setChecked(True))

        self.home = HomePage()
        self.tabs.addWidget(self.home)
        self.home.demo_requested.connect(self.try_home_word)
        self.home.region_requested.connect(lambda: self.begin(True))
        self.home.reader_requested.connect(self.open_reader)
        self.home.settings_requested.connect(self.open_gesture_settings)
        self.home.stats_requested.connect(self.refresh_home)
        self.stats_ready.connect(self.home.set_stats)
        self.reader_page = QWidget(objectName="readingPage")
        layout = self.reading_layout = QVBoxLayout(self.reader_page)
        layout.setSpacing(17)
        self.tabs.addWidget(self.reader_page)
        self.library = Library(self.notebook, self.player)
        self.home.library_requested.connect(self.open_library)
        self.library.reader_requested.connect(self.open_reader)
        self.tabs.addWidget(self.library)
        self.preferences = SettingsPage()
        self.tabs.addWidget(self.preferences)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.trigger = self.preferences.trigger
        self.auto_online = self.preferences.auto_online
        for control, key, default in ((self.trigger, "gesture", "left"),
                                      (self.preferences.source_language, "sourceLanguage", ""),
                                      (self.preferences.close_behavior, "closeBehavior", "tray")):
            control.setCurrentIndex(max(0, control.findData(self.settings.value(key, default))))
        self.auto_online.setChecked(self.settings.value("onlineTerms", True, type=bool))
        self.auto_online.toggled.connect(lambda checked: self.save_preference("onlineTerms", checked))
        self.preferences.close_behavior.currentIndexChanged.connect(
            lambda: self.save_preference("closeBehavior", self.preferences.close_behavior.currentData()))
        self.preferences.startup.toggled.connect(self.set_startup)
        self.preferences.repair_startup.clicked.connect(lambda: self.set_startup(True))
        self.preferences.remove_startup.clicked.connect(lambda: self.set_startup(False))
        self.preferences.retry_startup.clicked.connect(self.refresh_startup)
        self.preferences.system_startup.clicked.connect(self.open_system_startup)
        layout.addWidget(label("阅读与翻译", "heading"))
        self.workspace = TextWorkspace(self.pool)
        self.workspace.set_source_language(self.preferences.source_language.currentData())
        self.preferences.source_language.currentIndexChanged.connect(self.change_language)
        self.workspace.input.lookup_requested.connect(self.lookup_text)
        self.workspace.input.textChanged.connect(self.editor_changed)
        self.workspace.example.clicked.connect(self.demo)
        layout.addWidget(self.workspace, 1)
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.gesture_warning = self.home.warning
        self.update_trigger_hints()
        self.trigger.currentIndexChanged.connect(self.change_trigger)
        menu = QMenu(self)
        menu.addAction(f"打开 {APP_NAME}", self.open_home)
        menu.addAction("生词本", self.open_library)
        menu.addAction("框选翻译", lambda: self.begin(True))
        menu.addSeparator()
        menu.addAction("设置", self.open_settings)
        menu.addAction("退出", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        self.sync_tray_window()
        self.gesture_ready = False
        self.active_mode = None
        self.gestures = QProcess(self)
        self.gestures.readyReadStandardOutput.connect(self.read_gestures)
        self.gestures.errorOccurred.connect(lambda error: self.gesture_failed(self.gestures.errorString()))
        self.gestures.finished.connect(lambda: self.gesture_failed("监听进程已退出"))
        self.gestures.start(str(Path(sys.executable).with_name("pythonw.exe")),
                            ["-u", str(Path(__file__).with_name("gestures.py").resolve()), self.trigger.currentData()])
        area = QApplication.primaryScreen().availableGeometry()
        size = QSize(min(1000, area.width() - 24), min(672, area.height() - 48))
        # Let the two-column pages cross their breakpoints when the window shrinks.
        self.shell.setSizeConstraint(QLayout.SetNoConstraint)
        self.ensurePolished()
        self.arrange_shell(True)
        self.setMinimumSize(self.minimumSizeHint().boundedTo(size))
        self.arrange_shell(size.width() < 740)
        self.resize(size)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange_shell(event.size().width() < 740)

    def arrange_shell(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        self.wordmark.setVisible(not compact)
        self.engine_dot.setVisible(not compact)
        self.engine_label.setVisible(not compact)
        self.sidebar.setFixedHeight(54 if compact else 64)
        if compact:
            self.rail.setContentsMargins(16, 0, 16, 0)
            self.reading_layout.setContentsMargins(18, 18, 18, 18)
        else:
            self.rail.setContentsMargins(32, 0, 32, 0)
            self.reading_layout.setContentsMargins(32, 24, 32, 24)

    def sync_tray_window(self):
        """Keep a normal, reachable window on desktops without a notification area."""
        available = self.tray.isSystemTrayAvailable()
        if available and not self.tray.isVisible():
            self.tray.show()
        kind = Qt.Tool if available else Qt.Window
        if self.windowType() != kind:
            # On Windows Qt.Tool supplies WS_EX_TOOLWINDOW. Explicit caption
            # hints keep resizing and the minimize/maximize buttons available.
            self.setWindowFlags(kind | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
                                | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        return available

    def open_home(self):
        self.sync_tray_window()
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def open_settings(self):
        self.tabs.setCurrentWidget(self.preferences)
        self.open_home()

    def open_reader(self):
        self.tabs.setCurrentWidget(self.reader_page)
        self.workspace.input.setFocus()

    def open_gesture_settings(self):
        self.open_settings()
        self.trigger.setFocus()

    def tab_changed(self, index):
        if self.tabs.widget(index) is self.preferences:
            self.refresh_startup()
        elif self.tabs.widget(index) is self.reader_page:
            self.workspace.input.setFocus()

    def refresh_home(self, *, lookup_at=None):
        visible = self.home.isVisible()
        if not self.stopping and (lookup_at is not None or visible):
            self.stats_pool.submit(self.update_home_stats, lookup_at, visible)

    def update_home_stats(self, lookup_at, visible):
        try:
            if lookup_at is not None:
                self.notebook.record_lookup(lookup_at)
            if visible:
                self.stats_ready.emit(*self.notebook.home_stats())
        except (sqlite3.Error, OSError):
            if visible:
                self.stats_ready.emit(None, None, None)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and self.isMinimized() and hasattr(self, "tray"):
            # Finish the native minimize transition before hiding the window.
            QTimer.singleShot(0, self.finish_minimize)
        if (event.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, "preferences")
                and self.tabs.currentWidget() is self.preferences):
            self.refresh_startup()

    def finish_minimize(self):
        if self.stopping or not self.isMinimized():
            return
        if self.sync_tray_window():
            self.hide()
        elif not self.isVisible():
            # The tray disappeared while the tool window was open. Changing
            # its native type hides it; put it back on the regular taskbar.
            self.showMinimized()

    def refresh_startup(self):
        try:
            state = self.login_startup.status()
        except (OSError, ValueError) as error:
            self.preferences.set_startup_state("error", f"读取启动项失败。{error}")
            return
        self.preferences.set_startup_state(state)

    def set_startup(self, enabled):
        try:
            self.login_startup.set_enabled(enabled)
        except (OSError, ValueError) as error:
            self.refresh_startup()
            self.preferences.set_notice(f"启动项更改失败。{error}")
            return
        self.refresh_startup()
        self.preferences.set_notice("")

    def open_system_startup(self):
        if not QDesktopServices.openUrl(QUrl("ms-settings:startupapps")):
            self.preferences.set_notice("请从 Windows 设置打开「应用 → 启动」。")

    def save_preference(self, key, value):
        self.settings.setValue(key, value)
        self.settings.sync()
        self.preferences.set_notice("" if self.settings.status() == QSettings.NoError
                                    else "此更改已在本次运行生效，写入本机设置失败。")

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
        self.refresh_home()
        if self.library.isVisible():
            self.library.refresh()

    def tray_clicked(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_home()

    def update_trigger_hints(self):
        mode = self.trigger.currentData() if self.gesture_warning.isHidden() else "off"
        self.home.set_mode(mode)
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.tray.setToolTip(f"{APP_NAME} · " + (f"轻按{key}取词" if key else "仅应用内查词"))

    def change_language(self):
        code = self.preferences.source_language.currentData()
        self.save_preference("sourceLanguage", code)
        self.workspace.set_source_language(code)
        self.invalidate()

    def change_trigger(self):
        self.save_preference("gesture", self.trigger.currentData())
        self.update_trigger_hints()
        self.invalidate()

    def gesture_failed(self, reason):
        self.gesture_ready = False
        self.card.dismiss_on_deactivate = True
        if not self.stopping and self.gesture_warning.isHidden():
            self.gesture_warning.setText(f"无法监听屏幕取词键（{reason}）。可双击原文查词或点「开始框选」。")
            self.gesture_warning.show()
            self.update_trigger_hints()
            if self.overlay is not None and self.overlay.from_ctrl:
                self.overlay.close()

    def read_gestures(self):
        while self.gestures.canReadLine() and not self.stopping:
            action, origin, end = json.loads(bytes(self.gestures.readLine()))
            if action == "ready":
                self.gesture_ready = True
                self.gesture_warning.hide()
                self.update_trigger_hints()
                self.active_mode = origin
                self.card.dismiss_on_deactivate = False
                self.watch_card()
            elif action == "mode":
                self.active_mode = origin
            elif action == "error":
                self.gesture_failed(f"Windows 错误 {origin}")
            else:
                self.on_gesture(action, origin, end)

    def watch_card(self):
        if self.gesture_ready and not self.stopping:
            hwnd = int(self.card.winId()) if self.card.isVisible() else 0
            self.gestures.write((json.dumps((self.ticket, hwnd, self.trigger.currentData())) + "\n").encode("ascii"))

    def on_gesture(self, action, origin, end):
        if action == "dismiss":
            if origin == self.ticket and self.card.isVisible():
                self.card.close()
            return
        if action in ("lookup", "start"):
            if self.active_mode != self.trigger.currentData() or self.active_mode == "off":
                return
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
        self.search_context = None
        if self.online_job is not None:
            self.online_job.cancel()
            self.online_job = None
        self.reading_from_editor = False
        self.saved_result = None
        if self.pending is not None:
            self.pending.cancel()
        self.card.hide()
        self.watch_card()
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None

    def try_home_word(self):
        self.invalidate()
        start = HOME_EXAMPLE.index("bank")
        self.submit(self.home.demo.mapToGlobal(self.home.demo.rect().center()),
                    passage=Passage(HOME_EXAMPLE, (start, start + 4), source_code="en"))

    def demo(self):
        examples = {
            "ja": ("図書館で日本語の本を読みます。", "図書館"),
            "ko": ("도서관에서 한국어 책을 읽습니다.", "도서관"),
            "it": ("Il gatto dorme sul divano in salotto.", "gatto"),
            "pt": ("O gato da minha irmã está dormindo no sofá da sala.", "gato"),
            "ru": ("Кошка спит на диване в гостиной.", "Кошка"),
            "fr": ("Le chat dort dans la maison de ma sœur.", "chat"),
            "de": ("Die Katze schläft auf dem Sofa im Wohnzimmer.", "Katze"),
            "es": ("El gato duerme en la casa de mi hermana.", "gato"),
        }
        text, word = examples.get(self.workspace.source_code,
                                  ("They sat on the river bank and watched the water.", "bank"))
        editor = self.workspace.input
        if not editor.toPlainText().strip():
            editor.setPlainText(text + "\n\nShe deposited her paycheck at the bank." if word == "bank" else text)
            editor.setTextCursor(editor.document().find(word))
            editor.setFocus()
            editor.lookup_cursor()
            return
        start = text.index(word)
        self.lookup_text(Passage(text, (start, start + len(word))), QCursor.pos())

    def lookup_text(self, passage, point):
        self.invalidate()
        self.reading_from_editor = True
        self.submit(point, passage=passage)

    def editor_changed(self):
        if self.reading_from_editor:
            self.invalidate()

    def begin(self, region, point=None):
        if point is None:
            point = QCursor.pos()
        editor = self.workspace.input
        under_pointer = QApplication.widgetAt(point) if not region else None
        if under_pointer is not None and self.home.isAncestorOf(under_pointer) and self.home.demo.isVisible():
            demo = self.home.demo
            if demo.rect().adjusted(-3, -3, 3, 3).contains(demo.mapFromGlobal(point)):
                self.try_home_word()
                return
        if under_pointer is editor.viewport():
            if not editor.lookup_point(QPointF(editor.viewport().mapFromGlobal(point))):
                self.invalidate()
                self.card.show_message("原文查词", "请指向一个单词，或将光标放在词中按 Alt+Enter。", point)
            return
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
        self.card.show_message("本机翻译", "正在读取并翻译…", point)
        future = self.pool.submit(analyze, image, hit, passage, self.workspace.source_code)
        self.pending = future

        def completed(job):
            if not job.cancelled():
                self.finished.emit(ticket, point, job)
        future.add_done_callback(completed)

    def show_result(self, ticket, point, job):
        if ticket != self.ticket:
            return
        try:
            passage, result, excerpt, language, pos = job.result()
        except UnsupportedLanguage as error:
            self.card.show_original(error.language, error.text, point)
            return
        except Exception as error:
            self.card.show_message("需要处理", str(error), point)
            return
        unknown = result[0] == UNKNOWN
        can_search = bool(passage.selection) and passage.source_code in ("", "en")
        self.search_context = (passage, result, point, language, pos) if can_search else None
        self.saved_result = (passage, result) if passage.selection and not unknown else None
        self.card.show_result(passage, *result, point, excerpt=excerpt, language=language, pos=pos,
                              can_save=not unknown, can_search=can_search)
        if passage.selection and any(c.isalpha() for c in passage.word):
            self.refresh_home(lookup_at=time.time())
        if unknown and self.auto_online.isChecked() and any(c.isascii() and c.isalpha() for c in passage.word):
            self.search_online()

    def search_online(self):
        if not self.search_context or self.online_job is not None:
            return
        ticket = self.ticket
        self.card.online.setText("查询中…")
        self.card.online.setEnabled(False)
        future = self.online_pool.submit(online_meanings, self.search_context[0].word)
        self.online_job = future
        future.add_done_callback(lambda job: self.online_finished.emit(ticket, job) if not job.cancelled() else None)

    def show_online(self, ticket, job):
        if ticket != self.ticket or self.search_context is None or job is not self.online_job:
            return
        passage, local_result, point, language, pos = self.search_context
        self.online_job = None
        try:
            matches = job.result()
        except Exception:
            matches = []
            message = "百科暂时无法连接，可稍后重试。"
        else:
            message = "百科也没有找到同名且有说明的条目。"
        if matches:
            gloss = "\n".join((f"{i}. " if len(matches) > 1 else "") + desc
                              for i, (_, desc) in enumerate(matches, 1))
            ids = [identity for identity, _ in matches]
            result = ("Wikidata · 同名参考" if len(ids) > 1 else "Wikidata · 百科参考", gloss, local_result[2])
            self.saved_result = passage, (result[0] + " · " + " / ".join(ids), gloss, result[2])
            self.card.show_result(passage, *result, point, language=language, pos=pos, references=ids)
        else:
            unknown = local_result[0] == UNKNOWN
            gloss = message if unknown else local_result[1] + "\n" + message
            self.card.show_result(passage, local_result[0], gloss, local_result[2], point,
                                  language=language, pos=pos, can_save=not unknown, can_search=True, web_search=True)
            self.card.online.setText("再查一次")

    def closeEvent(self, event):
        if (self.preferences.close_behavior.currentData() == "tray" and self.tray.isVisible()
                and self.tray.isSystemTrayAvailable()):
            self.hide()
            event.ignore()
        else:
            QApplication.quit()

    def shutdown(self):
        self.stopping = True
        self.player.shutdown()
        self.gestures.closeWriteChannel()
        if self.gestures.state() != QProcess.NotRunning and not self.gestures.waitForFinished(2000):
            self.gestures.kill()
            self.gestures.waitForFinished(2000)
        self.invalidate()
        self.tray.hide()
        self.workspace.reset_result()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.online_pool.shutdown(wait=False, cancel_futures=True)
        self.stats_pool.shutdown(wait=True)


def main():
    from instance import activation_event
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WaxTranslate.Desktop")
    background = sys.argv[1:] == ["--background"]
    app = QApplication(sys.argv[:1] if background else sys.argv)
    activation = activation_event(app, activate_existing=not background)
    if activation is None:
        return 0
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    window = Window()
    activation.activated.connect(window.open_home)
    if not window.tray.isVisible():
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
