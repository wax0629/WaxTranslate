"""The Windows home screen, with an interactive example of the active lookup gesture."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


HOME_EXAMPLE = "They sat on the river bank."
PORTRAIT = Path(__file__).resolve().parent.parent / "Assets" / "Brand" / "barrette.svg"

HOME_STYLE = """
    QScrollArea#lookupHome, QWidget#home {background:#faf9f5; border:0;}
    QLabel#pageTitle {color:#193b32; font-size:27px; font-weight:650;}
    QPushButton#gestureSettings {background:transparent; color:#4e655a; border:1px solid #d6dfd3;
        border-radius:7px; padding:5px 11px; font-size:12px;}
    QPushButton#gestureSettings:hover {background:#eaf0e7; border-color:#8da590;}
    QLabel#gestureHeadline {font-size:32px; color:#faf7eb; font-weight:650;}
    QLabel#keyVerb {font-size:24px; color:#faf7eb; font-weight:600;}
    QLabel#gestureKey {color:#253a2b; background:#f6ebbc; border:1px solid #faf4d4;
        border-bottom:3px solid #c8ba85; border-radius:7px; padding:0 9px 1px;
        font-size:19px; font-weight:650;}
    QLabel#heroDescription {color:#d3e3d7; font-size:13px;}
    QFrame#sampleRule {background:#668476; max-height:1px; border:0;}
    QLabel#homeExample, QPushButton#trialWord {font-family:'Spectral','Georgia';
        font-size:23px; color:#f7f3e7; background:transparent; border:0;}
    QPushButton#trialWord {color:#f9e7aa; background:#38594a; border:1px solid #64785a;
        border-bottom:2px solid #d9c582; border-radius:4px; padding:0 3px; min-height:0;}
    QPushButton#trialWord:hover {background:#496750; color:#fff4c4;}
    QPushButton#homeRead {background:#f6ebbc; color:#273c2e; border:1px solid #f6ebbc;
        border-radius:6px; margin-top:10px; padding:5px 13px; font-weight:600;}
    QPushButton#homeRead:hover {background:#ffefb3;}
    QLabel#homeWarning {color:#913a23; font-size:12px;}
    QFrame#regionStrip {background:#f0f2eb; border:1px solid #dce2d7; border-radius:11px;}
    QLabel#regionTitle {color:#203d32; font-size:15px; font-weight:650;}
    QLabel#regionHint, QLabel#metricCaption {color:#5b6b60; font-size:12px;}
    QPushButton#homeRegion {background:#fdfcf8; color:#254735; border:1px solid #ccd6ca;
        border-radius:7px; padding:5px 12px; font-weight:600;}
    QPushButton#homeRegion:hover {color:#163b28; border-color:#8da590; background:#fff;}
    QLabel#recordHeading {color:#213a30; font-size:17px; font-weight:650;}
    QFrame#homeMetrics {background:transparent; border:0; border-top:1px solid #d9ded2;}
    QFrame#metricDivider {background:#e3e3d9; border:0; min-width:1px; max-width:1px;}
    QLabel#metricNumber {color:#223d30; font-family:'Spectral','Georgia'; font-size:39px; font-weight:600;}
    QPushButton#gestureSettings:focus, QPushButton#homeRegion:focus {border-color:#346b58;}
    QPushButton#trialWord:focus, QPushButton#homeRead:focus {border:2px solid #fff2bb;}
