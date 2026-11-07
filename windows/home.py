"""The Windows reader's first screen: try the active gesture and see local learning activity."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from theme import label


HOME_EXAMPLE = "They sat on the river bank."


class HomePage(QScrollArea):
    demo_requested = Signal()
    region_requested = Signal()
    reader_requested = Signal()
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="lookupHome")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)
        self.compact = None
        surface = QWidget(objectName="home")
        self.setWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(26, 23, 26, 19)
        layout.setSpacing(0)

        self.hero = QFrame(objectName="gesturePanel")
        panel = QVBoxLayout(self.hero)
        panel.setContentsMargins(20, 13, 20, 20)
        panel.setSpacing(8)
        top = QHBoxLayout()
        self.guide_title = label("", "homeSection")
        top.addWidget(self.guide_title)
        top.addStretch()
        self.settings_link = QPushButton("取词键设置")
        self.settings_link.setProperty("role", "quiet")
        self.settings_link.clicked.connect(self.settings_requested)
        top.addWidget(self.settings_link)
        panel.addLayout(top)

        title = QHBoxLayout()
        title.setSpacing(8)
        self.headline = label("", "gestureHeadline")
        self.headline.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        title.addWidget(self.headline)
        self.keycap = label("", "gestureKey")
        self.keycap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title.addWidget(self.keycap)
        title.addStretch()
        panel.addLayout(title)
        self.description = label("", "gestureDescription")
        self.description.setWordWrap(True)
        panel.addWidget(self.description)
        panel.addSpacing(6)

        self.sample = QFrame(objectName="gestureSample")
        example = QHBoxLayout(self.sample)
        example.setContentsMargins(13, 9, 13, 9)
        example.setSpacing(0)
        before, word, after = HOME_EXAMPLE.partition("bank")
        example.addWidget(label(before, "exampleText"))
        self.demo = QPushButton(word, objectName="sampleWord")
        self.demo.setAccessibleName("试查 bank")
        self.demo.clicked.connect(self.demo_requested)
        example.addWidget(self.demo)
        example.addWidget(label(after, "exampleText"))
        example.addStretch()
        panel.addWidget(self.sample)
        self.reader = QPushButton("打开阅读页")
        self.reader.setProperty("role", "primary")
        self.reader.clicked.connect(self.reader_requested)
        panel.addWidget(self.reader, 0, Qt.AlignLeft)
        self.warning = label("", "warning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        panel.addWidget(self.warning)
        layout.addWidget(self.hero)

        layout.addSpacing(18)
        region_row = QHBoxLayout()
        region_text = QVBoxLayout()
        region_text.setSpacing(3)
        region_text.addWidget(label("整段翻译", "subhead"))
        self.region_hint = label("", "meta")
        self.region_hint.setWordWrap(True)
        region_text.addWidget(self.region_hint)
        region_row.addLayout(region_text, 1)
        self.region = QPushButton("开始框选")
        self.region.clicked.connect(self.region_requested)
        region_row.addWidget(self.region, 0, Qt.AlignVCenter)
        layout.addLayout(region_row)

        layout.addSpacing(22)
        layout.addWidget(label("学习记录", "homeSection"))
        layout.addSpacing(8)
        stats = QFrame(objectName="homeStats")
        metrics = QHBoxLayout(stats)
        metrics.setContentsMargins(4, 12, 4, 12)
        metrics.setSpacing(0)
        self.values = []
        for caption in ("今日查词", "已收藏", "待复习"):
            if self.values:
                metrics.addWidget(QFrame(objectName="metricDivider"))
            column = QVBoxLayout()
            column.setContentsMargins(14, 0, 5, 0)
            column.setSpacing(2)
            value = label("—", "metricValue")
            value.setAccessibleName(caption)
            column.addWidget(value)
            column.addWidget(label(caption, "meta"))
            metrics.addLayout(column, 1)
            self.values.append(value)
        layout.addWidget(stats)
        layout.addStretch()

        for button in (self.demo, self.reader, self.settings_link, self.region):
            button.setCursor(Qt.PointingHandCursor)
        self.refresh = QTimer(self)
        self.refresh.setInterval(30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.keycap.setVisible(bool(key))
        self.sample.setVisible(bool(key))
        self.reader.setVisible(not key)
        if key:
            self.guide_title.setText("悬停查词")
            self.headline.setText("鼠标指向单词，轻按")
            self.keycap.setText(key)
            self.description.setText("在网页或 PDF 中看句中释义。试试下面的 bank。")
            self.demo.setToolTip(f"指向 bank，轻按{key}或点击查看句中释义")
            self.region_hint.setText(f"按住{key}，用鼠标左键拖选原文。")
        else:
            self.guide_title.setText("仅应用内查词")
            self.headline.setText("粘贴文章，单击查词")
            self.description.setText("在阅读页粘贴英文，点一个词就能看到句中释义。")
            self.region_hint.setText("点击「开始框选」，拖选屏幕上的原文。")

    def set_stats(self, today, saved, due):
        for display, value in zip(self.values, (today, saved, due)):
            display.setText("—" if value is None else f"{value:,}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 470
        if compact != self.compact:
            self.compact = compact
            margin = 12 if compact else 26
            self.widget().layout().setContentsMargins(margin, 16 if compact else 23, margin, 19)
            inset = 12 if compact else 20
            self.hero.layout().setContentsMargins(inset, 13, inset, inset)
            self.headline.setStyleSheet("font-size:20px;" if compact else "")
            self.keycap.setStyleSheet("font-size:17px; padding:0 6px;" if compact else "")

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
