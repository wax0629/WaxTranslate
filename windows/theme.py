"""Shared typography and quiet surfaces for the Windows reader."""
from html import escape
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"


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
    for state, color in ((QIcon.Off, "#56645d"), (QIcon.On, "#fffdf5")):
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
    fonts = Path(__file__).with_name("fonts")
    for filename in ("Spectral-Regular.ttf", "Spectral-SemiBold.ttf"):
        QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = app.palette()
    for role, color in (
        (QPalette.Window, "#f9f8f3"), (QPalette.WindowText, "#172d25"),
        (QPalette.Base, "#fffefa"), (QPalette.Text, "#263b32"),
        (QPalette.Button, "#f6f6ef"), (QPalette.ButtonText, "#284336"),
        (QPalette.Highlight, "#c8dccc"), (QPalette.HighlightedText, "#173b29"),
        (QPalette.PlaceholderText, "#68746b"), (QPalette.Link, "#315f49"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget {color:#23382e; font-size:13px;}
        QWidget#desk, QWidget#home, QWidget#readingPage, QWidget#library, QWidget#settingsSurface,
        QScrollArea#settingsPage, QScrollArea#lookupHome {background:#f9f8f3;}
        QLabel {background:transparent; border:0;}
        QLabel[role="heading"] {color:#172d25; font-size:27px; font-weight:600;}
        QLabel[role="subhead"] {color:#20392c; font-size:15px; font-weight:600;}
        QLabel[role="meta"] {color:#5f6e62; font-size:12px;}
        QLabel[role="warning"] {color:#923f24; font-size:13px;}
        QLabel[role="settingsSection"] {color:#546858; font-size:13px; font-weight:600;}
        QLabel[role="shortcut"] {color:#526357; background:#eef1e9; border:1px solid #d5ded2;
            border-radius:4px; padding:2px 5px; font-family:'Segoe UI'; font-size:11px;}

        /* Navigation shares the paper surface. The selected destination carries the ink. */
        QFrame#sidebar {background:#eeefe7; border:0; border-right:1px solid #d9ded1;}
        QFrame#sidebar[compact="true"] {border-right:0; border-bottom:1px solid #d9ded1;}
        QFrame#brandBadge {background:#fbfaf4; border:1px solid #d6dccf; border-radius:10px;}
        QLabel[role="brand"] {color:#1c3629; font-family:'Spectral','Georgia'; font-size:19px; font-weight:600;}
        QLabel[role="engine"] {color:#5c6b61; font-size:11px;}
        QFrame#railRule {background:#d5dbcf; border:0; max-height:1px;}
        QPushButton[role="nav"] {text-align:left; background:transparent; color:#45564b;
            border:1px solid transparent; border-radius:8px; padding:9px 12px; min-height:18px; font-size:14px;}
        QPushButton[role="nav"]:hover {background:#e0e6da; color:#193b2a;}
        QPushButton[role="nav"]:checked {background:#294c3b; border-color:#294c3b; color:#fffdf5; font-weight:600;}
        QPushButton[role="nav"]:checked:hover {background:#315642;}
        QPushButton[role="nav"]:focus {border-color:#7d967f;}

        /* Controls */
        QPushButton {color:#284234; background:#fffefa; border:1px solid #cdd6c9;
            border-radius:7px; padding:6px 12px; min-height:18px;}
        QPushButton:hover {background:#edf2e9; border-color:#95ac97;}
        QPushButton:pressed {background:#dde8d9; border-color:#718f75;}
        QPushButton:focus, QCheckBox:focus {border-color:#527c63;}
        QPushButton:disabled {color:#737d73; background:#f0f1eb; border-color:#dfe4d9;}
        QPushButton[role="primary"] {background:#274b38; color:#fffefa; border-color:#274b38; font-weight:600;}
        QPushButton[role="primary"]:hover {background:#365e45; border-color:#365e45;}
        QPushButton[role="primary"]:pressed {background:#183a2a;}
        QPushButton[role="primary"]:disabled {background:#ebeee6; border-color:#d8dfd2; color:#697969;}
        QPushButton[role="quiet"] {background:transparent; color:#47604e; border:1px solid transparent; padding:4px 8px;}
        QPushButton[role="quiet"]:hover {background:#e7ede2; color:#21432f;}
        QPushButton[role="sample"] {background:#e7eee2; color:#2a5036; border:1px solid #d2decf;
            border-radius:6px; padding:3px 8px; min-height:16px; font-size:12px;}
        QPushButton[role="sample"]:hover {background:#dbe8d7;}
        QPushButton[role="sample"]:focus, QPushButton[role="quiet"]:focus {border-color:#6c9174;}
        QPushButton[role="primary"]:focus {border-color:#cca76c;}
        QLineEdit#search {background:#fffefa; color:#263b32; border:1px solid #d3dace;
            border-radius:8px; padding:8px 12px; selection-background-color:#d8e7d7;}
        QLineEdit#search:focus, QComboBox#settingsChoice:focus {border-color:#65876d;}
        QComboBox#settingsChoice {background:#f4f6ee; color:#2c4c37; border:1px solid #d2dbcb;
            border-radius:7px; padding:4px 9px; font-size:13px; min-height:23px;}
        QComboBox#settingsChoice::drop-down {border:0; width:20px;}
        QComboBox#settingsChoice QAbstractItemView {background:#fffefa; border:1px solid #ced7c9;
            selection-background-color:#dce9d9; selection-color:#1d3526;}
        QMenu {background:#fffefa; color:#263b32; border:1px solid #d2d9cc; padding:4px;}
        QMenu::item {padding:6px 18px; border-radius:4px;}
        QMenu::item:selected {background:#e4ecdf; color:#1d3b28;}
        QToolTip {background:#203a2d; color:#fffdf5; border:0; padding:5px 7px;}

        /* Reading sheets, vocabulary and preferences */
        QFrame#readingSheet, QFrame#entrySheet, QFrame#settingsGroup {
            background:#fffefa; border:1px solid #d7ddcf; border-radius:14px;}
        QFrame#editor {background:#fffefa; border:0; border-radius:13px;}
        QFrame#translationPane {background:#eff3e9; border:0; border-radius:13px;}
        QFrame#binding, QFrame#hairline {background:#dbe0d4; border:0;}
        QFrame#hairline {min-height:1px; max-height:1px;}
        QLabel[role="sourceLanguage"] {font:600 24px 'Spectral','Georgia'; color:#253d2b;}
        QLabel[role="targetLanguage"] {font-size:18px; font-weight:600; color:#3c5846;}
        QPlainTextEdit#input, QPlainTextEdit#translation {background:transparent; border:0; padding:0;
            selection-background-color:#c9decd; selection-color:#193726;}
        QPlainTextEdit#input {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:19px; color:#213b2b;}
        QPlainTextEdit#translation {font-size:16px; color:#314b3a;}
        QFrame#emptyBook {background:#eef2e8; border:1px solid #d5dfce; border-radius:14px;}
        QTextBrowser#entry {background:transparent; border:0; padding:8px 11px;
            selection-background-color:#d7e6d8; selection-color:#193726;}
        QListWidget#words {background:#fffefa; border:1px solid #d7ddcf; border-radius:10px;
            padding:3px; outline:0;}
        QListWidget#words::item {padding:6px; border-radius:5px;}
        QListWidget#words::item:selected {background:#e1ebdd; color:#1d3727;}
        QListWidget#words:focus {border-color:#809c85;}
        QScrollBar:vertical {background:transparent; width:9px; margin:2px 1px;}
        QScrollBar::handle:vertical {background:#becbbb; min-height:24px; border-radius:3px;}
        QScrollBar::handle:vertical:hover {background:#95aa94;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
    """)


def plain(text):
    return escape(text).replace("\n", "<br>")


DOCUMENT_STYLE = """
    p {margin:0; font-family:'Microsoft YaHei UI'; color:#303a34;}
    .word {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:28px; font-weight:600; color:#1c3629; margin-bottom:3px;}
    .details {font-size:12px; color:#53675b; margin-bottom:6px;}
    .gloss {font-size:17px; line-height:133%; color:#283e31; margin-bottom:4px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:17px; line-height:128%; color:#46584d; margin-top:4px;}
    .hit {font-weight:600; color:#244b32; background-color:#e2ecda;}
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
