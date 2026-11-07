"""Shared typography and quiet surfaces for the Windows reader."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel

APP_NAME = "WaxTranslate"


def label(text, role):
    widget = QLabel(text)
    widget.setProperty("role", role)
    return widget


def nav_icon(book=False):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)
    p.setPen(QPen(QColor("#55534b"), 1.55, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if book:
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
        QWidget#desk, QWidget#home, QWidget#library {background:#fbfaf7;}
        QFrame#sidebar {background:#f0eee7; border:0; border-right:1px solid #e3e0d8;}
        QFrame#sidebar[compact="true"] {border-right:0; border-bottom:1px solid #e3e0d8;}
        QLabel {background:transparent; border:0;}
        QLabel[role="brand"] {font-family:'Segoe UI'; font-weight:650; font-size:18px;}
        QLabel[role="heading"] {font-size:24px; font-weight:650;}
        QLabel[role="subhead"] {font-size:14px; font-weight:600;}
        QLabel[role="meta"] {color:#69685f; font-size:12px;}
        QLabel[role="language"] {color:#58594f; font-size:12px; font-weight:600;}
        QLabel[role="key"] {color:#56564e; background:#f2f1eb; border:1px solid #e2dfd6;
            border-radius:5px; padding:2px 7px; font-size:12px;}
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
        QPushButton[role="disclosure"] {background:transparent; border:1px solid transparent; padding:3px 0;
            color:#393a35; font-size:13px; font-weight:600;}
        QPushButton[role="disclosure"]:hover {color:#171814;}
        QPushButton[role="disclosure"]:focus {border-color:#6589ab;}
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
