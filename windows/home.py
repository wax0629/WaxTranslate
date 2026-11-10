"""Windows lookup dashboard."""
from datetime import datetime
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHeaderView, QHBoxLayout, QLabel, QLayout, QPushButton,
    QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from languages import NAMES
from theme import COLORS, theme_css


HOME_STYLE = theme_css("""
    QWidget#home {background:transparent;}
    QPushButton#useHint {background:transparent; border:1px solid transparent; border-radius:4px; padding:0;}
    QPushButton#useHint:focus, QPushButton#useHint:hover {border-bottom:1px solid #79756e;}
    QPushButton#useHint QLabel {color:$ink; font-size:12px;}
    QLabel#shortcutKey {background:transparent; border:0; padding:0; font-weight:400;}
    QFrame#statTile {background:$sheet; border:1px solid $rule; border-radius:10px;}
    QLabel#statValue {color:$ink; font:30px 'Spectral';}
    QLabel#statName {color:$ink; font-size:12px;}
    QLabel#statNote, QLabel#historyNotice {color:$muted; font-size:11px;}
    QLabel#recentTitle {color:$ink; font-size:13px; font-weight:600;}
    QTableWidget#recentWords {background:transparent; border:0; outline:0;
        selection-background-color:$soft; selection-color:$ink;}
    QTableWidget#recentWords::item {border:0; padding:0 2px;}
    QTableWidget#recentWords::item:focus {border:1px solid #767369;}
    QLabel#homeWarning {color:$accent; font-size:13px;}
""")


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
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="home")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(HOME_STYLE)
        outer = QHBoxLayout(self)
        outer.setSizeConstraint(QLayout.SetNoConstraint)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.column = QWidget()
        self.column.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        outer.addWidget(self.column, 1)
        outer.addStretch(0)
        self.page = QVBoxLayout(self.column)
        self.page.setSpacing(18)
        tools = QHBoxLayout()
        self.instructions = QPushButton(objectName="useHint")
        self.instructions.setToolTip("更改取词键")
        self.instructions.setCursor(Qt.PointingHandCursor)
        self.instructions.clicked.connect(self.settings_requested)
        hint = QHBoxLayout(self.instructions)
        hint.setSizeConstraint(QLayout.SetFixedSize)
        hint.setSpacing(4)
        hint.setContentsMargins(0, 3, 0, 3)
        self.hint_start = QLabel()
        self.key = QLabel(objectName="shortcutKey")
        self.hint_end = QLabel("查看释义")
        for part in (self.hint_start, self.key, self.hint_end):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            hint.addWidget(part)
        tools.addWidget(self.instructions)
        tools.addStretch()
        self.page.addLayout(tools)

        self.statistics = QWidget()
        self.statistics.setMaximumWidth(432)
        self.grid = QGridLayout(self.statistics)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.values = {}
        for index, (name, note) in enumerate((("次取词", "今日 — 次"), ("已保存", "生词本中的词条"),
                                              ("待复习", "已到复习时间"), ("已掌握", "连续记住 3 次"))):
            tile = QFrame(objectName="statTile")
            content = QVBoxLayout(tile)
            content.setContentsMargins(14, 9, 14, 11)
            content.setSpacing(2)
            line = QHBoxLayout()
            line.setSpacing(5)
            value = QLabel("—", objectName="statValue")
            self.values[name] = value
            line.addWidget(value)
            line.addWidget(QLabel(name, objectName="statName"), 0, Qt.AlignBaseline)
            line.addStretch()
            content.addLayout(line)
            description = QLabel(note, objectName="statNote")
            if index == 0:
                self.today = description
            content.addWidget(description)
            self.grid.addWidget(tile, index // 2, index % 2)
        self.page.addWidget(self.statistics)
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
        self.table.verticalHeader().setDefaultSectionSize(38)
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
                    font = QFont({"ja": "Yu Gothic UI", "ko": "Malgun Gothic"}.get(language, "Spectral")
                                 if column == 0 else "Microsoft YaHei UI")
                    font.setPixelSize((18, 13, 10)[column])
                    item.setFont(font)
                    item.setForeground(QColor(COLORS["muted"] if column == 2 else COLORS["ink"]))
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
        width = self.width() if compact else min(640, round(self.width() * 0.64))
        # A width derived from the current viewport must not become the
        # window's minimum width before its first resize (initially 640px).
        self.column.setMaximumWidth(width)
        margin = 22 if compact else 26
        self.statistics.setFixedWidth(min(432, max(1, width - margin * 2)))
        self.page.setContentsMargins(margin, 24, margin, 24)
        self.table.setColumnWidth(0, max(100, (width - margin * 2 - 60) // 2))
        self.table.setColumnWidth(2, 60)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
