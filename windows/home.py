"""Windows lookup dashboard."""
from datetime import datetime
import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHeaderView, QHBoxLayout, QLabel, QLayout, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from languages import NAMES
from theme import ui_icon


HOME_STYLE = """
    QWidget#home {background:transparent;}
    QPushButton#useHint {background:rgba(250,249,246,220); border:1px solid transparent; border-radius:4px; padding:0;}
    QPushButton#useHint:focus, QPushButton#useHint:hover {border-bottom:1px solid #79756e;}
    QPushButton#useHint QLabel {color:#403e39; font-size:13px;}
    QLabel#shortcutKey {background:#f7f5ef; border:1px solid #b8b4aa; border-bottom:2px solid #aaa69c;
        border-radius:4px; padding:1px 5px; font-weight:600;}
    QPushButton#region {background:rgba(250,249,246,185); color:#292824; border:1px solid #aaa69c;
        border-radius:5px; padding:4px 8px; font-size:13px;}
    QPushButton#region:hover, QPushButton#region:focus {background:#efede6; border-color:#494740;}
    QFrame#statTile {background:rgba(255,254,251,229); border:1px solid rgba(117,113,102,44); border-radius:10px;}
    QLabel#statValue {color:#201f1c; font:600 29px 'Segoe UI','Microsoft YaHei UI';}
    QLabel#statName {color:#393832; font-size:13px;}
    QLabel#statNote, QLabel#historyNotice {color:#5b5951; font-size:12px;}
    QLabel#recentTitle {color:#45423c; font-size:14px; font-weight:600;}
    QTableWidget#recentWords {background:transparent; border:0; outline:0;
        selection-background-color:#e6e4dd; selection-color:#171715;}
    QTableWidget#recentWords::item {border:0; padding:0 2px;}
    QTableWidget#recentWords::item:focus {border:1px solid #767369;}
    QLabel#homeWarning {color:#862d21; font-size:13px;}
"""


