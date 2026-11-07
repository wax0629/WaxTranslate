"""Preferences for the Windows reader. The window owns persistence and system actions."""
from PySide6.QtCore import QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from theme import label


class Switch(QCheckBox):
    """A compact switch with native checkbox focus, keyboard and accessibility semantics."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 32)
        self.setCursor(Qt.PointingHandCursor)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#365f91"), 1.5))
            painter.drawRoundedRect(QRectF(1, 2, 42, 28), 14, 14)
        if not self.isEnabled():
            fill, border = "#ecece7", "#d8d8d1"
        elif self.isChecked():
            fill, border = "#48725b", "#48725b"
        else:
            fill, border = "#dedfd8", "#c5c7be"
        painter.setBrush(QColor(fill))
        painter.setPen(QPen(QColor(border), 1))
        painter.drawRoundedRect(QRectF(4, 5.5, 36, 21), 10.5, 10.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.white)
        painter.drawEllipse(QRectF(22 if self.isChecked() else 7, 8.5, 15, 15))


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


def setting_group(layout, title):
    layout.addWidget(label(title, "settingsSection"))
    panel = QFrame(objectName="settingsGroup")
    box = QVBoxLayout(panel)
    box.setContentsMargins(16, 12, 16, 12)
    box.setSpacing(11)
    layout.addWidget(panel)
    return box


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
        layout.setContentsMargins(27, 22, 27, 20)
        layout.setSpacing(8)
        layout.addWidget(label("设置", "heading"))
        layout.addSpacing(7)

        system = setting_group(layout, "启动与窗口")
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
        self.close_behavior = QComboBox(objectName="settingsChoice")
        self.close_behavior.addItem("收起到托盘", "tray")
        self.close_behavior.addItem("退出应用", "quit")
        setting_row(system, "关闭主窗口时", self.close_behavior)
        layout.addSpacing(8)

        reading = setting_group(layout, "取词与翻译")
        self.trigger = QComboBox(objectName="settingsChoice")
        for text, mode in (("轻按左 Ctrl", "left"), ("轻按右 Ctrl", "right"), ("仅应用内查词", "off")):
            self.trigger.addItem(text, mode)
        setting_row(reading, "屏幕取词键", self.trigger)
        reading.addWidget(QFrame(objectName="hairline"))
        self.auto_online = Switch()
        setting_row(reading, "未收录词自动查百科", self.auto_online,
                    "仅将所选词条发送给 Wikidata，原句和截图保留在本机。")
        self.notice = label("", "warning")
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        layout.addStretch(1)
        self.set_startup_state("off")

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
