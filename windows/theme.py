"""Typography, colour and icons for the Windows reader."""
from html import escape
from math import cos, pi, sin
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def ui_icon(name, color="#595955"):
    path = QPainterPath()
    if name == "settings":
        for tooth in range(8):
            for step, radius in enumerate((8, 10, 10, 8)):
                angle = (tooth + step / 4) * pi / 4
                point = QPointF(12 + radius * cos(angle), 12 + radius * sin(angle))
                if tooth == 0 and step == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
        path.closeSubpath()
        path.addEllipse(QPointF(12, 12), 3, 3)
    elif name == "history":
        path.addEllipse(QPointF(12, 12), 8, 8)
        path.moveTo(12, 7)
        path.lineTo(12, 12)
        path.lineTo(16, 14)
    elif name == "launch":
        path.moveTo(5, 19)
        path.lineTo(19, 5)
        path.moveTo(8, 5)
        path.lineTo(19, 5)
        path.lineTo(19, 16)
    elif name == "book":
        path.moveTo(12, 6)
        path.quadTo(7, 3, 3, 5)
        path.lineTo(3, 18)
        path.quadTo(7, 16, 12, 19)
        path.quadTo(17, 16, 21, 18)
        path.lineTo(21, 5)
        path.quadTo(17, 3, 12, 6)
        path.lineTo(12, 19)
    elif name == "region":
        for x, dx in ((4, 4), (20, -4)):
            for y, dy in ((4, 4), (20, -4)):
                path.moveTo(x + dx, y)
                path.lineTo(x, y)
                path.lineTo(x, y + dy)
        for y, end in ((10, 16), (14, 13)):
            path.moveTo(8, y)
            path.lineTo(end, y)
    elif name == "bookmark":
        path.moveTo(5, 3)
        path.lineTo(19, 3)
        path.lineTo(19, 21)
        path.lineTo(12, 16)
        path.lineTo(5, 21)
        path.closeSubpath()
    elif name == "minimize":
        path.moveTo(5, 15)
        path.lineTo(19, 15)
    elif name == "maximize":
        path.addRect(5, 5, 14, 14)
    elif name == "restore":
        path.addRect(5, 8, 11, 11)
        path.moveTo(8, 6)
        path.lineTo(8, 4)
        path.lineTo(19, 4)
        path.lineTo(19, 15)
        path.lineTo(17, 15)
    elif name == "close":
        path.moveTo(6, 6)
        path.lineTo(18, 18)
        path.moveTo(18, 6)
        path.lineTo(6, 18)
    elif name == "arrow":
        path.moveTo(5, 12)
        path.lineTo(19, 12)
        path.moveTo(13, 6)
        path.lineTo(19, 12)
        path.lineTo(13, 18)
    pix = QPixmap(72, 72)
    pix.fill(Qt.transparent)
    with QPainter(pix) as pen:
        pen.setRenderHint(QPainter.Antialiasing)
        pen.scale(3, 3)
        pen.setPen(QPen(QColor(color), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        pen.drawPath(path)
    pix.setDevicePixelRatio(3)
    return QIcon(pix)


def apply_theme(app):
    fonts = Path(__file__).with_name("fonts")
    for filename in ("Spectral-Regular.ttf", "Spectral-SemiBold.ttf", "Spectral-Italic.ttf", "ArchivoBlack-Regular.ttf", "NotoSerifSC-Glance-Black.ttf"):
        QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = app.palette()
    for role, color in (
        (QPalette.Window, "#faf9f6"), (QPalette.WindowText, "#161615"),
        (QPalette.Base, "#fffefa"), (QPalette.Text, "#161615"),
        (QPalette.Button, "#faf9f6"), (QPalette.ButtonText, "#161615"),
        (QPalette.Highlight, "#d5d4ce"), (QPalette.HighlightedText, "#161615"),
        (QPalette.PlaceholderText, "#595955"), (QPalette.Link, "#161615"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget {color:#161615; font-size:13px;}
        QWidget#desk {background:#faf9f6; border:0;}
        QWidget#home, QScrollArea#settingsPage {background:transparent; border:0;}
        QWidget#readingPage, QWidget#library {background:rgba(250,249,246,168); border:0;}
        QWidget#settingsSurface {background:rgba(250,249,246,191); border:0;}
        QLabel {background:transparent; border:0;}
        QLabel[role="heading"] {color:#161615; font-size:28px; font-weight:600;}
        QLabel[role="subhead"] {color:#161615; font-size:15px; font-weight:600;}
        QLabel[role="meta"] {color:#595955; font-size:12px;}
        QLabel[role="warning"] {color:#a13922; font-size:13px;}
        QLabel[role="settingsSection"] {color:#363634; font-size:16px; font-weight:600;}
        QLabel[role="shortcut"] {color:#595955; background:#f0efea; border:1px solid #bcbcb6;
            border-radius:4px; padding:2px 5px; font:12px 'Consolas';}

        QFrame#sidebar {background:rgba(248,247,243,198); border:0;}
        QFrame#navDivider {background:rgba(68,67,59,72); border:0;}
        QPushButton[role="windowControl"] {background:transparent; border:0; border-radius:2px; padding:0;}
        QPushButton[role="windowControl"]:hover, QPushButton[role="windowControl"]:focus {background:#e7e6df;}
        QPushButton#closeWindow:hover {background:#e3c5c0;}
        QLabel[role="brand"] {color:#101010; font:italic 27px 'Archivo Black','Arial Black'; padding-right:4px;}
        QPushButton[role="nav"] {color:#45443f; background:rgba(249,248,244,146);
            border:1px solid rgba(83,80,68,50); border-radius:8px; font-weight:500;}
        QPushButton[role="nav"]:hover {background:#f6f5f0; border-color:#a6a498;}
        QPushButton[role="nav"]:checked {color:#171714; background:#fffefa; border-color:#817e72; font-weight:600;}
        QPushButton[role="nav"]:focus {border:1px dashed #37362f;}
        QPushButton[role="nav"]:pressed {background:#e7e5dd;}

        QPushButton {color:#161615; background:#fffefa; border:1px solid #bcbcb6;
            border-radius:2px; padding:7px 13px; min-height:18px;}
        QPushButton:hover {background:#f0efea; border-color:#90908a;}
        QPushButton:pressed {background:#e6e5df; border-color:#747470;}
        QPushButton:focus {border-color:#555551;}
        QPushButton:disabled {color:#747470; background:#f0efea; border-color:#d5d4ce;}
        QPushButton[role="primary"] {background:#161615; color:#fffefa; border-color:#161615;
            padding:7px 18px; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#363634; border-color:#363634;}
        QPushButton[role="primary"]:pressed {background:#161615;}
        QPushButton[role="primary"]:focus {border-color:#9c9c95;}
        QPushButton[role="primary"]:disabled {color:#747470; background:#e6e5df; border-color:#d5d4ce;}
        QPushButton[role="quiet"], QPushButton[role="sample"] {color:#363634; background:transparent;
            border:1px solid transparent; padding:4px 7px; font-size:12px;}
        QPushButton[role="sample"] {color:#161615;}
        QPushButton[role="quiet"]:hover, QPushButton[role="sample"]:hover {background:#e6e5df; color:#161615;}
        QPushButton[role="quiet"]:focus, QPushButton[role="sample"]:focus {border-color:#161615;}
        QPushButton[role="quiet"]:disabled {color:#747470; background:transparent;}
        QLineEdit#search {background:#fffefa; border:1px solid #bcbcb6; border-radius:2px;
            padding:8px 9px; selection-background-color:#d5d4ce; selection-color:#161615;}
        QLineEdit#search:focus, QComboBox#settingsChoice:focus {border-color:#555551;}
        QComboBox#settingsChoice {background:#fffefa; color:#161615; border:1px solid #bcbcb6;
            border-radius:2px; padding:5px 23px 5px 10px; min-height:22px;}
        QComboBox#settingsChoice::drop-down {border:0; width:18px;}
        QComboBox#settingsChoice QAbstractItemView, QMenu {background:#fffefa; color:#161615;
            border:1px solid #bcbcb6; selection-background-color:#e6e5df; selection-color:#161615;}
        QMenu {padding:4px;}
        QMenu::item {padding:6px 16px; border-radius:3px;}
        QMenu::item:selected {background:#e6e5df; color:#161615;}
        QToolTip {background:#161615; color:#fffefa; border:0; padding:5px 8px;}

        QFrame#readingSheet {background:rgba(255,254,250,105); border:1px solid rgba(60,60,53,72); border-radius:4px;}
        QFrame#editor {background:transparent; border:0;}
        QFrame#translationPane {background:rgba(237,236,230,68); border:0; border-top-right-radius:4px;}
        QFrame#binding {border:0; background:#d5d4ce;}
        QFrame#hairline {background:#d5d4ce; border:0; min-height:1px; max-height:1px;}
        QFrame#entrySheet {background:rgba(255,254,250,110); border:1px solid rgba(60,60,53,72); border-radius:4px;}
        QFrame#emptyBook {background:rgba(246,245,240,100); border:0; border-radius:4px;}
        QFrame#settingsGroup {background:transparent; border:0; border-top:1px solid #747470;}
        QLabel[role="paneTitle"] {font:600 17px 'Microsoft YaHei UI'; color:#161615;}
        QLabel[role="language"] {font-size:12px; color:#595955;}
        QLabel[role="characterCount"] {font-size:12px; color:#595955;}
        QPlainTextEdit#input, QPlainTextEdit#translation, QTextBrowser#entry {background:transparent; border:0;
            padding:0; selection-background-color:#d5d4ce; selection-color:#161615;}
        QPlainTextEdit#input {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:21px; color:#161615;}
        QPlainTextEdit#translation {font-size:17px; color:#363634;}
        QListWidget#words {background:transparent; border:1px solid transparent; padding:0; outline:0;}
        QListWidget#words:focus {border-color:#90908a;}
        QListWidget#words QScrollBar:horizontal {background:transparent; height:6px; margin:0 2px;}
        QListWidget#words QScrollBar::handle:horizontal {background:#bcbcb6; min-width:24px; border-radius:3px;}
        QListWidget#words QScrollBar::add-line:horizontal, QListWidget#words QScrollBar::sub-line:horizontal {width:0;}
        QListWidget#words QScrollBar::add-page:horizontal, QListWidget#words QScrollBar::sub-page:horizontal {background:transparent;}
        QScrollBar:vertical {background:transparent; width:8px; margin:2px 1px;}
        QScrollBar::handle:vertical {background:#bcbcb6; min-height:24px; border-radius:3px;}
        QScrollBar::handle:vertical:hover {background:#90908a;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
    """)



def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = """
    p {margin:0; font-family:'Microsoft YaHei UI'; color:#161615;}
    .word {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:34px; font-weight:600; color:#161615;}
    .details {font-size:12px; color:#595955; margin-bottom:8px;}
    .gloss {font-size:18px; line-height:136%; color:#161615; margin-bottom:8px;}
    .contextTitle {font-size:11px; color:#595955; margin-top:6px; margin-bottom:3px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:19px; line-height:122%; color:#363634;}
    .hit {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-weight:600; color:#161615; background-color:#e6e5df;}
    .translation {font-size:14px; line-height:138%; color:#363634; margin-top:6px;}
    .message {font-size:14px; line-height:140%;}
    a {color:#161615;}
"""


def marked_source(passage):
    if not passage.selection:
        return plain(passage.text)
    a, b = passage.selection
    return plain(passage.text[:a]) + f"<span class='hit'>{plain(passage.word)}</span>" + plain(passage.text[b:])


def result_html(passage, gloss, sentence, details, prefix="", suffix=""):
    source = marked_source(passage)
    heading = ""
    if passage.selection:
        word = plain(passage.word)
        heading = f"<p class='word'>{word}</p>"
    source_label = "原句" if passage.selection else "原文"
    content = (heading + f"<p class='details'>{plain(details)}</p><p class='gloss'>{plain(gloss)}</p>"
               + f"<hr style='background-color:#d5d4ce'><p class='contextTitle'>{source_label}</p>"
               + f"<p class='source'>{prefix}{source}{suffix}</p>")
    if sentence:
        content += f"<p class='translation'>{plain(sentence)}</p>"
    return content