def elapsed_label(stamp, now):
    if stamp is None:
        return ""
    minutes = max(0, int(now - stamp) // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes}分钟前"
    if minutes < 1440:
        return f"{minutes // 60}小时前"
    return f"{minutes // 1440}天前"


class HomePage(QWidget):
    region_requested = Signal()
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="home")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(HOME_STYLE)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.column = QWidget()
        outer.addWidget(self.column)
        outer.addStretch()
        self.page = QVBoxLayout(self.column)
        self.page.setSpacing(9)
        tools = QHBoxLayout()
        self.instructions = QPushButton(objectName="useHint")
        self.instructions.setToolTip("更改取词键")
        self.instructions.setCursor(Qt.PointingHandCursor)
        self.instructions.clicked.connect(self.settings_requested)
        hint = QHBoxLayout(self.instructions)
        hint.setSizeConstraint(QLayout.SetFixedSize)
        hint.setSpacing(4)
        hint.setContentsMargins(4, 3, 4, 3)
        self.hint_start = QLabel()
        self.key = QLabel(objectName="shortcutKey")
        self.hint_end = QLabel("查看释义")
        for part in (self.hint_start, self.key, self.hint_end):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            hint.addWidget(part)
        tools.addWidget(self.instructions)
        tools.addStretch()
        self.region = QPushButton(ui_icon("region"), "框选翻译", objectName="region")
        self.region.setIconSize(QSize(14, 14))
        self.region.setCursor(Qt.PointingHandCursor)
        self.region.clicked.connect(self.region_requested)
        tools.addWidget(self.region)
        self.page.addLayout(tools)

        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.values = {}
        for index, (name, note) in enumerate((("次取词", "今日 — 次"), ("已保存", "生词本中的词条"),
                                              ("待复习", "已到复习时间"), ("已掌握", "连续记住 3 次"))):
            tile = QFrame(objectName="statTile")
            content = QVBoxLayout(tile)
            content.setContentsMargins(14, 6, 12, 9)
            content.setSpacing(1)
            line = QHBoxLayout()
            line.setSpacing(5)
            value = QLabel("—", objectName="statValue")
            self.values[name] = value
            line.addWidget(value)
            line.addWidget(QLabel(name, objectName="statName"), 0, Qt.AlignVCenter)
            line.addStretch()
            content.addLayout(line)
            description = QLabel(note, objectName="statNote")
            if index == 0:
                self.today = description
            content.addWidget(description)
            self.grid.addWidget(tile, index // 2, index % 2)
        self.page.addLayout(self.grid)
        self.heading = QLabel("最近取词", objectName="recentTitle")
        self.heading.setContentsMargins(1, 5, 0, 0)
        self.page.addWidget(self.heading)
        self.history = QStackedWidget()
        self.notice = QLabel("正在读取查词记录…", objectName="historyNotice")
        self.notice.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.notice.setContentsMargins(2, 6, 0, 0)
        self.history.addWidget(self.notice)
        self.table = QTableWidget(0, 3, objectName="recentWords")
        self.table.setAccessibleName("最近取词，从新到旧")
        self.table.setHorizontalHeaderLabels(["词语", "释义", "最近取词时间"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.viewport().setAutoFillBackground(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.hide()
        self.history.addWidget(self.table)
        self.page.addWidget(self.history, 1)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        self.page.addWidget(self.warning)
        self.rows = []
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")
        self.arrange()

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.hint_start.setText("指向生词，轻按" if key else "在对照翻译中双击单词，查看释义")
        self.key.setText(key or "")
        self.key.setVisible(bool(key))
        self.hint_end.setVisible(bool(key))
        hint = f"{self.hint_start.text()} {key} 查看释义" if key else self.hint_start.text()
        self.instructions.setAccessibleName(hint + "。更改取词键")

    def set_stats(self, stats):
        counts = (stats.total, stats.saved, stats.due, stats.mastered) if stats is not None else (None,) * 4
        for (name, label), count in zip(self.values.items(), counts):
            value = "—" if count is None else f"{count:,}"
            label.setText(value)
            label.setAccessibleName(f"{value} {name}")
        self.today.setText(f"今日 {stats.today:,} 次" if stats is not None else "今日 — 次")
        recent = stats.recent if stats is not None else []
        self.notice.setText("查过的词会显示在这里" if stats is not None else "暂时无法读取查词记录")
        self.history.setCurrentWidget(self.table if recent else self.notice)
        now = time.time()
        if recent != self.rows:
            self.table.setRowCount(len(recent))
            for row, (word, language, gloss, stamp) in enumerate(recent):
                for column, value in enumerate((word, gloss, "")):
                    item = QTableWidgetItem(value)
                    font = QFont({"ja": "Yu Gothic UI", "ko": "Malgun Gothic"}.get(language, "Segoe UI")
                                 if column == 0 else "Microsoft YaHei UI")
                    font.setPixelSize((15, 14, 12)[column])
                    item.setFont(font)
                    item.setForeground(QColor(("#201f1c", "#383731", "#5a5851")[column]))
                    if column == 2:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        item.setToolTip(datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M") if stamp else "")
                    else:
                        item.setToolTip(f"{word} · {NAMES.get(language, language)}" if column == 0 else gloss)
                    self.table.setItem(row, column, item)
            self.rows = recent
        for row, (_, _, _, stamp) in enumerate(recent):
            self.table.item(row, 2).setText(elapsed_label(stamp, now))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def hasHeightForWidth(self):
        return False

    def arrange(self):
        compact = self.width() < 760
        width = min(self.width(), max(445, min(710, round(self.width() * 0.58))))
        self.column.setFixedWidth(width)
        margin = 16 if compact else 28
        self.page.setContentsMargins(margin, 14, 12, 14)
        self.table.setColumnWidth(0, (width - margin - 12) // 3)
        self.table.setColumnWidth(2, 76)

    def paintEvent(self, event):
        super().paintEvent(event)
        edge = self.column.width()
        wash = QLinearGradient(0, 0, edge + self.width() * 0.13, 0)
        for position, opacity in ((0, 244), (0.75, 235), (0.87, 207), (1, 0)):
            wash.setColorAt(position, QColor(250, 249, 246, opacity))
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), wash)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
