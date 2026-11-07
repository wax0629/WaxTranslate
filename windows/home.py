"""Interactive manga dictionary cover and live notebook counts."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from theme import ui_icon


HOME_WORD = "glance"
HOME_EXAMPLE = "She turned back for one last glance."
COVER = Path(__file__).resolve().parents[1] / "Assets/Editorial/glance.png"

HOME_STYLE = """
    QWidget#home, QFrame#actionStrip {background:#faf9f6;}
    QFrame#actionStrip {border:0; border-top:2px solid #171715;}
    QPushButton#trialWord {background:transparent; border:0; padding:0;}
    QPushButton#trialWord:hover, QPushButton#trialWord:focus {border-bottom:2px solid #181816;}
    QPushButton#tryMeaning {background:#121211; color:#ffffff; border:2px solid #121211;
        border-radius:0; font-weight:bold; text-align:center; padding:2px 8px;}
    QPushButton#tryMeaning:hover {background:#393937;}
    QPushButton#tryMeaning:focus {border-color:#777772;}
    QPushButton#coverKey {background:#faf9f6; color:#171715; border:1px solid #262624;
        border-radius:3px; padding:2px 7px; font-weight:600;}
    QPushButton#coverKey:hover, QPushButton#coverKey:focus {background:#e8e7e3; border-color:#080808;}
    QPushButton[role="stripAction"] {background:transparent; border:1px solid transparent;
        border-radius:0; color:#191917; text-align:left; padding:4px 7px; font-weight:600; font-size:15px;}
    QPushButton[role="stripAction"]:hover {background:#eae9e5;}
    QPushButton[role="stripAction"]:focus {border-color:#393937;}
    QFrame#stripDivider {background:#888882; border:0;}
    QLabel#metricCaption {font-size:14px; color:#353532;}
    QLabel#metricValue {font:22px 'Archivo Black','Arial Black'; color:#141413;}
    QLabel#homeWarning {background:#faf9f6; color:#862d21; padding:4px 16px;}
"""


class Cover(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(306)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.portrait = QPixmap(str(COVER))
        font = QFont("Archivo Black")
        font.setPixelSize(140)
        letters = QPainterPath()
        letters.addText(0, 0, font, HOME_WORD.upper())
        self.lettering = letters

        # The lettering is composited with the ink below it. A native button
        # over exactly the same rectangle handles focus, keyboard and hit tests.
        self.demo = QPushButton(self, objectName="trialWord")
        self.demo.setAccessibleName("试查 glance")
        self.phonetic = QLabel("/ɡlæns/   n.", self)
        self.meaning = QLabel("一瞥", self)
        self.sentence = QLabel(HOME_EXAMPLE.replace(HOME_WORD, f"<u>{HOME_WORD}</u>"), self)
        self.sentence.setAccessibleName(HOME_EXAMPLE)
        self.sentence.setWordWrap(True)
        self.trial = QPushButton(ui_icon("launch", "#ffffff"), "试查词义", self, objectName="tryMeaning")
        self.trial.setLayoutDirection(Qt.RightToLeft)
        self.keycap = QPushButton(self, objectName="coverKey")
        self.keycap.setToolTip("更改屏幕取词键")

    def art_rect(self):
        # On a tall, narrow desktop the illustration occupies the top of
        # the page, leaving a paper band below for the definition and controls.
        w, h = self.width(), self.height()
        if w < h * 1.15:
            return QRectF(0, 0, w, min(w * 0.72, h - 210))
        return QRectF(self.rect())

    def paintEvent(self, event):
        area = self.art_rect()
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), QColor("#faf8f4"))
            if not self.portrait.isNull():
                scale = max(area.width() / self.portrait.width(), area.height() / self.portrait.height())
                w, h = area.width() / scale, area.height() / scale
                crop = QRectF((self.portrait.width() - w) * 0.56, (self.portrait.height() - h) * 0.30, w, h)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawPixmap(area, self.portrait, crop)
            box = QRectF(self.demo.geometry()).adjusted(1, 2, -1, -2)
            ink = self.lettering.boundingRect()
            painter.setRenderHint(QPainter.Antialiasing)
            slant = 0.20
            painter.translate(box.x() + slant * box.height(), box.y())
            painter.shear(-slant, 0)
            painter.scale((box.width() - slant * box.height()) / ink.width(), box.height() / ink.height())
            painter.translate(-ink.topLeft())
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
            painter.fillPath(self.lettering, Qt.white)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_entry()

    def layout_entry(self):
        w, h = self.width(), self.height()
        inset = max(17, min(54, round(w * 0.037)))
        art = self.art_rect()
        stacked = art.height() < h
        if stacked:
            title_y, title_h = round(art.height() * 0.17), round(art.height() * 0.32)
            baseline = round(art.height()) + 8
            unit = min(1.25, max(0.7, (h - baseline) / 258))
        else:
            title_y, title_h = round(h * 0.13), round(h * 0.34)
            baseline = title_y + title_h + max(4, round(h * 0.02))
            unit = min(1.65, w / 1000, h / 535)
        self.demo.setGeometry(inset - 3, title_y, round(min(w * 0.465, title_h * 3.0)), title_h)
        measure = w - 2 * inset if stacked else round(w * 0.39)

        def line(widget, y, family, pixels, weight="normal"):
            size = max(12, round(pixels * unit))
            widget.setStyleSheet(f"color:#151513; font:{weight} {size}px {family};")
            height = widget.sizeHint().height()
            widget.setGeometry(inset, y, measure, height)
            return y + height

        y = line(self.phonetic, baseline, "'Consolas','Courier New'", 22)
        y = line(self.meaning, y + round(3 * unit), "'Noto Serif SC Black','Noto Serif SC','SimSun'", 61, "900")
        # Fit the example on the paper beside the face at any window ratio.
        sentence_size = max(13, round(24 * unit))
        font = QFont("Spectral")
        font.setPixelSize(sentence_size)
        width = QFontMetrics(font).horizontalAdvance(HOME_EXAMPLE)
        sentence_size = max(16, min(sentence_size, int(sentence_size * (measure - 3) / max(1, width))))
        self.sentence.setStyleSheet(f"color:#171715; font:{sentence_size}px 'Spectral','Georgia';")
        self.sentence.setGeometry(inset, y + round(3 * unit), measure, self.sentence.heightForWidth(measure))
        y = self.sentence.geometry().bottom() + max(8, round(15 * unit))
        button_h = max(29, min(64, round(44 * unit)))
        self.trial.setStyleSheet(f"font-size:{max(13, round(18 * unit))}px;")
        self.trial.setIconSize(QSize(round(button_h * 0.48), round(button_h * 0.48)))
        self.trial.setGeometry(inset, y, max(102, round(155 * unit)), button_h)
        key_h = max(25, round(button_h * 0.77))
        self.keycap.setStyleSheet(f"font-size:{max(12, round(15 * unit))}px;")
        self.keycap.setGeometry(self.trial.geometry().right() + max(10, round(15 * unit)),
                                y + (button_h - key_h) // 2, self.keycap.sizeHint().width() + 2, key_h)


class HomePage(QScrollArea):
    demo_requested = Signal()
    region_requested = Signal()
    reader_requested = Signal()
    settings_requested = Signal()
    library_requested = Signal()
    stats_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="lookupHome")
        self.setStyleSheet(HOME_STYLE)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)
        surface = QWidget(objectName="home")
        self.setWidget(surface)
        page = QVBoxLayout(surface)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        self.hero = Cover()
        page.addWidget(self.hero, 1)
        self.demo = self.hero.demo
        self.keycap = self.hero.keycap
        self.demo.clicked.connect(self.demo_requested)
        self.hero.trial.clicked.connect(self.demo_requested)
        self.keycap.clicked.connect(self.settings_requested)
        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        page.addWidget(self.warning)

        strip = QFrame(objectName="actionStrip")
        page.addWidget(strip)
        self.strip_layout = QBoxLayout(QBoxLayout.LeftToRight, strip)
        self.strip_layout.setContentsMargins(17, 3, 17, 3)
        self.strip_layout.setSpacing(4)
        tools = self.tools = QHBoxLayout()
        tools.setSpacing(5)
        self.read_tool = QPushButton(ui_icon("book", "#171715"), "对照阅读")
        self.read_tool.setToolTip("打开阅读页，粘贴原文并翻译")
        self.read_tool.clicked.connect(self.reader_requested)
        self.region = QPushButton(ui_icon("region", "#171715"), "框选翻译")
        self.region.clicked.connect(self.region_requested)
        for button in (self.read_tool, self.region):
            button.setProperty("role", "stripAction")
            button.setIconSize(QSize(23, 23))
            if button is self.region:
                rule = QFrame(objectName="stripDivider")
                rule.setFixedSize(1, 19)
                tools.addWidget(rule)
            tools.addWidget(button)
        tools.addStretch(1)
        self.strip_layout.addLayout(tools, 1)

        self.notebook = QPushButton(objectName="openNotebook")
        self.notebook.setProperty("role", "stripAction")
        self.notebook.setAccessibleName("打开生词本")
        self.notebook.setToolTip("打开生词本查看收藏和复习进度")
        self.notebook.clicked.connect(self.library_requested)
        metrics = QHBoxLayout(self.notebook)
        metrics.setContentsMargins(8, 2, 8, 2)
        metrics.setSpacing(5)
        self.values = []
        for caption in ("今日查词", "已收藏", "待复习"):
            if self.values:
                metrics.addSpacing(7)
                rule = QFrame(objectName="stripDivider")
                rule.setFixedSize(1, 17)
                metrics.addWidget(rule)
                metrics.addSpacing(7)
            metrics.addWidget(QLabel(caption, objectName="metricCaption"))
            value = QLabel("—", objectName="metricValue")
            value.setAccessibleName(caption)
            metrics.addWidget(value)
            self.values.append(value)
        for child in self.notebook.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.notebook.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.strip_layout.addWidget(self.notebook)
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.PointingHandCursor)
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.keycap.setText(key or "仅应用内")
        self.keycap.setAccessibleName(f"取词键设置：{key or '仅应用内查词'}")
        self.hero.layout_entry()
        self.demo.setToolTip(f"单击，或指向词头轻按{key}试查" if key else "单击试查 glance")
        self.region.setToolTip(f"按住{key}，拖选屏幕上的原文" if key else "点击开始框选，拖选屏幕上的原文")

    def set_stats(self, today, saved, due):
        for display, value in zip(self.values, (today, saved, due)):
            display.setText("—" if value is None else f"{value:,}")
        self.notebook.setAccessibleDescription("，".join(f"{v.accessibleName()} {v.text()}" for v in self.values))
        self.notebook.setMinimumSize(self.notebook.layout().sizeHint())
        self.arrange_strip()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange_strip()

    def arrange_strip(self):
        needed = self.tools.minimumSize().width() + self.notebook.layout().sizeHint().width() + 58
        narrow = self.viewport().width() < needed
        self.strip_layout.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self.strip_layout.setContentsMargins(11 if narrow else 22, 7, 11 if narrow else 22, 7)
        self.strip_layout.setAlignment(self.notebook, Qt.AlignLeft if narrow else Qt.AlignVCenter)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
