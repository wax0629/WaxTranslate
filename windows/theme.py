"""Shared typography and quiet surfaces for the Windows reader."""
from html import escape

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def nav_icon(book=False, *, settings=False, home=False):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)
    p.setPen(QPen(QColor("#55534b"), 1.55, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
        p.drawPath(path)
    elif settings:
        for y, x in ((6, 9), (12, 15), (18, 10)):
            p.drawLine(QPointF(3.5, y), QPointF(x - 2, y))
            p.drawLine(QPointF(x + 2, y), QPointF(20.5, y))
            p.drawEllipse(QPointF(x, y), 2, 2)
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
        p.drawPath(path)
    else:
        p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 3, 3)
        for y, end in ((9, 16.5), (13.5, 13)):
            p.drawLine(QPointF(7.5, y), QPointF(end, y))
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


def apply_theme(app):
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet("""
        QWidget {color:#272722; font-size:13px;}
        QWidget#desk, QWidget#home, QWidget#readingPage, QWidget#library, QWidget#settingsSurface, QScrollArea#settingsPage,
        QScrollArea#lookupHome {
            background:#fbfaf7;}
        QFrame#gesturePanel {background:#eaf1eb; border:1px solid #d8e3d9; border-radius:14px;}
        QLabel[role="homeSection"] {color:#4c6758; font-weight:600; font-size:13px;}
        QLabel[role="gestureHeadline"] {color:#20392c; font-weight:650; font-size:27px;}
        QLabel[role="gestureKey"] {background:#fff; color:#284a36; border:1px solid #b5c9ba;
            border-bottom:3px solid #b5c9ba; border-radius:7px; font-size:21px; font-weight:600; padding:0 9px;}
        QLabel[role="gestureDescription"] {color:#46594c; font-size:14px;}
        QFrame#gestureSample {background:#fcfdfb; border:1px solid #d6e1d7; border-radius:8px;}
        QLabel[role="exampleText"], QPushButton#sampleWord {font-family:'Segoe UI'; font-size:17px; color:#334137;}
        QPushButton#sampleWord {background:#dceadf; color:#204f36; font-weight:600; min-height:0;
            border-radius:4px; border:1px solid transparent; padding:0 3px;}
        QPushButton#sampleWord:hover {background:#cddfd1;}
        QPushButton#sampleWord:focus {border-color:#587a61;}
        QFrame#homeStats {background:#fff; border:1px solid #e2dfd6; border-radius:11px;}
        QFrame#metricDivider {background:#e6e3da; border:0; min-width:1px; max-width:1px;}
        QLabel[role="metricValue"] {font-family:'Segoe UI'; font-size:26px; font-weight:600; color:#293d30;}
        QFrame#settingsGroup {background:#fff; border:1px solid #e2dfd6; border-radius:12px;}
        QFrame#settingsGroup QFrame#hairline {min-height:1px;}
        QFrame#sidebar {background:#f0eee7; border:0; border-right:1px solid #e3e0d8;}
        QFrame#sidebar[compact="true"] {border-right:0; border-bottom:1px solid #e3e0d8;}
        QLabel {background:transparent; border:0;}
        QLabel[role="brand"] {font-family:'Segoe UI'; font-weight:650; font-size:18px;}
        QLabel[role="heading"] {font-size:24px; font-weight:650;}
        QLabel[role="subhead"] {font-size:14px; font-weight:600;}
        QLabel[role="settingsSection"] {color:#536459; font-size:12px; font-weight:600;}
        QLabel[role="meta"] {color:#69685f; font-size:12px;}
        QLabel[role="language"] {color:#58594f; font-size:12px; font-weight:600;}
        QLabel[role="warning"] {color:#963f26;}
        QFrame#translationPane, QFrame#editor, QTextBrowser#entry, QListWidget#words {
            background:white; border:1px solid #e2dfd6; border-radius:12px;}
        QFrame#translationPane {background:#f4f4ed;}
        QFrame#hairline {background:#e6e3da; border:0; max-height:1px;}
        QPlainTextEdit#input, QPlainTextEdit#translation {background:transparent; border:0; padding:0;
            selection-background-color:#d8e6f6; selection-color:#202128;}
        QPlainTextEdit#input {font-family:'Segoe UI','Microsoft YaHei UI'; font-size:16px;}
        QPlainTextEdit#translation {font-size:16px;}
        QTextBrowser#entry {padding:10px 14px;}
        QLineEdit#search {background:white; color:#272722; border:1px solid #dedbd2;
            border-radius:7px; padding:6px 10px;}
        QLineEdit#search:focus {border-color:#6589ab;}
        QComboBox#settingsChoice {background:#f2f3ef; color:#3d5044; border:1px solid #dfe3db;
            border-radius:6px; padding:3px 8px; font-size:12px; min-height:22px;}
        QComboBox#settingsChoice:focus {border-color:#6b8d7d;}
        QComboBox#settingsChoice::drop-down {border:0; width:20px;}
        QListWidget#words {padding:4px; outline:0;}
        QListWidget#words::item {padding:6px; border-radius:5px;}
        QListWidget#words::item:selected {background:#efeee7; color:#242620;}
        QPushButton {color:#35362f; background:#fff; border:1px solid #d8d7ce;
            border-radius:7px; padding:6px 12px; min-height:18px;}
        QPushButton:hover {background:#f5f4ef; border-color:#b9b7af;}
        QPushButton:pressed {background:#eae8e0;}
        QPushButton:focus {border-color:#5073a0;}
        QPushButton:disabled {background:#f3f2ee; color:#77766e; border-color:#e5e3db;}
        QPushButton[role="primary"] {background:#292b27; color:white; border-color:#292b27; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#45473f;}
        QPushButton[role="primary"]:disabled {color:#77756e; background:#eeede7; border-color:#e5e3db;}
        QPushButton[role="quiet"] {background:transparent;
            border:1px solid transparent; color:#56574e; padding:4px 8px;}
        QPushButton[role="quiet"]:hover {background:#eeede7; color:#20211e;}
        QPushButton[role="sample"] {background:#e7efe8; color:#315947; border:1px solid transparent;
            border-radius:7px; padding:2px 8px; min-height:16px; font-size:12px;}
        QPushButton[role="sample"]:hover {background:#dae8dd;}
        QPushButton[role="sample"]:focus {border-color:#6d927b;}
        QPushButton[role="nav"] {text-align:left; background:transparent; border:1px solid transparent;
            border-radius:8px; padding:8px 10px; color:#57574e;}
        QPushButton[role="nav"]:hover {background:#e9e7df;}
        QPushButton[role="nav"]:checked {background:white; border-color:#dedbd1; color:#20211d; font-weight:600;}
        QPushButton[role="nav"]:focus, QPushButton[role="quiet"]:focus,
        QPushButton[role="primary"]:focus {border-color:#6589ab;}
        QMenu {background:white; color:#262821; border:1px solid #dedbd2; padding:4px;}
        QMenu::item {padding:6px 18px;}
        QMenu::item:selected {background:#eeede7;}
        QToolTip {background:#292b27; color:white; border:0; padding:4px;}
    """)


def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = """
    p {margin:0; font-family:'Microsoft YaHei UI'; color:#303a34;}
    .word {font-family:'Segoe UI'; font-size:26px; font-weight:600; color:#18261f; margin-bottom:3px;}
    .details {font-size:12px; color:#53675b; margin-bottom:6px;}
    .gloss {font-size:17px; line-height:133%; color:#283e31; margin-bottom:4px;}
    .source {font-family:'Segoe UI'; font-size:15px; line-height:119%; color:#57615b; margin-top:4px;}
    .hit {font-weight:600; color:#205943; background-color:#e2eee4;}
    .translation {font-size:14px; line-height:130%; color:#29332e; margin-top:7px;}
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
               + f"<hr style='background-color:#dfe5df'><p class='source'>{prefix}{source}{suffix}</p>")
    if sentence:
        content += f"<p class='translation'>{plain(sentence)}</p>"
    return content
