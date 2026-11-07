"""Windows lookup dashboard."""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from languages import NAMES
from theme import ui_icon


HOME_STYLE = """
    QWidget#home {background:transparent;}
    QFrame#recentSheet {background:rgba(253,252,248,197); border:1px solid rgba(66,65,57,66); border-radius:6px;}
    QLabel#totalLabel {color:#464641; font-size:15px; font-weight:500;}
    QLabel#totalValue {font:600 48px 'Segoe UI'; color:#151514;}
    QLabel#metricUnit {font-size:16px; color:#565650;}
    QLabel#activity {font-size:13px; color:#484842;}
    QFrame#guideBar {background:rgba(250,249,245,194); border:1px solid rgba(66,65,57,52); border-radius:4px;}
    QPushButton#useHint {background:transparent; color:#44443e; border:1px solid transparent;
        font-size:13px; text-align:left; padding:3px 0;}
    QPushButton#useHint:focus, QPushButton#useHint:hover {border-bottom:1px solid #565650;}
    QPushButton#region {background:transparent; border:1px solid #a09f97; border-radius:3px;
        padding:3px 9px; font-size:13px; color:#272724;}
    QPushButton#region:focus, QPushButton#region:hover {background:#e6e5de; border-color:#54544e;}
    QLabel#recentTitle {font-size:20px; font-weight:600;}
    QLabel#emptyHistory {color:#696962; font-size:14px;}
    QTableWidget#recentWords, QHeaderView {background:transparent; border:0; outline:0;
        selection-background-color:#e4e3dc; selection-color:#171715;}
    QTableWidget#recentWords::item {border:0; border-bottom:1px solid rgba(74,73,65,50); padding:0 4px;}
    QTableWidget#recentWords::item:focus {border:1px solid #76766d;}
    QHeaderView::section {background:transparent; color:#55554e; font-size:12px; padding:3px 4px;
        border:0; border-bottom:1px solid #a7a69e;}
    QLabel#homeWarning {background:rgba(250,249,246,220); color:#862d21; padding:3px 7px;}
"""


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
        outer.addStretch(1)
        self.page = QVBoxLayout(self.column)
        self.page.setSpacing(9)
        self.summary = QVBoxLayout()
        self.summary.setSpacing(2)
        self.page.addLayout(self.summary)
        self.summary.addWidget(QLabel("累计查词", objectName="totalLabel"))
        amount = QHBoxLayout()
        amount.setSpacing(7)
        self.total = QLabel("—", objectName="totalValue")
        self.total.setAccessibleName("累计查词次数")
        amount.addWidget(self.total)
        unit = QLabel("次", objectName="metricUnit")
        unit.setContentsMargins(0, 0, 0, 8)
        amount.addWidget(unit, 0, Qt.AlignBottom)
        amount.addStretch()
        self.summary.addLayout(amount)
        self.activity = QLabel(objectName="activity")
        self.summary.addWidget(self.activity)
        self.art_space = QSpacerItem(0, 3, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.page.addSpacerItem(self.art_space)
        bar = QFrame(objectName="guideBar")
        self.tools = QHBoxLayout(bar)
        self.tools.setSpacing(8)
        self.instructions = QPushButton(objectName="useHint")
        self.instructions.setToolTip("更改取词键")
        self.instructions.setCursor(Qt.PointingHandCursor)
        self.instructions.clicked.connect(self.settings_requested)
        self.tools.addWidget(self.instructions, 0, Qt.AlignLeft)
        self.tools.addStretch()
        self.region = QPushButton(ui_icon("region"), "框选翻译", objectName="region")
        self.region.setIconSize(QSize(16, 16))
        self.region.setCursor(Qt.PointingHandCursor)
        self.region.clicked.connect(self.region_requested)
        self.tools.addWidget(self.region)
        self.page.addWidget(bar)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        self.page.addWidget(self.warning)
        self.sheet = QFrame(objectName="recentSheet")
        self.page.addWidget(self.sheet, 1)
        self.page.addStretch()
        self.history = QVBoxLayout(self.sheet)
        self.history.setSpacing(7)
        self.history.addWidget(QLabel("最近查词", objectName="recentTitle"))
        self.contents = QStackedLayout()
        self.history.addLayout(self.contents, 1)

        self.empty = QLabel(objectName="emptyHistory")
        self.empty.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.contents.addWidget(self.empty)
        self.table = QTableWidget(0, 3, objectName="recentWords")
        self.table.setAccessibleName("最近查词，从新到旧")
        self.table.setHorizontalHeaderLabels(["词语", "释义", "语种"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.viewport().setAutoFillBackground(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(39)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setHighlightSections(False)
        header.viewport().setAutoFillBackground(False)
        self.contents.addWidget(self.table)
        self.rows = []
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")
        self.empty.setText("正在读取查词记录…")
        self.arrange()

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        hint = f"指向单词轻按{key}查词，按住拖选可翻译一段。" if key else "在「对照翻译」双击单词查词，或点「框选翻译」。"
        self.instructions.setText(hint)
        self.instructions.setAccessibleName(hint + " 点击更改取词键。")

    def set_stats(self, snapshot):
        if snapshot is None:
            self.total.setText("—")
            self.activity.clear()
            self.empty.setText("暂时无法读取查词记录")
            recent = []
        else:
            total, today, saved, due, recent = snapshot
            self.total.setText(f"{total:,}")
            self.activity.setText(f"今日 {today:,} 次     ·     已收藏 {saved:,}     ·     待复习 {due:,}")
            self.empty.setText("还没有查词记录")
        self.contents.setCurrentWidget(self.table if recent else self.empty)
        self.sheet.setMaximumHeight(90 + len(recent) * self.table.verticalHeader().defaultSectionSize())
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
                item.setForeground(QColor(("#181816", "#363632", "#484841")[column]))
                self.table.setItem(row, column, item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        compact = self.width() < 720
        margin = 14 if compact else 30
        width = min(self.width(), max(467, min(740, round(self.width() * 0.58))))
        self.column.setFixedWidth(width)
        # In a tall window leave the portrait visible above the history sheet.
        gap = max(3, min(240, round((self.height() - self.width()) * 0.85))) if compact else 3
        self.art_space.changeSize(0, gap, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.page.invalidate()
        self.page.setContentsMargins(margin, 14 if compact else 26, 6, 14)
        self.tools.setContentsMargins(9, 4, 6, 4)
        self.history.setContentsMargins(14, 10, 14, 9)
        self.table.setColumnWidth(0, max(96, min(158, width // 4)))
        self.table.setColumnWidth(2, 62 if compact else 72)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
