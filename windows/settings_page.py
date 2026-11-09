"""Preferences for the Windows reader. The window owns persistence and system actions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QBoxLayout, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from install_model import DEFAULT_LANGUAGES, install_language, language_ready, translation_dir
from languages import NAMES
from theme import COLORS, label


class Switch(QCheckBox):
    """A compact switch with native checkbox focus, keyboard and accessibility semantics."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(48, 34)
        self.setCursor(Qt.PointingHandCursor)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#555551"), 1.5))
            painter.drawRoundedRect(QRectF(1, 2, 46, 30), 15, 15)
        if not self.isEnabled():
            fill, border = "#e6e5df", "#d5d4ce"
        elif self.isChecked():
            fill, border = COLORS["accent"], COLORS["accent"]
        else:
            fill, border = "#bcbcb6", "#90908a"
        painter.setBrush(QColor(fill))
        painter.setPen(QPen(QColor(border), 1))
        painter.drawRoundedRect(QRectF(4, 6, 40, 22), 11, 11)
        painter.setPen(Qt.NoPen)
        thumb = QRectF(25 if self.isChecked() else 7, 9, 16, 16)
        painter.setBrush(QColor(36, 51, 40, 32))
        painter.drawEllipse(thumb.translated(0, 1))
        painter.setBrush(QColor("#fffefa"))
        painter.drawEllipse(thumb)


class Choice(QComboBox):
    def __init__(self):
        super().__init__(objectName="settingsChoice")
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(COLORS["muted"]), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 11, self.height() / 2
        painter.drawPolyline([QPointF(x - 3, y - 1.5), QPointF(x, y + 1.5), QPointF(x + 3, y - 1.5)])


def setting_row(layout, title, control, description=""):
    row = QGridLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setHorizontalSpacing(12)
    row.setVerticalSpacing(3)
    row.setColumnStretch(0, 1)
    name = label(title, "subhead")
    name.setWordWrap(True)
    name.setBuddy(control)
    control.setAccessibleName(title)
    row.addWidget(name, 0, 0)
    if description:
        detail = label(description, "meta")
        detail.setWordWrap(True)
        detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(detail, 1, 0)
        control.setAccessibleDescription(description)
    row.addWidget(control, 0, 1, row.rowCount(), 1, Qt.AlignRight | Qt.AlignVCenter)
    layout.addLayout(row)


class SectionMark(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_mark = window
        self.setFixedSize(28, 30)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(COLORS["ink"]), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        if self.window_mark:
            painter.drawRoundedRect(QRectF(7.5, 9, 17, 14), 2, 2)
            painter.drawLine(QPointF(8, 13), QPointF(24, 13))
        else:
            painter.drawPolygon(QPolygonF([QPointF(10, 6.5), QPointF(23.5, 17), QPointF(17.8, 17.8),
                                           QPointF(20.5, 24), QPointF(17.2, 25.3), QPointF(14.6, 19.3),
                                           QPointF(10.4, 23)]))


class PreferenceSection(QWidget):
    def __init__(self, title, *, window_mark=False):
        super().__init__()
        self.row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(20)
        self.category = QWidget()
        heading = QHBoxLayout(self.category)
        heading.setSpacing(7)
        heading.addWidget(SectionMark(window_mark))
        heading.addWidget(label(title, "settingsSection"))
        heading.addStretch()
        self.row.addWidget(self.category, 0, Qt.AlignTop)
        panel = QFrame(objectName="settingsGroup")
        self.options = QVBoxLayout(panel)
        self.options.setContentsMargins(0, 15, 0, 6)
        self.options.setSpacing(15)
        self.row.addWidget(panel, 1)

    def set_compact(self, compact):
        self.category.setMinimumWidth(0 if compact else 132)
        self.category.layout().setContentsMargins(0, 0 if compact else 8, 0, 0)
        self.row.setSpacing(5 if compact else 20)
        self.row.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)


