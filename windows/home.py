"""Windows lookup dashboard."""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QFrame, QHeaderView, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from languages import NAMES
from theme import ui_icon


HOME_STYLE = """
    QWidget#home {background:transparent;}
    QLabel#coverTitle {font:600 56px 'Noto Serif SC','SimSun','Microsoft YaHei UI'; color:#171715;}
    QLabel#totalLabel {color:#4d4a45; font-size:14px;}
    QLabel#activity, QLabel#historyNotice, QLabel#pastActivity {color:#504d48; font-size:13px;}
    QPushButton#useHint {background:transparent; color:#413f3b; border:1px solid transparent;
        padding:2px 0; text-align:left; font-size:14px;}
    QPushButton#useHint:focus, QPushButton#useHint:hover {border-bottom:1px solid #79756e;}
    QPushButton#region {background:#232321; color:#fffefa; border:1px solid #232321;
        padding:6px 14px; border-radius:4px; font-size:14px; font-weight:600;}
    QPushButton#region:hover {background:#40403b;}
    QPushButton#region:focus {border:2px solid #827f74; padding:5px 13px;}
    QPushButton#readOriginal {background:transparent; color:#34332f; border:1px solid transparent;
        padding:6px 9px; border-radius:4px; font-size:14px;}
    QPushButton#readOriginal:hover, QPushButton#readOriginal:focus {border-color:#928e84;}
    QLabel#recentTitle {color:#272622; font-size:16px; font-weight:600;}
    QTableWidget#recentWords {background:transparent; border:0; border-top:1px solid #a5a198;
        outline:0; selection-background-color:#dfddd5; selection-color:#171715;}
    QTableWidget#recentWords::item {border:0; border-bottom:1px solid rgba(74,73,65,45); padding:0 2px;}
    QTableWidget#recentWords::item:focus {border:1px solid #767369;}
    QLabel#homeWarning {color:#862d21; font-size:13px;}
"""