"""


class HeroPanel(QFrame):
    """Paint the brand illustration behind the controls, inside the rounded cover."""
    def __init__(self):
        super().__init__()
        self.portrait = QPixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect())
        outline = QPainterPath()
        outline.addRoundedRect(area, 14, 14)
        painter.setClipPath(outline)
        width, height = area.width(), area.height()
        background = QLinearGradient(0, 0, width, height)
        background.setColorAt(0, QColor("#153a30"))
        background.setColorAt(1, QColor("#285044"))
        painter.fillRect(area, background)

        # The same portrait is a book-cover crop on wide windows and a smaller
        # bust on medium widths. At the narrowest size the text takes the full cover.
        art_width = min(width * 0.39, width - 284)
        if art_width < 115:
            return
        painter.setClipRect(QRectF(width - art_width, 0, art_width, height), Qt.IntersectClip)
        diameter = min(art_width * 0.93, height * 1.13)
        center = QPointF(width - art_width * 0.43, height * 0.48)
        painter.setPen(QPen(QColor("#69816c"), 0.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, diameter * 0.56, diameter * 0.56)
        painter.setPen(Qt.NoPen)
        sun = QLinearGradient(0, 0, 0, height)
        sun.setColorAt(0, QColor("#efdfa6"))
        sun.setColorAt(1, QColor("#c4bd85"))
        painter.setBrush(sun)
        painter.drawEllipse(center, diameter / 2, diameter / 2)

        # One small patch of screen tone echoes the pen-and-ink source.
        painter.setBrush(QColor("#8b946c"))
        for y in range(8):
            for x in range(8 - y):
                painter.drawEllipse(QPointF(width - 12 - x * 5, 13 + y * 5), 0.8, 0.8)

        ratio = self.devicePixelRatioF()
        if self.portrait.isNull() or self.portrait.devicePixelRatio() != ratio:
            side = round(400 * ratio)
            self.portrait = QPixmap(side, side)
            self.portrait.setDevicePixelRatio(ratio)
            self.portrait.fill(Qt.transparent)
            with QPainter(self.portrait) as ink:
                QSvgRenderer(str(PORTRAIT)).render(ink, QRectF(0, 0, 400, 400))
                ink.setCompositionMode(QPainter.CompositionMode_SourceAtop)
                ink.fillRect(QRectF(0, 0, 400, 400), QColor(215, 199, 147, 14))
        side = min(art_width * 1.12, height * 1.20)
        target = QRectF(width - art_width * 0.45 - side / 2, height - side * 0.91, side, side)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(target, self.portrait, QRectF(self.portrait.rect()))


class RegionMark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(34, 34)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dce8d9"))
        painter.drawRoundedRect(QRectF(0, 0, 34, 34), 8, 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#486d55"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for x, dx in ((9, 4), (25, -4)):
            for y, dy in ((10, 4), (24, -4)):
                painter.drawPolyline([QPointF(x + dx, y), QPointF(x, y), QPointF(x, y + dy)])
        painter.drawLine(13, 15, 21, 15)
        painter.drawLine(13, 19, 18, 19)


class HomePage(QScrollArea):
    demo_requested = Signal()
    region_requested = Signal()
    reader_requested = Signal()
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="lookupHome")
        self.setStyleSheet(HOME_STYLE)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)
        self.compact = None
        surface = QWidget(objectName="home")
        self.setWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(28, 20, 28, 22)
        layout.setSpacing(0)
        header = QHBoxLayout()
        self.guide_title = QLabel(objectName="pageTitle")
        header.addWidget(self.guide_title)
        header.addStretch()
        self.settings_link = QPushButton("取词键设置", objectName="gestureSettings")
        self.settings_link.clicked.connect(self.settings_requested)
        header.addWidget(self.settings_link)
        layout.addLayout(header)
        layout.addSpacing(14)

        self.hero = HeroPanel()
        panel = QVBoxLayout(self.hero)
        panel.setContentsMargins(24, 20, 24, 20)
        panel.setSpacing(0)
        panel.addStretch()
        self.headline = QLabel(objectName="gestureHeadline")
        panel.addWidget(self.headline, 0, Qt.AlignLeft)
        action = QHBoxLayout()
        action.setSpacing(9)
        self.key_verb = QLabel("轻按", objectName="keyVerb")
        action.addWidget(self.key_verb)
        self.keycap = QLabel(objectName="gestureKey")
        action.addWidget(self.keycap)
        action.addStretch()
        panel.addSpacing(6)
        panel.addLayout(action)
        self.description = QLabel(objectName="heroDescription")
        panel.addSpacing(12)
        panel.addWidget(self.description, 0, Qt.AlignLeft)

        self.sample = QWidget()
        sample = QVBoxLayout(self.sample)
        sample.setContentsMargins(0, 17, 0, 0)
        sample.setSpacing(8)
        rule = QFrame(objectName="sampleRule")
        rule.setFixedSize(202, 1)
        sample.addWidget(rule)
        example = QHBoxLayout()
        example.setSpacing(0)
        before, word, after = HOME_EXAMPLE.partition("bank")
        example.addWidget(QLabel(before, objectName="homeExample"))
        self.demo = QPushButton(word, objectName="trialWord")
        self.demo.setAccessibleName("试查 bank")
        self.demo.clicked.connect(self.demo_requested)
        example.addWidget(self.demo)
        example.addWidget(QLabel(after, objectName="homeExample"))
        example.addStretch()
        sample.addLayout(example)
        panel.addWidget(self.sample)
        self.reader = QPushButton("打开阅读页", objectName="homeRead")
        self.reader.clicked.connect(self.reader_requested)
        panel.addWidget(self.reader, 0, Qt.AlignLeft)
        panel.addStretch()
        layout.addWidget(self.hero)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        layout.addWidget(self.warning)
        layout.addSpacing(14)
        strip = QFrame(objectName="regionStrip")
        region = QHBoxLayout(strip)
        region.setContentsMargins(16, 13, 16, 13)
        region.setSpacing(10)
        region.addWidget(RegionMark())
        wording = QVBoxLayout()
        wording.setSpacing(1)
        wording.addWidget(QLabel("整段翻译", objectName="regionTitle"))
        self.region_hint = QLabel(objectName="regionHint")
        self.region_hint.setWordWrap(True)
        wording.addWidget(self.region_hint)
        region.addLayout(wording, 1)
        self.region = QPushButton("开始框选", objectName="homeRegion")
        self.region.clicked.connect(self.region_requested)
        region.addWidget(self.region)
        layout.addWidget(strip)

        layout.addSpacing(25)
        layout.addWidget(QLabel("学习记录", objectName="recordHeading"))
        layout.addSpacing(8)
        stats = QFrame(objectName="homeMetrics")
        metrics = QHBoxLayout(stats)
        metrics.setContentsMargins(0, 15, 0, 16)
        metrics.setSpacing(0)
        self.values = []
        for caption in ("今日查词", "已收藏", "待复习"):
            if self.values:
                metrics.addWidget(QFrame(objectName="metricDivider"))
            column = QVBoxLayout()
            column.setContentsMargins(16 if self.values else 0, 0, 5, 0)
            column.setSpacing(4)
            value = QLabel("—", objectName="metricNumber")
            value.setAccessibleName(caption)
            column.addWidget(value)
            column.addWidget(QLabel(caption, objectName="metricCaption"))
            metrics.addLayout(column, 1)
            self.values.append(value)
        layout.addWidget(stats)
        layout.addStretch()

        for button in (self.settings_link, self.demo, self.reader, self.region):
            button.setCursor(Qt.PointingHandCursor)
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.keycap.setVisible(bool(key))
        self.key_verb.setVisible(bool(key))
        self.sample.setVisible(bool(key))
        self.reader.setVisible(not key)
        if key:
            self.guide_title.setText("悬停查词")
            self.headline.setText("鼠标指向单词")
            self.keycap.setText(key)
            self.description.setText("在网页和 PDF 中看句中释义。")
            self.demo.setToolTip(f"指向 bank，轻按{key}或点击查看句中释义")
            self.region_hint.setText(f"按住{key}，用鼠标左键拖选原文。")
        else:
            self.guide_title.setText("仅应用内查词")
            self.headline.setText("单击查词")
            self.description.setText("在阅读页粘贴英文，点词看释义。")
            self.region_hint.setText("点击「开始框选」，拖选屏幕上的原文。")

    def set_stats(self, today, saved, due):
        for display, value in zip(self.values, (today, saved, due)):
            display.setText("—" if value is None else f"{value:,}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 520
        height = 270 if self.viewport().height() >= 575 else 224
        self.hero.setMinimumHeight(196 if compact else height)
        if compact != self.compact:
            self.compact = compact
            margin = 14 if compact else 28
            self.widget().layout().setContentsMargins(margin, 14 if compact else 20, margin, 18)
            inset = 16 if compact else 24
            self.hero.layout().setContentsMargins(inset, 17 if compact else 23, inset, 18 if compact else 23)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
