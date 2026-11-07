"""The interactive word cover, translation tools and notebook metrics."""
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from theme import ui_icon


HOME_EXAMPLE = "They sat on the river bank."
COVER = Path(__file__).resolve().parents[1] / "Assets/Editorial/river.jpg"

HOME_STYLE = """
    QLabel#coverLabel {color:#faf9ee; font-size:13px; font-weight:600;}
    QFrame#coverDash {background:#ed997a; border:0;}
    QPushButton#coverSettings {background:rgba(19,35,30,150); border:1px solid rgba(250,250,242,95);
        border-radius:16px; padding:0; min-height:30px; max-height:30px;}
    QPushButton#coverSettings:hover, QPushButton#coverSettings:focus {
        background:#35463e; border-color:#fff9e9;}
    QPushButton#trialWord {font:italic 91px 'Spectral','Georgia'; padding:0; border:0; background:transparent;}
    QPushButton#tryMeaning {color:#1c3024; background:#faf9ec; border:1px solid #faf9ec;
        border-radius:5px; padding:6px 12px; font-size:13px; font-weight:600;}
    QPushButton#tryMeaning:hover, QPushButton#tryMeaning:focus {background:#f5dfbb; border-color:#db926f;}
    QLabel#phonetic {color:#fcf2dc; font:italic 19px 'Spectral','Georgia';}
    QLabel#sentence {color:#fffdf4; font:22px 'Spectral','Georgia';}
    QLabel#coverHint {color:#faf9f0; font-size:13px;}
    QLabel#coverKey {color:#fffcf3; font-size:12px; font-weight:600;
        background:rgba(52,66,57,190); border:1px solid #aeb6a5; border-bottom-width:2px;
        border-radius:4px; padding:1px 7px;}
    QPushButton#coverRead {color:#fff9ec; background:transparent; padding:1px 0;
        border:0; border-bottom:1px solid #e4cdbc; border-radius:0;}
    QPushButton#coverRead:hover, QPushButton#coverRead:focus {color:#ffd0a8; border-color:#ffd0a8;}
    QLabel#homeWarning {color:#923b27; padding:5px 0; font-size:12px;}

    QLabel#sectionTitle {color:#202d27; font-size:18px; font-weight:600;}
    QFrame#toolRule {background:#d8dcd2; border:0; min-height:1px; max-height:1px;}
    QPushButton[role="toolRow"] {background:transparent; border:1px solid transparent;
        border-radius:6px; padding:0; min-height:61px;}
    QPushButton[role="toolRow"]:hover {background:#ecf0e8;}
    QPushButton[role="toolRow"]:focus {background:#eef1e9; border-color:#899c90;}
    QLabel#toolGlyph {background:#e5ebe3; border:0; border-radius:10px;}
    QLabel#toolName {font-size:15px; color:#1f3028; font-weight:600;}
    QLabel#toolHint, QLabel#metricCaption, QLabel#recordDate {color:#52615a; font-size:12px;}
    QFrame#recordPanel {background:#e9ede5; border:0; border-radius:8px;}
    QLabel#metricValue {font:42px 'Spectral','Georgia'; color:#233a2b;}
    QFrame#statDivider {background:#cbd4c8; border:0;}
    QPushButton#openNotebook {background:transparent; color:#354c3c; border:1px solid transparent;
        border-radius:3px; padding:1px 3px; font-size:12px; text-align:left; min-height:0;}
    QPushButton#openNotebook:hover, QPushButton#openNotebook:focus {border-color:#819685;}
"""


class Cover(QFrame):
    def __init__(self):
        super().__init__()
        self.river = QPixmap(str(COVER))

    def paintEvent(self, event):
        area = QRectF(self.rect())
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            corners = QPainterPath()
            corners.addRoundedRect(area, 8, 8)
            painter.setClipPath(corners)
            painter.fillRect(area, QColor("#23372e"))
            if not self.river.isNull():
                scale = max(area.width() / self.river.width(), area.height() / self.river.height())
                w, h = area.width() / scale, area.height() / scale
                # Keep the sunlit bank in the frame as the cover gets narrower.
                crop = QRectF((self.river.width() - w) * 0.77, (self.river.height() - h) / 2, w, h)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawPixmap(area, self.river, crop)
            shade = QLinearGradient(area.topLeft(), area.topRight())
            shade.setColorAt(0, QColor(12, 26, 21, 200))
            if area.width() < 575:
                shade.setColorAt(0.72, QColor(12, 26, 21, 166))
                shade.setColorAt(1, Qt.transparent)
            else:
                shade.setColorAt(0.42, QColor(12, 26, 21, 132))
                shade.setColorAt(0.76, Qt.transparent)
            painter.fillRect(area, shade)


