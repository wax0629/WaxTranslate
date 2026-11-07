"""Typography, colour and icons for the Windows reader."""
from html import escape
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def ui_icon(name, color="#52605a"):
    path = QPainterPath()
    if name == "settings":
        for y, x in ((6, 9), (12, 15), (18, 10)):
            path.moveTo(3.5, y)
            path.lineTo(x - 2, y)
            path.moveTo(x + 2, y)
            path.lineTo(20.5, y)
            path.addEllipse(QPointF(x, y), 2, 2)
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
    for filename in ("Spectral-Regular.ttf", "Spectral-SemiBold.ttf", "Spectral-Italic.ttf"):
        QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = app.palette()
    for role, color in (
        (QPalette.Window, "#f8f7f2"), (QPalette.WindowText, "#202c28"),
        (QPalette.Base, "#fffefa"), (QPalette.Text, "#202c28"),
        (QPalette.Button, "#f8f7f2"), (QPalette.ButtonText, "#26352f"),
        (QPalette.Highlight, "#cdded2"), (QPalette.HighlightedText, "#19251e"),
        (QPalette.PlaceholderText, "#647169"), (QPalette.Link, "#a33e27"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget {color:#202c28; font-size:13px;}
        QWidget#desk, QWidget#home, QWidget#readingPage, QWidget#library, QWidget#settingsSurface,
        QScrollArea#settingsPage, QScrollArea#lookupHome {background:#f8f7f2; border:0;}
        QLabel {background:transparent; border:0;}
        QLabel[role="heading"] {color:#202c28; font-size:28px; font-weight:600;}
        QLabel[role="subhead"] {color:#23332a; font-size:15px; font-weight:600;}
        QLabel[role="meta"] {color:#59665e; font-size:12px;}
        QLabel[role="warning"] {color:#a13922; font-size:13px;}
        QLabel[role="settingsSection"] {color:#33493e; font-size:16px; font-weight:600;}
        QLabel[role="shortcut"] {color:#4e5b54; background:#eeefe9; border:1px solid #cdd2c9;
            border-radius:4px; padding:2px 5px; font:12px 'Consolas';}

        QFrame#sidebar {background:#f8f7f2; border:0; border-bottom:1px solid #d5d9cf;}
        QFrame#brandBadge {background:#e4e9dd; border:0; border-radius:16px;}
        QLabel[role="brand"] {color:#1e2a25; font:600 24px 'Spectral','Georgia';}
        QLabel[role="engine"] {color:#56675e; font-size:12px;}
        QFrame#engineDot {background:#607a62; border:0; border-radius:3px;}
        QPushButton[role="nav"] {text-align:center; color:#556159; background:transparent;
            border:0; border-bottom:2px solid transparent; border-radius:0; padding:7px 9px; font-size:14px;}
        QPushButton[role="nav"]:hover {background:#eceee6; color:#23332a;}
        QPushButton[role="nav"]:checked {color:#17291f; font-weight:600; border-bottom:2px solid #bc5036;}
        QPushButton[role="nav"]:focus {color:#973d28; border-bottom:2px solid #a5432c;}

        QPushButton {color:#273631; background:#fffefa; border:1px solid #ced2ca;
            border-radius:6px; padding:7px 13px; min-height:18px;}
        QPushButton:hover {background:#ecefe8; border-color:#98a599;}
        QPushButton:pressed {background:#e1e7de; border-color:#78877b;}
        QPushButton:focus {border-color:#b04b31;}
        QPushButton:disabled {color:#79817b; background:#eeeee8; border-color:#d9dcd4;}
        QPushButton[role="primary"] {background:#24372e; color:#fffef7; border-color:#24372e;
            padding:7px 18px; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#354d3e; border-color:#354d3e;}
        QPushButton[role="primary"]:pressed {background:#17281f;}
        QPushButton[role="primary"]:focus {border-color:#dd946c;}
        QPushButton[role="primary"]:disabled {color:#6f786e; background:#e3e7de; border-color:#d5dbd1;}
        QPushButton[role="quiet"], QPushButton[role="sample"] {color:#41564a; background:transparent;
            border:1px solid transparent; padding:4px 7px; font-size:12px;}
        QPushButton[role="sample"] {color:#a7442c;}
        QPushButton[role="quiet"]:hover, QPushButton[role="sample"]:hover {background:#e6ebe2; color:#24372e;}
        QPushButton[role="quiet"]:focus, QPushButton[role="sample"]:focus {border-color:#a7442c;}
        QPushButton[role="quiet"]:disabled {color:#7b837d; background:transparent;}
        QLineEdit#search {background:#fdfdf9; border:1px solid #ced4cb; border-radius:6px;
            padding:8px 9px; selection-background-color:#dae5d8; selection-color:#1d3127;}
        QLineEdit#search:focus, QComboBox#settingsChoice:focus {border-color:#aa5035;}
        QComboBox#settingsChoice {background:#fffefa; color:#293b31; border:1px solid #c9d0c5;
            border-radius:5px; padding:5px 23px 5px 10px; min-height:22px;}
        QComboBox#settingsChoice::drop-down {border:0; width:18px;}
        QComboBox#settingsChoice QAbstractItemView, QMenu {background:#fffefa; color:#25352b;
            border:1px solid #c5cec2; selection-background-color:#e6ece1; selection-color:#263a2c;}
        QMenu {padding:4px;}
        QMenu::item {padding:6px 16px; border-radius:3px;}
        QMenu::item:selected {background:#e6ece1; color:#213529;}
        QToolTip {background:#28392f; color:#fffdf3; border:0; padding:5px 8px;}

        QFrame#readingSheet {background:#fffefa; border:1px solid #d9ddd4; border-radius:6px;}
        QFrame#editor {background:transparent; border:0;}
        QFrame#translationPane {background:#edf0e9; border:0; border-top-right-radius:5px;}
        QFrame#binding {border:0; background:#d8ded2;}
        QFrame#hairline {background:#d8ddd3; border:0; min-height:1px; max-height:1px;}
        QFrame#entrySheet {background:#fffefa; border:1px solid #d8ddd3; border-radius:6px;}
        QFrame#emptyBook {background:#eef1e9; border:0; border-radius:6px;}
        QFrame#settingsGroup {background:transparent; border:0; border-top:1px solid #78887c;}
        QLabel[role="paneTitle"] {font:600 17px 'Microsoft YaHei UI'; color:#25372d;}
        QLabel[role="language"] {font-size:12px; color:#53685a;}
        QLabel[role="characterCount"] {font-size:12px; color:#657469;}
        QPlainTextEdit#input, QPlainTextEdit#translation, QTextBrowser#entry {background:transparent; border:0;
            padding:0; selection-background-color:#d8e6d6; selection-color:#223629;}
        QPlainTextEdit#input {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:21px; color:#202c28;}
        QPlainTextEdit#translation {font-size:17px; color:#283d30;}
        QListWidget#words {background:transparent; border:1px solid transparent; padding:0; outline:0;}
        QListWidget#words:focus {border-color:#a6b3a3;}
        QListWidget#words QScrollBar:horizontal {background:transparent; height:6px; margin:0 2px;}
        QListWidget#words QScrollBar::handle:horizontal {background:#bcc5b9; min-width:24px; border-radius:3px;}
        QListWidget#words QScrollBar::add-line:horizontal, QListWidget#words QScrollBar::sub-line:horizontal {width:0;}
        QListWidget#words QScrollBar::add-page:horizontal, QListWidget#words QScrollBar::sub-page:horizontal {background:transparent;}
        QScrollBar:vertical {background:transparent; width:8px; margin:2px 1px;}
        QScrollBar::handle:vertical {background:#b9c1b6; min-height:24px; border-radius:3px;}
        QScrollBar::handle:vertical:hover {background:#94a291;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
    """)



def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = """
    p {margin:0; font-family:'Microsoft YaHei UI'; color:#202c28;}
    .word {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:34px; font-weight:600; color:#203328;}
    .details {font-size:12px; color:#5c6d61; margin-bottom:8px;}
    .gloss {font-size:18px; line-height:136%; color:#202c28; margin-bottom:8px;}
    .contextTitle {font-size:11px; color:#617365; margin-top:6px; margin-bottom:3px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:19px; line-height:122%; color:#354637;}
    .hit {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-weight:600; color:#913c29; background-color:#f7e4d5;}
    .translation {font-size:14px; line-height:138%; color:#425246; margin-top:6px;}
    .message {font-size:14px; line-height:140%;}
    a {color:#99422b;}
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
               + f"<hr style='background-color:#d5ddd2'><p class='contextTitle'>{source_label}</p>"
               + f"<p class='source'>{prefix}{source}{suffix}</p>")
    if sentence:
        content += f"<p class='translation'>{plain(sentence)}</p>"
    return content