class HomePage(QWidget):
    region_requested = Signal()
    reader_requested = Signal()
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
        self.page.setSpacing(0)
        self.page.addStretch(2)
        self.title = QLabel(objectName="coverTitle")
        self.page.addWidget(self.title)

        self.metrics = QWidget()
        metrics = QVBoxLayout(self.metrics)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(0)
        metrics.addWidget(QLabel("累计查词", objectName="totalLabel"))
        self.total = QLabel()
        self.total.setTextFormat(Qt.RichText)
        metrics.addWidget(self.total)
        self.activity = QLabel(objectName="activity")
        self.activity.setContentsMargins(0, 3, 0, 0)
        metrics.addWidget(self.activity)
        self.page.addWidget(self.metrics)

        self.sheet = QWidget()
        history = QVBoxLayout(self.sheet)
        history.setContentsMargins(0, 14, 0, 0)
        history.setSpacing(5)
        history.addWidget(QLabel("最近查词", objectName="recentTitle"))
        self.table = QTableWidget(0, 3, objectName="recentWords")
        self.table.setAccessibleName("最近查词，从新到旧")
        self.table.setHorizontalHeaderLabels(["词语", "释义", "语种"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.viewport().setAutoFillBackground(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.hide()
        history.addWidget(self.table)
        self.page.addWidget(self.sheet)

        self.notice = QLabel("正在读取查词记录…", objectName="historyNotice")
        self.page.addWidget(self.notice)
        self.page.addSpacing(8)
        self.instructions = QPushButton(objectName="useHint")
        self.instructions.setToolTip("更改取词键")
        self.instructions.setCursor(Qt.PointingHandCursor)
        self.instructions.clicked.connect(self.settings_requested)
        self.page.addWidget(self.instructions, 0, Qt.AlignLeft)
        self.page.addSpacing(10)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.region = QPushButton(ui_icon("region", "#fffefa"), "框选翻译", objectName="region")
        self.region.setIconSize(QSize(16, 16))
        self.region.setCursor(Qt.PointingHandCursor)
        self.region.clicked.connect(self.region_requested)
        actions.addWidget(self.region)
        self.reader = QPushButton(ui_icon("book"), "打开对照翻译", objectName="readOriginal")
        self.reader.setIconSize(QSize(16, 16))
        self.reader.setCursor(Qt.PointingHandCursor)
        self.reader.clicked.connect(self.reader_requested)
        actions.addWidget(self.reader)
        actions.addStretch()
        self.page.addLayout(actions)
        self.past_activity = QLabel(objectName="pastActivity")
        self.past_activity.setContentsMargins(0, 18, 0, 0)
        self.past_activity.setWordWrap(True)
        self.past_activity.hide()
        self.page.addWidget(self.past_activity)
        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        self.page.addWidget(self.warning)
        self.page.addStretch(3)
        self.rows = []
        self.metrics.hide()
        self.sheet.hide()
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")
        self.arrange()

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.title.setText("屏幕取词" if key else "原文查词")
        hint = f"指向外文单词，轻按 {key} 查看释义。" if key else "在「对照翻译」中双击单词，即可查看释义。"
        self.instructions.setText(hint)
        self.instructions.setAccessibleName(hint + " 点击更改取词键。")

    def set_stats(self, snapshot):
        total, today, saved, due, recent = snapshot if snapshot is not None else (0, 0, 0, 0, [])
        self.metrics.setVisible(bool(recent))
        self.title.setVisible(not recent)
        count = f"累计查词 {total:,} 次"
        self.total.setAccessibleName(count)
        # A single text line gives the two font sizes a shared typographic baseline.
        self.total.setText(f"<span style=\"font:600 52px 'Spectral'; color:#171715\">{total:,}</span>"
                           "&nbsp; <span style=\"font-size:15px; color:#514e48\">次</span>")
        self.activity.setText(f"今日 {today:,} 次     ·     已收藏 {saved:,}     ·     待复习 {due:,}")
        past = [label for value, label in ((total, count), (today, f"今日 {today:,} 次"),
                (saved, f"已收藏 {saved:,}"), (due, f"待复习 {due:,}")) if value]
        self.past_activity.setText("   ·   ".join(past))
        self.past_activity.setVisible(bool(past) and not recent)
        self.notice.setText("暂时无法读取查词记录" if snapshot is None else "")
        self.notice.setVisible(snapshot is None)
        self.sheet.setVisible(bool(recent))
        self.update()
        if recent == self.rows:
            return
        self.rows = recent
        self.table.setRowCount(len(recent))
        for row, (word, language, gloss) in enumerate(recent):
            for column, value in enumerate((word, gloss, NAMES.get(language, language))):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                word_font = {"ja": "Yu Gothic UI", "ko": "Malgun Gothic"}.get(language, "Segoe UI")
                font = QFont(word_font if column == 0 else "Microsoft YaHei UI")
                font.setPixelSize((16, 14, 12)[column])
                font.setWeight(QFont.DemiBold if column == 0 else QFont.Normal)
                item.setFont(font)
                item.setForeground(QColor(("#181816", "#363632", "#56544e")[column]))
                if column == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.setMaximumHeight(2 + len(recent) * self.table.verticalHeader().defaultSectionSize())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        compact = self.width() < 720
        self.portrait = self.height() > self.width() * 1.15
        margin = 22 if compact else min(64, round(self.width() * 0.052))
        width = self.width() if self.portrait else min(self.width(), max(330, min(640, round(self.width() * 0.48))))
        self.column.setFixedWidth(width)
        self.page.setStretch(0, 7 if self.portrait else 2)
        self.page.setStretch(self.page.count() - 1, 1 if self.portrait else 3)
        self.page.setContentsMargins(margin, 12, margin if self.portrait else 6, 12)
        self.table.setColumnWidth(0, max(87, min(154, (width - margin) // 3)))
        self.table.setColumnWidth(2, 47 if compact else 58)

    def paintEvent(self, event):
        super().paintEvent(event)
        paper = QColor(250, 249, 246)
        if self.portrait:
            heading = self.title if self.metrics.isHidden() else self.metrics
            top = heading.y()
            wash = QLinearGradient(0, max(0, top - 140), 0, max(1, top + 24))
            stops = ((0, 0), (0.35, 58), (0.75, 197), (1, 237))
        else:
            # The original landscape illustration already leaves paper at the left.
            if self.metrics.isHidden() and self.width() >= 820 and self.width() > self.height() * 1.55:
                return
            edge = self.column.width()
            wash = QLinearGradient(0, 0, edge + self.width() * 0.19, 0)
            stops = ((0, 225), (0.7, 221), (0.8, 166), (0.9, 55), (1, 0))
        for position, opacity in stops:
            paper.setAlpha(opacity)
            wash.setColorAt(position, paper)
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), wash)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