class WordButton(QPushButton):
    """Fit the clickable word to its ink, including the slant of the italic."""
    def sizeHint(self):
        ink = QFontMetricsF(self.font()).tightBoundingRect(self.text())
        return QSize(round(ink.width()) + 8, round(ink.height()) + 12)

    def paintEvent(self, event):
        ink = QFontMetricsF(self.font()).tightBoundingRect(self.text())
        with QPainter(self) as painter:
            painter.setFont(self.font())
            painter.setPen(QColor("#fffbed"))
            painter.drawText(QPointF(3 - ink.left(), (self.height() - ink.height()) / 2 - ink.top()), self.text())
            if self.underMouse() or self.hasFocus():
                painter.fillRect(2, self.height() - 3, self.width() - 4, 2, QColor("#eea383"))


class ToolRow(QPushButton):
    """The icon, text and arrow form one focusable target."""
    def __init__(self, title, description, icon):
        super().__init__()
        self.setProperty("role", "toolRow")
        self.setAccessibleName(title)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(63)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 8, 3)
        row.setSpacing(13)
        mark = QLabel(objectName="toolGlyph")
        mark.setFixedSize(39, 39)
        mark.setAlignment(Qt.AlignCenter)
        mark.setPixmap(ui_icon(icon, "#435d4d").pixmap(QSize(21, 21)))
        row.addWidget(mark)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch()
        text.addWidget(QLabel(title, objectName="toolName"))
        self.hint = QLabel(description, objectName="toolHint")
        text.addWidget(self.hint)
        text.addStretch()
        row.addLayout(text, 1)
        arrow = QLabel()
        arrow.setPixmap(ui_icon("arrow", "#718177").pixmap(QSize(18, 18)))
        row.addWidget(arrow)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)


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
        self.page = QVBoxLayout(surface)
        self.page.setSpacing(0)
        self.hero = Cover()
        self.page.addWidget(self.hero)
        cover = QVBoxLayout(self.hero)
        cover.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(9)
        dash = QFrame(objectName="coverDash")
        dash.setFixedSize(20, 2)
        header.addWidget(dash)
        self.guide_title = QLabel(objectName="coverLabel")
        header.addWidget(self.guide_title)
        header.addStretch()
        self.settings_link = QPushButton(ui_icon("settings", "#fff7e9"), "", objectName="coverSettings")
        self.settings_link.setFixedSize(32, 32)
        self.settings_link.setIconSize(QSize(16, 16))
        self.settings_link.setAccessibleName("取词键设置")
        self.settings_link.setToolTip("取词键设置")
        self.settings_link.clicked.connect(self.settings_requested)
        header.addWidget(self.settings_link)
        cover.addLayout(header)
        cover.addStretch()

        self.sample = QWidget()
        word = QHBoxLayout(self.sample)
        word.setContentsMargins(0, 0, 0, 0)
        word.setSpacing(10)
        self.demo = WordButton("bank", objectName="trialWord")
        self.demo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.demo.setAccessibleName("试查 bank")
        self.demo.clicked.connect(self.demo_requested)
        word.addWidget(self.demo, 0, Qt.AlignVCenter)
        phonetic = QLabel("/bæŋk/", objectName="phonetic")
        phonetic.setContentsMargins(0, 0, 0, 7)
        word.addWidget(phonetic, 0, Qt.AlignBottom)
        word.addStretch()
        cover.addWidget(self.sample)
        cover.addSpacing(3)
        cover.addWidget(QLabel(HOME_EXAMPLE, objectName="sentence"))
        cover.addStretch()
        instruction = QHBoxLayout()
        instruction.setSpacing(6)
        trial = QPushButton("试查词义", objectName="tryMeaning")
        trial.setIcon(ui_icon("arrow", "#354b3b"))
        trial.setIconSize(QSize(15, 15))
        trial.setLayoutDirection(Qt.RightToLeft)
        trial.clicked.connect(self.demo_requested)
        instruction.addWidget(trial)
        instruction.addSpacing(6)
        self.key_verb = QLabel(objectName="coverHint")
        instruction.addWidget(self.key_verb)
        self.keycap = QLabel(objectName="coverKey")
        instruction.addWidget(self.keycap)
        self.reader = QPushButton("打开阅读页", objectName="coverRead")
        self.reader.clicked.connect(self.reader_requested)
        instruction.addWidget(self.reader)
        instruction.addStretch()
        cover.addLayout(instruction)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        self.page.addWidget(self.warning)
        self.page.addSpacing(23)
        self.sections = QBoxLayout(QBoxLayout.LeftToRight)
        self.page.addLayout(self.sections)

        tools = QVBoxLayout()
        tools.setSpacing(0)
        tools.addWidget(QLabel("翻译工具", objectName="sectionTitle"))
        tools.addSpacing(10)
        tools.addWidget(QFrame(objectName="toolRule"))
        self.read_tool = ToolRow("对照阅读", "粘贴原文，对照译文阅读。", "book")
        self.read_tool.setAccessibleDescription(self.read_tool.hint.text())
        self.read_tool.clicked.connect(self.reader_requested)
        tools.addWidget(self.read_tool)
        tools.addWidget(QFrame(objectName="toolRule"))
        self.region = ToolRow("开始框选", "", "region")
        self.region.clicked.connect(self.region_requested)
        self.region_hint = self.region.hint
        tools.addWidget(self.region)
        tools.addStretch()
        self.sections.addLayout(tools, 11)

        record = QFrame(objectName="recordPanel")
        ledger = QVBoxLayout(record)
        ledger.setContentsMargins(21, 16, 21, 13)
        ledger.setSpacing(0)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("学习记录", objectName="sectionTitle"))
        heading.addStretch()
        self.record_date = QLabel(objectName="recordDate")
        heading.addWidget(self.record_date)
        ledger.addLayout(heading)
        ledger.addSpacing(9)
        metrics = QHBoxLayout()
        metrics.setSpacing(13)
        self.values = []
        for caption in ("今日查词", "已收藏", "待复习"):
            column = QVBoxLayout()
            column.setSpacing(0)
            number = QLabel("—", objectName="metricValue")
            number.setAccessibleName(caption)
            column.addWidget(number)
            column.addWidget(QLabel(caption, objectName="metricCaption"))
            self.values.append(number)
            metrics.addLayout(column, 1)
        ledger.addLayout(metrics)
        ledger.addSpacing(12)
        rule = QFrame(objectName="statDivider")
        rule.setFixedHeight(1)
        ledger.addWidget(rule)
        ledger.addSpacing(6)
        notebook = QPushButton("查看生词本", objectName="openNotebook")
        notebook.setIcon(ui_icon("arrow", "#425b49"))
        notebook.setIconSize(QSize(15, 15))
        notebook.setLayoutDirection(Qt.RightToLeft)
        notebook.clicked.connect(self.library_requested)
        ledger.addWidget(notebook, 0, Qt.AlignRight)
        self.sections.addWidget(record, 10, Qt.AlignTop)
        self.page.addStretch()

        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.PointingHandCursor)
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.keycap.setVisible(bool(key))
        self.reader.setVisible(not key)
        if key:
            self.guide_title.setText("悬停取词")
            self.set_key_hint()
            self.keycap.setText(key)
            self.demo.setToolTip(f"单击，或指向词头轻按{key}查看句中释义")
            self.region_hint.setText(f"按住{key}，拖选屏幕上的原文。")
        else:
            self.guide_title.setText("仅应用内查词")
            self.key_verb.setText("或")
            self.demo.setToolTip("单击查看句中释义")
            self.region_hint.setText("点击「开始框选」，拖选屏幕上的原文。")
        self.region.setAccessibleDescription(self.region_hint.text())

    def set_key_hint(self):
        self.key_verb.setText("或指向词头，轻按" if self.viewport().width() < 500 else "或指向屏幕上的词，轻按")

    def set_stats(self, today, saved, due):
        now = date.today()
        self.record_date.setText(f"{now.month} 月 {now.day} 日")
        for display, value in zip(self.values, (today, saved, due)):
            display.setText("—" if value is None else f"{value:,}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        if not self.keycap.isHidden():
            self.set_key_hint()
        narrow = width < 700
        self.page.setContentsMargins(16 if narrow else 32, 16 if narrow else 22,
                                     16 if narrow else 32, 18)
        inset = 21 if narrow else 33
        self.hero.layout().setContentsMargins(inset, 17 if narrow else 21, inset, 24 if narrow else 27)
        self.hero.setFixedHeight(max(252, min(388, round(width * 0.34))))
        self.sections.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self.sections.setSpacing(17 if narrow else 32)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
