"""Typography, colour and icons for the Windows reader."""
from html import escape
from math import cos, pi, sin
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"
COLORS = dict(paper="#f8f7f3", sheet="#fffefa", ink="#242523", muted="#5c605b",
              rule="#d7d8d2", accent="#ac442d", soft="#eceee7", focus="#74786e")


def theme_css(source):
    """One palette for application chrome, reading documents and the lookup card."""
    return Template(source).substitute(COLORS)


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def ui_icon(name, color=COLORS["muted"]):
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
    elif name == "pin":
        path.moveTo(7, 4)
        path.lineTo(17, 4)
        path.lineTo(15, 6)
        path.lineTo(15, 11)
        path.lineTo(18, 14)
        path.lineTo(6, 14)
        path.lineTo(9, 11)
        path.lineTo(9, 6)
        path.closeSubpath()
        path.moveTo(12, 14)
        path.lineTo(12, 21)
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
    elif name == "menu":
        for y in (6, 12, 18):
            path.moveTo(5, y)
            path.lineTo(19, y)
    elif name == "globe":
        path.addEllipse(QPointF(12, 12), 9, 9)
        path.addEllipse(8, 3, 8, 18)
        path.moveTo(3, 12)
        path.lineTo(21, 12)
        path.moveTo(5, 7)
        path.quadTo(12, 10, 19, 7)
        path.moveTo(5, 17)
        path.quadTo(12, 14, 19, 17)
    elif name in ("expand", "collapse"):
        path.addEllipse(QPointF(6, 6), 3, 3)
        path.moveTo(4, 6)
        path.lineTo(8, 6)
        if name == "expand":
            path.moveTo(6, 4)
            path.lineTo(6, 8)
        for y, start in ((5, 12), (11, 4), (17, 4)):
            path.moveTo(start, y)
            path.lineTo(21, y)
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
        (QPalette.Window, COLORS["paper"]), (QPalette.WindowText, COLORS["ink"]),
        (QPalette.Base, COLORS["sheet"]), (QPalette.Text, COLORS["ink"]),
        (QPalette.Button, COLORS["paper"]), (QPalette.ButtonText, COLORS["ink"]),
        (QPalette.Highlight, COLORS["soft"]), (QPalette.HighlightedText, COLORS["ink"]),
        (QPalette.PlaceholderText, COLORS["muted"]), (QPalette.Link, COLORS["accent"]),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(theme_css("""
        QWidget {color:$ink; font-size:13px;}
        QWidget#desk, QFrame#sidebar {background:$paper; border:0;}
        QWidget#home {background:transparent; border:0;}
        QWidget#readingPage, QWidget#library, QScrollArea#settingsPage,
        QWidget#settingsSurface {background:$paper; border:0;}
        QLabel {background:transparent; border:0;}
        QLabel[role="heading"] {color:$ink; font-size:27px; font-weight:600;}
        QLabel[role="subhead"] {color:$ink; font-size:14px; font-weight:600;}
        QLabel[role="meta"] {color:$muted; font-size:12px;}
        QLabel[role="warning"] {color:$accent; font-size:13px;}
        QLabel[role="settingsSection"] {color:$ink; font-size:15px; font-weight:600;}
        QLabel[role="shortcut"] {color:$muted; background:$soft; border:0;
            border-radius:4px; padding:3px 6px; font:11px 'Consolas';}
        QFrame#navDivider {background:$rule; border:0;}
        QPushButton[role="windowControl"] {background:transparent; border:0; border-radius:4px; padding:0;}
        QPushButton[role="windowControl"]:hover, QPushButton[role="windowControl"]:focus {background:$soft;}
        QPushButton#closeWindow:hover {background:#edcfca;}
        QPushButton#appMenu::menu-indicator {image:none;}
        QLabel[role="brand"] {color:$ink; font:italic 600 26px 'Spectral';}
        QPushButton[role="nav"] {color:$muted; background:transparent; border:0;
            border-bottom:2px solid transparent; border-radius:0; font-weight:400;}
        QPushButton[role="nav"]:hover {color:$ink; background:$soft;}
        QPushButton[role="nav"]:checked {color:$ink; background:transparent;
            border-bottom:2px solid $ink; font-weight:600;}
        QPushButton[role="nav"]:focus {background:transparent; border-bottom:2px solid $accent;}
        QPushButton[role="nav"]:pressed {background:$rule;}
        QPushButton {color:$ink; background:$soft; border:1px solid transparent;
            border-radius:15px; padding:6px 13px; min-height:18px;}
        QPushButton:hover {background:#e2e6dc;}
        QPushButton:pressed {background:$rule;}
        QPushButton:focus {border-color:$focus;}
        QPushButton:disabled {color:#73796e; background:$soft; border-color:transparent;}
        QPushButton[role="primary"] {background:$ink; color:$sheet; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#3b4038;}
        QPushButton[role="primary"]:pressed {background:#1d211b;}
        QPushButton[role="primary"]:focus {border-color:$accent;}
        QPushButton[role="primary"]:disabled {color:#73796e; background:$soft;}
        QPushButton[role="quiet"], QPushButton[role="sample"] {color:$muted; background:transparent;
            border:1px solid transparent; padding:4px 8px; font-size:12px;}
        QPushButton[role="sample"] {color:$ink;}
        QPushButton[role="quiet"]:hover, QPushButton[role="sample"]:hover {background:$soft; color:$ink;}
        QPushButton[role="quiet"]:focus, QPushButton[role="sample"]:focus {border-color:$focus;}
        QPushButton[role="quiet"]:disabled {color:#73796e; background:transparent;}
        QLineEdit#search {background:$sheet; border:1px solid $rule; border-radius:8px;
            padding:8px 10px; selection-background-color:$soft; selection-color:$ink;}
        QLineEdit#search:focus, QComboBox#settingsChoice:focus {border-color:$focus;}
        QComboBox#settingsChoice {background:$sheet; color:$ink; border:1px solid $rule;
            border-radius:7px; padding:5px 23px 5px 10px; min-height:22px;}
        QComboBox#settingsChoice::drop-down {border:0; width:18px;}
        QComboBox#settingsChoice QAbstractItemView, QMenu {background:$sheet; color:$ink;
            border:1px solid $rule; selection-background-color:$soft; selection-color:$ink;}
        QMenu {padding:4px;}
        QMenu::item {padding:7px 16px; border-radius:4px;}
        QMenu::item:selected {background:$soft; color:$ink;}
        QToolTip {background:$ink; color:$sheet; border:0; padding:5px 8px;}
        QFrame#readingSheet, QFrame#editor, QFrame#translationPane {background:transparent; border:0;}
        QFrame#binding, QFrame#hairline {background:$rule; border:0;}
        QFrame#hairline {min-height:1px; max-height:1px;}
        QFrame#entrySheet {background:$sheet; border:1px solid $rule; border-radius:12px;}
        QFrame#emptyBook {background:transparent; border:0;}
        QFrame#settingsGroup {background:transparent; border:0; border-top:1px solid $rule;}
        QLabel[role="paneTitle"] {font:600 14px 'Microsoft YaHei UI'; color:$ink;}
        QLabel[role="language"], QLabel[role="characterCount"] {font-size:11px; color:$muted;}
        QPlainTextEdit#input, QPlainTextEdit#translation, QTextBrowser#entry {background:transparent; border:0;
            padding:0; selection-background-color:$soft; selection-color:$ink;}
        QPlainTextEdit#input {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:19px; color:$ink;}
        QPlainTextEdit#translation {font-size:16px; color:$ink;}
        QListWidget#words {background:transparent; border:1px solid transparent; padding:0; outline:0;}
        QListWidget#words:focus {border-color:$focus;}
        QScrollBar:horizontal {background:transparent; height:6px; margin:0 2px;}
        QScrollBar::handle:horizontal {background:#afb5a8; min-width:24px; border-radius:3px;}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {width:0;}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {background:transparent;}
        QScrollBar:vertical {background:transparent; width:8px; margin:2px 1px;}
        QScrollBar::handle:vertical {background:#afb5a8; min-height:24px; border-radius:3px;}
        QScrollBar::handle:vertical:hover {background:$muted;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
    """))



def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = theme_css("""
    p {margin:0; font-family:'Microsoft YaHei UI'; color:$ink;}
    .word {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:27px; font-weight:600; color:$ink;}
    .details {font-size:11px; color:$muted; margin-bottom:10px;}
    .gloss {font-size:17px; line-height:136%; color:$ink; margin-bottom:10px;}
    .contextTitle {font-size:11px; color:$muted; margin-top:10px; margin-bottom:6px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:16px; line-height:132%; color:$ink;}
    .hit {font-weight:600; color:$ink;}
    .translation {font-size:13px; line-height:138%; color:$ink; margin-top:8px;}
    .message {font-size:14px; line-height:140%;}
    a {color:$accent;}
""")


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
    source_label = "原文片段" if not passage.has_complete_context else "代码片段" if passage.structure == "code" else "原句" if passage.selection else "原文"
    content = (heading + f"<p class='details'>{plain(details)}</p><p class='gloss'>{plain(gloss)}</p>"
               + f"<hr style='background-color:#d5d4ce'><p class='contextTitle'>{source_label}</p>"
               + f"<p class='source'>{prefix}{source}{suffix}</p>")
    if sentence:
        content += f"<p class='translation'>{plain(sentence)}</p>"
    return content
