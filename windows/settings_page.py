"""Preferences for the Windows reader. The window owns persistence and system actions."""
from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QBoxLayout, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from languages import NAMES
from theme import label


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
            painter.setPen(QPen(QColor("#885145"), 1.5))
            painter.drawRoundedRect(QRectF(1, 2, 46, 30), 15, 15)
        if not self.isEnabled():
            top, bottom, border = "#eee5d3", "#e1d8c5", "#c8bca4"
        elif self.isChecked():
            top, bottom, border = "#995044", "#78392f", "#78392f"
        else:
            top, bottom, border = "#e1d1b4", "#d4c2a2", "#998262"
        track = QLinearGradient(0, 6, 0, 28)
        track.setColorAt(0, QColor(top))
        track.setColorAt(1, QColor(bottom))
        painter.setBrush(track)
        painter.setPen(QPen(QColor(border), 1))
        painter.drawRoundedRect(QRectF(4, 6, 40, 22), 11, 11)
        painter.setPen(Qt.NoPen)
        thumb = QRectF(25 if self.isChecked() else 7, 9, 16, 16)
        painter.setBrush(QColor(50, 31, 22, 38))
        painter.drawEllipse(thumb.translated(0, 1))
        painter.setBrush(QColor("#fff7e5"))
        painter.drawEllipse(thumb)


class Choice(QComboBox):
    def __init__(self):
        super().__init__(objectName="settingsChoice")
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#765844"), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
        self.setFixedSize(32, 32)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ead8b6"))
        painter.drawRoundedRect(self.rect(), 9, 9)
        painter.setPen(QPen(QColor("#6a4131"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
        self.row.setSpacing(12)
        self.category = QWidget()
        heading = QHBoxLayout(self.category)
        heading.setSpacing(7)
        heading.addWidget(SectionMark(window_mark))
        heading.addWidget(label(title, "settingsSection"))
        heading.addStretch()
        self.row.addWidget(self.category, 0, Qt.AlignTop)
        panel = QFrame(objectName="settingsGroup")
        self.options = QVBoxLayout(panel)
        self.options.setContentsMargins(18, 17, 18, 17)
        self.options.setSpacing(14)
        self.row.addWidget(panel, 1)

    def set_compact(self, compact):
        self.category.setMinimumWidth(0 if compact else 120)
        self.category.layout().setContentsMargins(0, 0 if compact else 14, 0, 0)
        self.row.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)


class SettingsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent, objectName="settingsPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        content = QWidget(objectName="settingsSurface")
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 26, 30, 23)
        layout.setSpacing(14)
        layout.addWidget(label("设置", "heading"))
        layout.addWidget(QFrame(objectName="hairline"))

        self.system = PreferenceSection("启动与窗口", window_mark=True)
        layout.addWidget(self.system)
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
        margin = 16 if self.viewport().width() < 520 else 30
        self.widget().layout().setContentsMargins(margin, 18 if compact else 26, margin, 23)

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