class SettingsPage(QScrollArea):
    pack_finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, objectName="settingsPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        content = QWidget(objectName="settingsSurface")
        content.setMaximumWidth(780)
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)
        layout.addWidget(label("设置", "heading"))

        self.system = PreferenceSection("启动与窗口", window_mark=True)
        system = self.system.options
        self.startup = Switch()
        setting_row(system, "开机启动", self.startup, "登录 Windows 后在系统托盘待命。")
        self.startup_status = label("", "warning")
        self.startup_status.setTextFormat(Qt.PlainText)
        self.startup_status.setWordWrap(True)
        self.startup_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        system.addWidget(self.startup_status)
        self.startup_actions = QWidget()
        actions = QHBoxLayout(self.startup_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.repair_startup = QPushButton("改用当前版本")
        self.system_startup = QPushButton("打开系统设置")
        self.remove_startup = QPushButton("移除启动项")
        self.retry_startup = QPushButton("重新读取")
        for action in (self.repair_startup, self.system_startup, self.remove_startup, self.retry_startup):
            actions.addWidget(action)
        actions.addStretch()
        system.addWidget(self.startup_actions)
        system.addWidget(QFrame(objectName="hairline"))
        self.close_behavior = Choice()
        self.close_behavior.addItem("收起到托盘", "tray")
        self.close_behavior.addItem("退出应用", "quit")
        setting_row(system, "关闭主窗口时", self.close_behavior)
        self.reading = PreferenceSection("取词与翻译")
        layout.addWidget(self.reading)
        reading = self.reading.options
        self.source_language = Choice()
        self.source_language.addItem("自动识别", "")
        for code, name in NAMES.items():
            self.source_language.addItem(name, code)
        setting_row(reading, "原文语言", self.source_language,
                    "应用于阅读、悬停和框选。短词难以判断时，可手动选择语言。")
        reading.addWidget(QFrame(objectName="hairline"))
        self.trigger = Choice()
        for text, mode in (("轻按左 Ctrl", "left"), ("轻按右 Ctrl", "right"), ("仅应用内查词", "off")):
            self.trigger.addItem(text, mode)
        setting_row(reading, "屏幕取词键", self.trigger)
        reading.addWidget(QFrame(objectName="hairline"))
        self.auto_online = Switch()
        setting_row(reading, "未收录词自动查百科", self.auto_online,
                    "本机查不到时，仅将选中的英文词条发送给 Wikidata。")
        self.packs = PreferenceSection("语言包")
        layout.addWidget(self.packs)
        self.pack_choice = Choice()
        self.pack_choice.setAccessibleName("选择要管理的语言包")
        for code in NAMES:
            self.pack_choice.addItem(NAMES[code], code)
        defaults = "、".join(NAMES[c] for c in DEFAULT_LANGUAGES)
        setting_row(self.packs.options, "离线语言", self.pack_choice, f"默认提供{defaults}。每个语言包包含识字和简体中文翻译资源。")
        actions = QHBoxLayout()
        self.pack_status = label("", "meta")
        self.pack_status.setWordWrap(True)
        self.pack_status.setTextFormat(Qt.PlainText)
        actions.addWidget(self.pack_status, 1)
        self.download = QPushButton("下载语言包")
        actions.addWidget(self.download)
        self.packs.options.addLayout(actions)
        self.pack_pool = ThreadPoolExecutor(max_workers=1)
        self.cancel_install = Event()
        self.pack_job = None
        self.pack_finished.connect(self.finish_pack)
        self.download.clicked.connect(self.start_pack)
        self.pack_choice.setCurrentIndex(next((i for i, code in enumerate(NAMES) if not language_ready(code)), 0))
        self.pack_choice.currentIndexChanged.connect(self.refresh_packs)
        self.source_language.currentIndexChanged.connect(self.select_missing_pack)
        self.refresh_packs()
        layout.addWidget(self.system)
        self.notice = label("", "warning")
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        layout.addStretch(1)
        self.set_startup_state("off")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 650
        self.system.set_compact(compact)
        self.reading.set_compact(compact)
        self.packs.set_compact(compact)
        margin = 16 if self.viewport().width() < 520 else 32
        self.widget().layout().setContentsMargins(margin, 15 if compact else 24, margin, 24)

    def refresh_packs(self):
        if self.pack_job is not None:
            return
        with QSignalBlocker(self.pack_choice):
            for i in range(self.pack_choice.count()):
                code = self.pack_choice.itemData(i)
                status = "已安装" if language_ready(code) else "待下载"
                self.pack_choice.setItemText(i, f"{NAMES[code]} · {status}")
        code = self.pack_choice.currentData()
        ready = language_ready(code)
        self.pack_status.setText("已安装，可以离线使用。" if ready else
                                 "已有翻译资源，下载后补齐识字模型。" if translation_dir(code) else
                                 "下载并校验后即可使用。")
        self.download.setEnabled(not ready)
        self.download.setText("已安装" if ready else "下载语言包")

    def select_missing_pack(self):
        code = self.source_language.currentData()
        if code and self.pack_job is None and not language_ready(code):
            self.pack_choice.setCurrentIndex(self.pack_choice.findData(code))

    def start_pack(self):
        code = self.pack_choice.currentData()
        if self.pack_job is not None or language_ready(code):
            return
        self.pack_choice.setEnabled(False)
        self.download.setEnabled(False)
        self.download.setText("下载中…")
        self.pack_status.setText(f"正在下载并校验{NAMES[code]}语言包…")
        self.pack_job = self.pack_pool.submit(install_language, code, cancel=self.cancel_install)
        self.pack_job.add_done_callback(self.pack_finished.emit)

    def finish_pack(self, job):
        if self.cancel_install.is_set():
            return
        self.pack_job = None
        self.pack_choice.setEnabled(True)
        self.refresh_packs()
        try:
            job.result()
        except Exception as error:
            self.pack_status.setText(f"安装失败，可重新下载。{error}")
            self.download.setText("重新下载")

    def stop_downloads(self):
        self.cancel_install.set()
        self.pack_pool.shutdown(wait=False, cancel_futures=True)

    def set_startup_state(self, state, message=""):
        with QSignalBlocker(self.startup):
            self.startup.setChecked(state in ("on", "moved"))
        self.startup.setEnabled(state in ("on", "off", "moved"))
        default = {
            "moved": "启动项仍指向其他位置。可以改用当前版本，或关闭开机启动。",
            "blocked": "Windows 已禁用该启动项。可在系统的“启动应用”中启用 WaxTranslate。",
            "error": "无法读取 Windows 启动项，请重试。",
        }
        status = message or default.get(state, "")
        self.startup_status.setText(status)
        self.startup_status.setVisible(bool(status))
        self.repair_startup.setVisible(state == "moved")
        self.system_startup.setVisible(state == "blocked")
        self.remove_startup.setVisible(state == "blocked")
        self.retry_startup.setVisible(state == "error")
        self.startup_actions.setVisible(state in ("moved", "blocked", "error"))

    def set_notice(self, message):
        self.notice.setText(message)
        self.notice.setVisible(bool(message))
        if message:
            self.ensureWidgetVisible(self.notice)
