"""First-use guide to screen lookup, reading and review."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from theme import ui_icon


HOME_WORD = "glance"
EXAMPLE_OPENING = "She turned back"
EXAMPLE_PHRASE = "for one last"
HOME_EXAMPLE = f"{EXAMPLE_OPENING} {EXAMPLE_PHRASE} {HOME_WORD}."
COVER = Path(__file__).resolve().parents[1] / "Assets/Editorial/glance.png"
SAVE_HINT = "查词时点「收藏生词」，在这里用原句复习。"

HOME_STYLE = """
    QWidget#home, QFrame#intro {background:#faf9f6;}
    QLabel#section {font-weight:700; font-size:14px; color:#494943;}
    QFrame#sectionRule {background:#191917; border:0;}
    QLabel#guideTitle {color:#131312; font-weight:900;}
    QLabel#instructions {color:#34342f;}
    QPushButton#tryMeaning {background:#171715; color:white; border:2px solid #171715;
        border-radius:0; font-size:16px; font-weight:700; padding:8px 14px;}
    QPushButton#tryMeaning:hover {background:#383835;}
    QPushButton#tryMeaning:focus {border-color:#8c8c84;}
    QPushButton#coverKey {background:transparent; color:#44443f; border:1px solid transparent;
        font-size:13px; border-radius:0; padding:6px;}
    QPushButton#coverKey:hover, QPushButton#coverKey:focus {border-color:#64645e;}
    QFrame#example {background:#fffefa; border:1px solid #171715;}
    QLabel#exampleCaption {font-size:12px; font-weight:600; color:#53534d;}
    QLabel[role="sampleText"], QPushButton#trialWord {font:italic 20px 'Spectral','Georgia'; color:#171715;}
    QPushButton#trialWord {background:transparent; border:0; border-bottom:2px solid #171715;
        min-height:0; border-radius:0; padding:0;}
    QPushButton#trialWord:hover, QPushButton#trialWord:focus {background:#deddd5;}
    QFrame#taskStrip {background:#272723; border:0;}
    QPushButton[role="homeTask"] {background:#faf9f6; border:0; border-radius:0; padding:0;}
    QPushButton[role="homeTask"]:hover, QPushButton[role="homeTask"]:focus {background:#eeede7;}
    QLabel#taskTitle {font-size:21px; font-weight:700; color:#191917;}
    QLabel#taskHint {font-size:14px; color:#50504b;}
    QLabel#homeWarning {background:#faf9f6; color:#862d21; padding:4px 16px;}
"""


class ExamplePanel(QWidget):
    """Keep the real lookup target attached to its sentence as the illustration resizes."""

    def __init__(self):
        super().__init__()
        self.portrait = QPixmap(str(COVER))
        layout = QVBoxLayout(self)
        layout.addStretch()
        self.note = QFrame(objectName="example")
        layout.addWidget(self.note, 0, Qt.AlignLeft)
        note = QVBoxLayout(self.note)
        note.setSpacing(1)
        note.setContentsMargins(12, 7, 12, 9)
        note.addWidget(QLabel("点击划线词试查", objectName="exampleCaption"))
        self.lead = QLabel(EXAMPLE_OPENING)
        self.prefix = QLabel(EXAMPLE_PHRASE + " ")
        self.period = QLabel(".")
        for label in (self.lead, self.prefix, self.period):
            label.setProperty("role", "sampleText")
        note.addWidget(self.lead)
        line = QHBoxLayout()
        line.setSpacing(0)
        note.addLayout(line)
        line.addWidget(self.prefix)
        self.demo = QPushButton(HOME_WORD, objectName="trialWord")
        self.demo.setAccessibleName("试查例句中的 glance")
        line.addWidget(self.demo)
        line.addWidget(self.period)
        line.addStretch()
        self.setAccessibleName(HOME_EXAMPLE)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        inset = 18 if self.width() >= 270 else 8
        self.layout().setContentsMargins(inset, 10, inset, inset)
        flat = self.prefix.fontMetrics().horizontalAdvance(HOME_EXAMPLE) + 34 <= self.width() - 2 * inset
        self.lead.setVisible(not flat)
        self.prefix.setText((f"{EXAMPLE_OPENING} {EXAMPLE_PHRASE}" if flat else EXAMPLE_PHRASE) + " ")

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), QColor("#edeae3"))
            if not self.portrait.isNull():
                scale = max(self.width() / self.portrait.width(), self.height() / self.portrait.height())
                w, h = self.width() / scale, self.height() / scale
                # Keep the visible eye in the panel when the window is tall and narrow.
                x = max(0, min(self.portrait.width() - w, self.portrait.width() * 0.72 - w * 0.52))
                source = QRectF(x, (self.portrait.height() - h) * 0.30, w, h)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawPixmap(QRectF(self.rect()), self.portrait, source)
            painter.fillRect(0, 0, 1, self.height(), QColor("#272723"))


class HomeTask(QPushButton):
    def __init__(self, title, icon, hint):
        super().__init__()
        self.setProperty("role", "homeTask")
        self.setAccessibleName(title)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        box = QGridLayout(self)
        box.setHorizontalSpacing(9)
        box.setVerticalSpacing(8)
        box.setColumnStretch(2, 1)
        glyph = QLabel()
        glyph.setPixmap(ui_icon(icon, "#191917").pixmap(23, 23))
        box.addWidget(glyph, 0, 0)
        self.heading = QLabel(title, objectName="taskTitle")
        box.addWidget(self.heading, 0, 1)
        arrow = QLabel()
        arrow.setPixmap(ui_icon("arrow", "#50504b").pixmap(18, 18))
        box.addWidget(arrow, 0, 3)
        self.hint = QLabel(objectName="taskHint")
        self.hint.setWordWrap(True)
        self.compact = None
        self.set_compact(False)
        self.set_hint(hint)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_compact(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        box = self.layout()
        box.removeWidget(self.hint)
        if compact:
            box.setContentsMargins(18, 9, 18, 9)
            box.setColumnMinimumWidth(1, self.heading.fontMetrics().horizontalAdvance("对照阅读"))
            box.setAlignment(Qt.AlignVCenter)
            box.addWidget(self.hint, 0, 2)
        else:
            box.setContentsMargins(24, 20, 24, 22)
            box.setColumnMinimumWidth(1, 0)
            box.setAlignment(Qt.AlignTop)
            box.addWidget(self.hint, 1, 0, 1, 4, Qt.AlignTop)

    def set_hint(self, hint):
        self.hint.setText(hint)
        self.setAccessibleDescription(hint)

    def sizeHint(self):
        return self.layout().sizeHint()

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)


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

        hero = QHBoxLayout()
        hero.setSpacing(0)
        page.addLayout(hero, 1)
        intro = QFrame(objectName="intro")
        self.copy = QVBoxLayout(intro)
        self.copy.setSpacing(0)
        self.copy.addStretch(2)
        kicker = QHBoxLayout()
        rule = QFrame(objectName="sectionRule")
        rule.setFixedSize(26, 3)
        kicker.addWidget(rule)
        kicker.addSpacing(5)
        self.mode_label = QLabel(objectName="section")
        kicker.addWidget(self.mode_label)
        kicker.addStretch()
        self.copy.addLayout(kicker)
        self.copy.addSpacing(10)
        self.title = QLabel("在原文里\n读懂生词", objectName="guideTitle")
        self.copy.addWidget(self.title)
        self.copy.addSpacing(12)
        self.instructions = QLabel(objectName="instructions")
        self.instructions.setWordWrap(True)
        self.copy.addWidget(self.instructions)
        self.copy.addSpacing(20)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.trial = QPushButton(ui_icon("launch", "#ffffff"), "试查 glance", objectName="tryMeaning")
        self.trial.setLayoutDirection(Qt.RightToLeft)
        self.trial.setIconSize(QSize(18, 18))
        self.trial.clicked.connect(self.demo_requested)
        actions.addWidget(self.trial)
        self.key_settings = QPushButton("更改取词键", objectName="coverKey")
        self.key_settings.clicked.connect(self.settings_requested)
        actions.addWidget(self.key_settings)
        actions.addStretch()
        self.copy.addLayout(actions)
        self.copy.addStretch(2)
        hero.addWidget(intro, 55)
        self.example = ExamplePanel()
        hero.addWidget(self.example, 45)
        self.demo = self.example.demo
        self.demo.clicked.connect(self.demo_requested)

        self.warning = QLabel(objectName="homeWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        page.addWidget(self.warning)

        strip = QFrame(objectName="taskStrip")
        page.addWidget(strip)
        self.task_layout = QBoxLayout(QBoxLayout.LeftToRight, strip)
        self.task_layout.setContentsMargins(0, 1, 0, 0)
        self.task_layout.setSpacing(1)
        self.region = HomeTask("框选翻译", "region", "")
        self.region.clicked.connect(self.region_requested)
        self.read_tool = HomeTask("对照阅读", "book", "粘贴文章，按 Ctrl + Enter 查看对照译文。")
        self.read_tool.clicked.connect(self.reader_requested)
        self.notebook = HomeTask("生词本", "bookmark", SAVE_HINT)
        self.notebook.setObjectName("openNotebook")
        self.notebook.clicked.connect(self.library_requested)
        for task in (self.region, self.read_tool, self.notebook):
            self.task_layout.addWidget(task, 1)
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.PointingHandCursor)
        self.refresh = QTimer(self, interval=30_000)
        self.refresh.timeout.connect(self.stats_requested)
        self.set_mode("left")
        self.arrange()

    def set_mode(self, mode):
        key = {"left": "左 Ctrl", "right": "右 Ctrl"}.get(mode)
        self.key_settings.setAccessibleDescription(f"当前为{key or '仅应用内查词'}")
        self.mode_label.setText("屏幕取词" if key else "应用内查词")
        if key:
            self.instructions.setText(f"在网页或 PDF 里，鼠标指向生词，轻按 <nobr><b>{key}</b></nobr>。<br>浮窗会显示句中词义和整句译文。")
            self.demo.setToolTip(f"点击，或指向 glance 轻按{key}试查")
            hint = f"按住{key}，左键拖选，松开鼠标看译文。"
        else:
            self.instructions.setText("在「阅读」页粘贴外文，<b>双击生词</b>。<br>浮窗会显示句中词义和整句译文。")
            self.demo.setToolTip("点击 glance 试查")
            hint = "点击开始框选，用鼠标拖出要翻译的区域，松开即可查看译文。"
        self.region.set_hint(hint)

    def set_stats(self, today, saved, due):
        if None in (today, saved, due):
            hint = "打开生词本，查看已收藏的原句和复习进度。"
        elif saved:
            hint = f"今日查词 {today:,} 次，已收藏 {saved:,} 条，待复习 {due:,} 条。"
        elif today:
            hint = f"今日查词 {today:,} 次。查词时点「收藏生词」即可保存原句。"
        else:
            hint = SAVE_HINT
        self.notebook.set_hint(hint)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        w = self.viewport().width()
        narrow = w < 720
        margin = 18 if narrow else max(28, min(64, w // 24))
        self.copy.setContentsMargins(margin, 20, margin, 20)
        self.title.setStyleSheet(f"font-size:{max(34, min(68, w // 18))}px;")
        self.instructions.setStyleSheet(f"font-size:{15 if narrow else 17}px;")
        self.task_layout.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        for task in (self.region, self.read_tool, self.notebook):
            task.set_compact(narrow)

    def showEvent(self, event):
        super().showEvent(event)
        self.stats_requested.emit()
        self.refresh.start()

    def hideEvent(self, event):
        self.refresh.stop()
        super().hideEvent(event)
