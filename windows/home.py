"""The Windows home screen, with an interactive example of the active lookup gesture."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from theme import STATIONERY


HOME_EXAMPLE = "They sat on the river bank."

HOME_STYLE = """
    QPushButton#gestureSettings {color:#653e31; background:#faf2df; border:1px solid #b9a480;
        border-radius:3px; padding:5px 11px; font-size:12px;}
    QPushButton#gestureSettings:hover {background:#eedfc2; border-color:#927348;}
    QLabel#gestureHeadline {font: bold 38px 'SimSun','Microsoft YaHei UI'; color:#402c23;}
    QLabel#keyVerb {font:19px 'SimSun','Microsoft YaHei UI'; color:#604937;}
    QLabel#gestureKey {color:#fff4dd; background:#813d35; border:1px solid #73372e;
        border-bottom:3px solid #5d2c25; border-radius:4px; padding:1px 9px;
        font-size:17px; font-weight:600;}
    QLabel#heroDescription {color:#675342; font-size:13px;}
    QFrame#sampleRule {background:#bfa782; border:0;}
    QLabel#homeExample, QPushButton#trialWord {font-family:'Spectral','Georgia';
        font-size:23px; color:#49342a; background:transparent; border:0;}
    QPushButton#trialWord {color:#79362e; background:#eedbb6; border-bottom:2px solid #874438;
        border-radius:1px; padding:0 3px; min-height:0; font-weight:600;}
    QPushButton#trialWord:hover {background:#e5c994;}
    QPushButton#homeRead {color:#fff3dd; background:#803c34; border:1px solid #70332d;
        border-radius:3px; margin-top:10px; padding:5px 13px; font-weight:600;}
    QPushButton#homeRead:hover {background:#934b40;}
    QLabel#homeWarning {color:#913a23; font-size:12px;}
    QFrame#regionStrip {background:#ecdfc3; border:1px solid #c6af89; border-radius:3px;}
    QLabel#regionTitle {color:#493127; font-size:15px; font-weight:650;}
    QLabel#regionHint, QLabel#metricCaption {color:#685441; font-size:12px;}
    QPushButton#homeRegion {color:#5a392a; background:#faf1db; border:1px solid #b39a75;
        border-radius:3px; padding:5px 12px; font-weight:600;}
    QPushButton#homeRegion:hover {color:#492a20; background:#fff6e1; border-color:#937249;}
    QLabel#recordHeading {color:#483126; font:bold 20px 'SimSun','Microsoft YaHei UI';}
    QFrame#homeMetrics {background:transparent; border:0; border-bottom:3px double #bda883;}
    QFrame#metricDivider {background:#cdb999; border:0; min-width:1px; max-width:1px;}
    QLabel#metricNumber {color:#61372d; font:600 39px 'Spectral','Georgia';}
    QPushButton#gestureSettings:focus, QPushButton#homeRegion:focus, QPushButton#trialWord:focus {
        border:1px solid #893e33;}
    QPushButton#homeRead:focus {border-color:#dab675;}
"""


class HeroPanel(QFrame):
    """A printed plate with space reserved for the interactive text on its left."""
    def __init__(self):
        super().__init__()
        self.river = QPixmap(str(STATIONERY / "riverbank.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect())
        painter.fillRect(area, QColor("#fbf2dc"))
        width, height = area.width(), area.height()
        # Leave the live sentence and controls clear at every breakpoint.
        art_width = min(width * 0.56, width - self.layout().sizeHint().width() + 4)
        if art_width >= 115 and not self.river.isNull():
            scale = min(art_width / self.river.width(), (height - 18) / self.river.height())
            w, h = self.river.width() * scale, self.river.height() * scale
            target = QRectF(width - w - 9, (height - h) / 2, w, h)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(target, self.river, QRectF(self.river.rect()))

        painter.setBrush(Qt.NoBrush)
        for inset, ink in ((0.5, "#ab906b"), (5.5, "#cbb594")):
            painter.setPen(QPen(QColor(ink), 1))
            painter.drawRect(area.adjusted(inset, inset, -inset, -inset))
        painter.setBrush(QColor("#a38359"))
        painter.setPen(Qt.NoPen)
        for x in (6, width - 6):
            for y in (6, height - 6):
                painter.drawPolygon(QPolygonF([QPointF(x, y - 3), QPointF(x + 3, y),
                                               QPointF(x, y + 3), QPointF(x - 3, y)]))


class RegionMark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(34, 34)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dcc59f"))
        painter.drawRoundedRect(QRectF(0, 0, 34, 34), 4, 4)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#6b4632"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
        header.setSpacing(14)
        header.addWidget(QFrame(objectName="hairline"), 1)
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
        record = QHBoxLayout()
        record.setSpacing(12)
        record.addWidget(QLabel("学习记录", objectName="recordHeading"))
        record.addWidget(QFrame(objectName="hairline"), 1)
        layout.addLayout(record)
        layout.addSpacing(8)
        stats = QFrame(objectName="homeMetrics")
        metrics = QHBoxLayout(stats)
        metrics.setContentsMargins(3, 4, 1, 12)
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
            margin = 14 if compact else 30
            self.widget().layout().setContentsMargins(margin, 14 if compact else 20, margin, 18)
            inset = 20 if compact else 30
            self.hero.layout().setContentsMargins(inset, 17 if compact else 23, inset, 18 if compact else 23)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
