"""Windows lookup dashboard."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from languages import NAMES
from theme import ui_icon


COVER = Path(__file__).resolve().parents[1] / "Assets/Editorial/glance.png"
HOME_STYLE = """
    QWidget#home {background:#faf9f6;}
    QLabel#totalLabel {color:#464641; font-size:15px; font-weight:500;}
    QLabel#totalValue {font:600 48px 'Segoe UI'; color:#151514;}
    QLabel#metricUnit {font-size:16px; color:#565650;}
    QLabel#activity {font-size:13px; color:#484842;}
    QFrame#guideBar {background:#f2f1eb; border-top:1px solid #bdbcb5; border-bottom:1px solid #cecdc6;}
    QPushButton#useHint {background:transparent; color:#44443e; border:1px solid transparent;
        font-size:13px; text-align:left; padding:3px 0;}
    QPushButton#useHint:focus, QPushButton#useHint:hover {border-bottom:1px solid #565650;}
    QPushButton#region {background:transparent; border:1px solid #a09f97; border-radius:3px;
        padding:3px 9px; font-size:13px; color:#272724;}
    QPushButton#region:focus, QPushButton#region:hover {background:#e6e5de; border-color:#54544e;}
    QLabel#recentTitle {font-size:20px; font-weight:600;}
    QLabel#emptyHistory {color:#696962; font-size:14px;}
    QTableWidget#recentWords {background:#faf9f6; border:0; outline:0;
        selection-background-color:#e4e3dc; selection-color:#171715;}
    QTableWidget#recentWords::item {border:0; border-bottom:1px solid #dddbd5; padding:0 6px;}
    QTableWidget#recentWords::item:focus {border:1px solid #76766d;}
    QHeaderView::section {background:#faf9f6; color:#686861; font-size:12px; padding:3px 6px;
        border:0; border-bottom:1px solid #a7a69e;}
    QLabel#homeWarning {color:#862d21; padding:3px 14px;}
"""


class Portrait(QWidget):
    def __init__(self):
        super().__init__()
        self.image = QPixmap(str(COVER))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

    def paintEvent(self, event):
        if self.image.isNull():
            return
        # Keep the eye in view as the dashboard banner changes proportions.
        w, h = self.image.width(), self.image.height()
        scale = max(self.width() / w, self.height() / h)
        crop_w, crop_h = self.width() / scale, self.height() / scale
        x = max(0, min(w - crop_w, w * 0.72 - crop_w * 0.54))
        y = max(0, min(h - crop_h, h * 0.31 - crop_h * 0.46))
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(self.rect()), self.image, QRectF(x, y, crop_w, crop_h))
            painter.fillRect(0, 0, 1, self.height(), QColor("#393933"))


class HomePage(QWidget):
    region_requested = Signal()
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="home")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(HOME_STYLE)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        self.banner = QWidget()
        hero = QHBoxLayout(self.banner)
        hero.setContentsMargins(0, 0, 0, 0)
        hero.setSpacing(0)
        metrics = QWidget()
        self.summary = QVBoxLayout(metrics)
        self.summary.setSpacing(2)
        self.summary.addStretch()
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
        self.summary.addStretch()
        hero.addWidget(metrics, 55)
        self.portrait = Portrait()
        hero.addWidget(self.portrait, 45)
        page.addWidget(self.banner)

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
        page.addWidget(bar)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        page.addWidget(self.warning)
        self.history = QVBoxLayout()
        self.history.setSpacing(7)
        self.history.addWidget(QLabel("最近查词", objectName="recentTitle"))
        self.contents = QStackedLayout()
        self.history.addLayout(self.contents, 1)
        page.addLayout(self.history, 1)

        self.empty = QLabel(objectName="emptyHistory")
        self.empty.setAlignment(Qt.AlignCenter)
        self.contents.addWidget(self.empty)
        self.table = QTableWidget(0, 3, objectName="recentWords")
        self.table.setAccessibleName("最近查词，从新到旧")
        self.table.setHorizontalHeaderLabels(["词语", "释义", "语种"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(39)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setHighlightSections(False)
        self.contents.addWidget(self.table)
        self.rows = []
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")
        self.empty.setText("正在读取查词记录…")
        self.arrange()

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        hint = f"指向单词，轻按{key}查词；按住并拖选可翻译一段。" if key else "在阅读页双击单词查词，或点「框选翻译」翻译一段。"
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
                item.setForeground(QColor(("#181816", "#363632", "#696962")[column]))
                self.table.setItem(row, column, item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        compact = self.width() < 720
        margin = 18 if compact else 32
        self.banner.setFixedHeight(130 if compact else 170)
        self.summary.setContentsMargins(margin, 4, 8, 6)
        self.tools.setContentsMargins(margin, 6, margin, 6)
        self.history.setContentsMargins(margin, 14 if compact else 21, margin, 12)
        self.table.setColumnWidth(0, max(106, min(242, self.width() // 4)))
        self.table.setColumnWidth(2, 76 if compact else 96)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
