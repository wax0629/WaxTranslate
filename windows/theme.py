"""Paper, wood and type for the Windows reader."""
from html import escape
from pathlib import Path

from PySide6.QtCore import QDir, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"
STATIONERY = Path(__file__).with_name("stationery")


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def nav_icon(book=False, *, settings=False, home=False):
    path = QPainterPath()
    if home:
        path = QPainterPath(QPointF(3, 10.5))
        path.lineTo(12, 3.5)
        path.lineTo(21, 10.5)
        path.moveTo(5.5, 9)
        path.lineTo(5.5, 20)
        path.lineTo(10, 20)
        path.lineTo(10, 14)
        path.lineTo(14, 14)
        path.lineTo(14, 20)
        path.lineTo(18.5, 20)
        path.lineTo(18.5, 9)
    elif settings:
        for y, x in ((6, 9), (12, 15), (18, 10)):
            path.moveTo(3.5, y)
            path.lineTo(x - 2, y)
            path.moveTo(x + 2, y)
            path.lineTo(20.5, y)
            path.addEllipse(QPointF(x, y), 2, 2)
    elif book:
        path = QPainterPath()
        path.moveTo(12, 6)
        path.quadTo(7, 3, 3.5, 5.5)
        path.lineTo(3.5, 18)
        path.quadTo(7, 15.8, 12, 19)
        path.quadTo(17, 15.8, 20.5, 18)
        path.lineTo(20.5, 5.5)
        path.quadTo(16, 3, 12, 6)
        path.lineTo(12, 19)
    else:
        path.addRoundedRect(QRectF(4.5, 2.75, 15, 18.5), 2.5, 2.5)
        for y, end in ((8, 15.5), (12, 15.5), (16, 12)):
            path.moveTo(8.5, y)
            path.lineTo(end, y)
    icon = QIcon()
    for state, color in ((QIcon.Off, "#eadac0"), (QIcon.On, "#fff3df")):
        pix = QPixmap(72, 72)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(3, 3)
        painter.setPen(QPen(QColor(color), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.end()
        pix.setDevicePixelRatio(3)
        icon.addPixmap(pix, QIcon.Normal, state)
    return icon


def apply_theme(app):
    QDir.addSearchPath("stationery", str(STATIONERY))
    fonts = Path(__file__).with_name("fonts")
    for filename in ("Spectral-Regular.ttf", "Spectral-SemiBold.ttf"):
        QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = app.palette()
    for role, color in (
        (QPalette.Window, "#f6ecd6"), (QPalette.WindowText, "#382b24"),
        (QPalette.Base, "#fcf7e9"), (QPalette.Text, "#382b24"),
        (QPalette.Button, "#f4ead4"), (QPalette.ButtonText, "#49352b"),
        (QPalette.Highlight, "#e5c5aa"), (QPalette.HighlightedText, "#37231e"),
        (QPalette.PlaceholderText, "#796c5c"), (QPalette.Link, "#853c33"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget {color:#382b24; font-size:13px;}
        QWidget#desk, QWidget#home, QWidget#readingPage, QWidget#library, QWidget#settingsSurface,
        QScrollArea#settingsPage, QScrollArea#lookupHome {
            background:#f6ecd6 url(stationery:parchment.jpg) repeat; border:0;}
        QLabel {background:transparent; border:0;}
        QLabel[role="heading"], QLabel#pageTitle {color:#382820;
            font: bold 29px 'SimSun','Microsoft YaHei UI';}
        QLabel[role="subhead"] {color:#382b24; font-size:15px; font-weight:600;}
        QLabel[role="meta"] {color:#695a4a; font-size:12px;}
        QLabel[role="warning"] {color:#913a27; font-size:13px;}
        QLabel[role="settingsSection"] {color:#623f31; font-size:14px; font-weight:600;}
        QLabel[role="shortcut"] {color:#645140; background:#f1e5cb; border:1px solid #ccba98;
            border-radius:3px; padding:2px 5px; font:12px 'Consolas';}

        QFrame#sidebar {background:#3f2b22 url(stationery:walnut.jpg) repeat;
            border:0; border-right:3px double #b99e73;}
        QFrame#sidebar[compact="true"] {border-right:0; border-bottom:3px double #b99e73;}
        QFrame#brandBadge {background:#f4e8cc; border:1px solid #bd9d6b; border-radius:17px;}
        QLabel[role="brand"] {color:#fff1d8; font:600 19px 'Spectral','Georgia';}
        QLabel[role="engine"] {color:#e1d0b5; font-size:11px;}
        QFrame#railRule {background:#8b7057; border:0; max-height:1px;}
        QPushButton[role="nav"] {text-align:left; color:#f3e6d0; background:transparent;
            border:1px solid transparent; border-radius:3px; padding:9px 12px; min-height:18px; font-size:14px;}
        QPushButton[role="nav"]:hover {background:#5c4133; color:#fff5e5;}
        QPushButton[role="nav"]:checked {background:#7b3731; border:1px solid #aa6e57;
            border-left:3px solid #daba83; color:#fff2d7; font-weight:600;}
        QPushButton[role="nav"]:checked:hover {background:#89423a;}
        QPushButton[role="nav"]:focus {border-color:#f1d79e;}

        QPushButton {color:#4d382b; background:#faf2df; border:1px solid #bca582;
            border-radius:4px; padding:6px 12px; min-height:18px;}
        QPushButton:hover {background:#f0e2c4; border-color:#9a7851;}
        QPushButton:pressed {background:#e3d0ac; border-color:#815e43;}
        QPushButton:focus {border-color:#883d34;}
        QPushButton:disabled {color:#857969; background:#f1e9d7; border-color:#d6c8b0;}
        QPushButton[role="primary"] {background:#803c34; color:#fff6e4; border-color:#70332d; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#95483e; border-color:#78362f;}
        QPushButton[role="primary"]:pressed {background:#68302b;}
        QPushButton[role="primary"]:disabled {background:#e9dfcb; border-color:#cebea2; color:#796e5b;}
        QPushButton[role="quiet"] {background:transparent; color:#6f4d3e; border:1px solid transparent; padding:4px 8px;}
        QPushButton[role="quiet"]:hover {background:#eadcc0; color:#513728;}
        QPushButton[role="sample"] {background:#f4e6c9; color:#683d30; border:1px solid #c9b18d;
            border-radius:3px; padding:3px 8px; min-height:16px; font-size:12px;}
        QPushButton[role="sample"]:hover {background:#e9d8b4;}
        QPushButton[role="sample"]:focus, QPushButton[role="quiet"]:focus {border-color:#883d34;}
        QPushButton[role="primary"]:focus {border-color:#dbb576;}
        QLineEdit#search {background:#fcf6e6; color:#382b24; border:1px solid #c5b28f;
            border-radius:4px; padding:8px 12px; selection-background-color:#e5c5aa;}
        QLineEdit#search:focus, QComboBox#settingsChoice:focus {border-color:#8b4134;}
        QComboBox#settingsChoice {background:#f3e8d0; color:#4c3528; border:1px solid #bfaa88;
            border-radius:3px; padding:4px 9px; font-size:13px; min-height:23px;}
        QComboBox#settingsChoice::drop-down {border:0; width:20px;}
        QComboBox#settingsChoice QAbstractItemView, QMenu {background:#faf1dc; color:#382b24;
            border:1px solid #bca582; selection-background-color:#e5c5aa; selection-color:#37231e;}
        QMenu {padding:4px;}
        QMenu::item {padding:6px 18px; border-radius:2px;}
        QMenu::item:selected {background:#e9d7b5; color:#482c21;}
        QToolTip {background:#442f25; color:#fff3dc; border:0; padding:5px 7px;}

        QFrame#readingSheet, QFrame#entrySheet, QFrame#settingsGroup, QFrame#emptyBook {
            background:#fcf6e6; border:1px solid #c1ab86; border-radius:4px;}
        QFrame#editor {background:transparent; border:0;}
        QFrame#translationPane {background:#f3e8ce; border:0; border-top-right-radius:4px;}
        QFrame#binding {border:0; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #e1d3b6, stop:0.38 #bb9f77, stop:1 #eee0c2);}
        QFrame#hairline {background:#d2c1a1; border:0; min-height:1px; max-height:1px;}
        QLabel[role="sourceLanguage"] {font:600 24px 'Spectral','Georgia'; color:#58362c;}
        QLabel[role="targetLanguage"] {font:bold 21px 'SimSun','Microsoft YaHei UI'; color:#58362c;}
        QPlainTextEdit#input, QPlainTextEdit#translation, QTextBrowser#entry {background:transparent; border:0;
            padding:0; selection-background-color:#e9cbab; selection-color:#37231e;}
        QPlainTextEdit#input {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:19px; color:#382b24;}
        QPlainTextEdit#translation {font-size:16px; color:#49382e;}
        QTextBrowser#entry {padding:8px 11px;}
        QListWidget#words {background:#faf1db; border:1px solid #c1ab86; border-radius:4px; padding:3px; outline:0;}
        QListWidget#words::item {padding:6px; border-radius:3px;}
        QListWidget#words::item:selected {background:#ecd7b6; color:#442a22;}
        QListWidget#words:focus {border-color:#8b4134;}
        QScrollBar:vertical {background:transparent; width:9px; margin:2px 1px;}
        QScrollBar::handle:vertical {background:#c4ae8d; min-height:24px; border-radius:3px;}
        QScrollBar::handle:vertical:hover {background:#a48a66;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
    """)



def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = """
    p {margin:0; font-family:'Microsoft YaHei UI'; color:#382b24;}
    .word {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:28px; font-weight:600; color:#512e26; margin-bottom:3px;}
    .details {font-size:12px; color:#705a48; margin-bottom:6px;}
    .gloss {font-size:17px; line-height:133%; color:#382b24; margin-bottom:4px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:17px; line-height:128%; color:#594636; margin-top:4px;}
    .hit {font-weight:600; color:#673126; background-color:#ead4ae;}
    .translation {font-size:14px; line-height:130%; color:#3f3027; margin-top:7px;}
    .message {font-size:14px; line-height:140%;}
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
    content = (heading + f"<p class='details'>{plain(details)}</p><p class='gloss'>{plain(gloss)}</p>"
               + f"<hr style='background-color:#ccb894'><p class='source'>{prefix}{source}{suffix}</p>")
    if sentence:
        content += f"<p class='translation'>{plain(sentence)}</p>"
    return content
