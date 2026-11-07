"""The compact reading card shared by word lookups and region translations."""
from math import ceil
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from languages import SUPPORTED
from speech import ListenButton, SpeechPlayer
from theme import APP_NAME, DOCUMENT_STYLE, plain, result_html


def action_icon(bookmark):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    painter.setPen(QPen(QColor("#f8f9f3" if bookmark else "#566a5c"), 1.4,
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if bookmark:
        path = QPainterPath()
        path.moveTo(4, 2.5)
        path.lineTo(12, 2.5)
        path.lineTo(12, 14)
        path.lineTo(8, 11)
        path.lineTo(4, 14)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        painter.drawRoundedRect(QRectF(6, 5.5, 7.5, 8.5), 1.4, 1.4)
        path = QPainterPath()
        path.moveTo(3.5, 10)
        path.lineTo(3.5, 3.2)
        path.quadTo(3.5, 2, 4.7, 2)
        path.lineTo(10, 2)
        painter.drawPath(path)
    painter.end()
    pix.setDevicePixelRatio(3)
    return QIcon(pix)


CARD_STYLE = """
    QFrame#readingCard {background:#fffdf7; border:1px solid #c6cfc2; border-radius:9px;}
    QWidget#resultMasthead {background:#eaf0e5; border-bottom:1px solid #d7dfd2;
        border-top-left-radius:8px; border-top-right-radius:8px;}
    QWidget#resultActions {background:#f5f6ef; border-top:1px solid #e0e5d9;
        border-bottom-left-radius:8px; border-bottom-right-radius:8px;}
    QLabel#origin {background:transparent; color:#39513e; font:600 12px 'Microsoft YaHei UI';}
    QPushButton {font:12px 'Microsoft YaHei UI'; border:1px solid transparent; min-height:0;
        padding:5px 8px; border-radius:5px;}
    QPushButton#bookmark {background:#2d4334; color:#fffef8;}
    QPushButton#bookmark:hover {background:#405947;}
    QPushButton#bookmark:pressed {background:#203025;}
    QPushButton#bookmark:disabled {background:#e2e7dc; color:#5f6e60;}
    QPushButton#copy, QPushButton#dismiss, QPushButton#expand {background:transparent; color:#455a4c;}
    QPushButton#copy:hover, QPushButton#dismiss:hover, QPushButton#expand:hover {background:#dfe7d9; color:#28402e;}
    QPushButton#dismiss {font:17px 'Segoe UI'; padding:0; border-radius:10px;}
    QPushButton:focus {border-color:#b04c32;}
    QTextBrowser {background:transparent; border:0; padding:0;
        selection-background-color:#d6e3d1; selection-color:#24372e;}
    QScrollBar:vertical {background:transparent; width:6px; margin:1px 0;}
    QScrollBar::handle:vertical {background:#b9c4b4; border-radius:3px; min-height:22px;}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
"""

class Card(QWidget):
    dismissed = Signal()
    presented = Signal()
    save_requested = Signal()
    dismiss_on_deactivate = True

    def __init__(self, player=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.press_position = None
        self.user_placed = False
        self.setWindowTitle(f"{APP_NAME} · 翻译结果")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(CARD_STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 16)
        self.shell = QFrame(objectName="readingCard")
        shadow = QGraphicsDropShadowEffect(self.shell)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(27, 42, 32, 46))
        self.shell.setGraphicsEffect(shadow)
        outer.addWidget(self.shell)
        body = QVBoxLayout(self.shell)
        body.setContentsMargins(1, 1, 1, 1)
        body.setSpacing(0)

        self.grip = QWidget(objectName="resultMasthead")
        self.grip.setAttribute(Qt.WA_StyledBackground)
        self.grip.setAccessibleName("移动翻译浮窗")
        self.grip.setToolTip("按住这里拖动浮窗")
        self.grip.setCursor(Qt.OpenHandCursor)
        header = QHBoxLayout(self.grip)
        header.setContentsMargins(16, 7, 10, 7)
        header.setSpacing(7)
        mark = QSvgWidget(str(Path(__file__).resolve().parents[1] / "Assets/Brand/barrette.svg"))
        mark.setFixedSize(22, 22)
        mark.setAccessibleName(APP_NAME)
        mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(mark)
        self.caption = QLabel(objectName="origin")
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.PlainText)
        header.addWidget(self.caption, 1)
        self.listen = ListenButton(player if player is not None else SpeechPlayer(self))
        header.addWidget(self.listen)
        close = QPushButton("×", objectName="dismiss")
        close.setAccessibleName("关闭翻译结果")
        close.setFixedSize(26, 26)
        close.setToolTip("关闭 (Esc)")
        close.clicked.connect(self.close)
        header.addWidget(close, 0, Qt.AlignTop)
        body.addWidget(self.grip)
        reading = QVBoxLayout()
        reading.setContentsMargins(20, 10, 20, 10)
        reading.setSpacing(6)
        body.addLayout(reading, 1)
        self.speech_error = QLabel()
        self.speech_error.setWordWrap(True)
        self.speech_error.setTextFormat(Qt.PlainText)
        self.speech_error.setProperty("role", "warning")
        self.speech_error.hide()
        reading.addWidget(self.speech_error)
        self.listen.notice.connect(self.show_speech_error)

        self.text = QTextBrowser()
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self.open_reference)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.document().setDocumentMargin(0)
        self.text.document().setDefaultStyleSheet(DOCUMENT_STYLE)
        reading.addWidget(self.text, 1)

        self.actions = QWidget(objectName="resultActions")
        self.actions.setAttribute(Qt.WA_StyledBackground)
        footer = QHBoxLayout(self.actions)
        footer.setContentsMargins(14, 7, 12, 7)
        footer.setSpacing(4)
        self.save = QPushButton(action_icon(True), "收藏生词", objectName="bookmark")
        self.online = QPushButton("查百科", objectName="expand")
        self.online.setToolTip("仅将这个词发给 Wikidata，在卡片内查看可能的含义")
        self.expand = QPushButton("查看全句", objectName="expand")
        self.expand.setCheckable(True)
        self.copy = QPushButton(action_icon(False), "复制", objectName="copy")
        self.copy.setAccessibleName("复制译文")
        self.copy.setToolTip("复制译文")
        footer.addWidget(self.save)
        footer.addWidget(self.online)
        footer.addStretch()
        footer.addWidget(self.expand)
        footer.addWidget(self.copy)
        body.addWidget(self.actions)
        for button in (self.save, self.online, self.expand, self.copy, close):
            button.setCursor(Qt.PointingHandCursor)
            button.setIconSize(QSize(15, 15))
        self.save.clicked.connect(self.save_requested)
        self.copy.clicked.connect(self.copy_translation)
        self.expand.clicked.connect(self.display_context)
        for surface in (self.grip, self.shell, self.actions, self.text.viewport()):
            surface.installEventFilter(self)
        QShortcut(Qt.Key_Escape, self, activated=self.close)
        self.translation = ""

    def copy_translation(self):
        QApplication.clipboard().setText(self.translation)
        self.copy.setText("已复制")

    def show_message(self, caption, message, point):
        self.listen.set_content()
        self.present(caption, f"<p class='message'>{plain(message)}</p>", point)

    def show_original(self, language, original, point):
        self.listen.set_content()
        content = (f"<p class='message'>支持从{SUPPORTED}译为简体中文。</p>"
                   + f"<p class='source'>{plain(original)}</p>")
        self.present(f"{language}原文", content, point, original, copy_original=True)

    def open_reference(self, url):
        if url.scheme() == "https" and url.host() in ("www.wikidata.org", "www.bing.com"):
            if not QDesktopServices.openUrl(url):
                self.show_speech_error("系统未能打开浏览器。")

    def show_result(self, passage, origin, gloss, sentence, point, excerpt=None, language="", pos="",
                    can_save=True, can_search=False, references=(), web_search=False):
        self.listen.set_content(passage.word, passage.text, passage.source_code or "en")
        if passage.selection:
            details = language or "按英语查词"
            if pos or passage.source_code in ("", "en"):
                details += " · " + (pos or "词性待定")
        else:
            details = (language or "按英语翻译") + " → 简体中文"
        full = result_html(passage, gloss, sentence, details)
        links = [f'<a href="https://www.wikidata.org/wiki/{entity}">条目 {i}</a>'
                 for i, entity in enumerate(references, 1)]
        if web_search:
            url = "https://www.bing.com/search?" + urlencode({"q": passage.word + " 意思"})
            links.append(f'<a href="{plain(url)}">在浏览器中搜索这个词</a>')
        if links:
            full += "<p class='details'>" + "　".join(links) + "</p>"
        if excerpt is None:
            original_only = not can_save and not sentence
            self.present(origin, full, point, (sentence or passage.word) if original_only else sentence or gloss,
                         bool(passage.selection) and can_save, copy_original=original_only, can_search=can_search)
            return
        part, translated = excerpt
        start = passage.selection[0] - part.selection[0]
        short = result_html(part, gloss, translated, details, "… " if start else "",
                            " …" if start + len(part.text) < len(passage.text) else "")
        self.present(origin, short, point, translated, True, (full, sentence), can_search=can_search)

    def present(self, caption, content, point, translation="", can_save=False, full_context=None, copy_original=False,
                can_search=False):
        self.speech_error.hide()
        self.anchor = point
        self.default_context = content, translation
        self.full_context = full_context
        self.copy_original = copy_original
        self.caption.setText(caption)
        self.save.setText("收藏生词")
        self.save.setEnabled(True)
        self.save.setVisible(can_save)
        self.online.setText("查百科")
        self.online.setEnabled(True)
        self.online.setVisible(can_search)
        self.expand.setChecked(False)
        self.expand.setVisible(full_context is not None)
        self.actions.setVisible(bool(translation))
        self.display_context(False)
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            self.text.setFocus()
        self.presented.emit()

    def display_context(self, expanded):
        content, self.translation = self.full_context if expanded else self.default_context
        self.expand.setText("收起" if expanded else "查看全句")
        self.copy.setText("复制原文" if self.copy_original else "复制")
        copy_hint = "复制原文" if self.copy_original else "复制译文"
        self.copy.setAccessibleName(copy_hint)
        self.copy.setToolTip("复制语境译文" if self.full_context and not expanded else copy_hint)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setHtml(content)
        self.fit_content()
        self.text.verticalScrollBar().setValue(0)

    def show_speech_error(self, message):
        self.speech_error.setText(message)
        self.speech_error.setVisible(bool(message))
        if self.isVisible():
            self.fit_content()

    def fit_content(self):
        point = self.anchor
        screen = self.screen() if self.user_placed else QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.setScreen(screen)
        self.ensurePolished()
        width = min(402, area.width())
        # Lay out the real header/footer first, then measure the document at the
        # full viewport width. Short results shrink; only the text scrolls on long ones.
        self.setFixedWidth(width)
        self.layout().activate()
        self.shell.layout().activate()
        chrome = self.layout().totalSizeHint().height()
        document = self.text.document()
        document.setTextWidth(self.text.contentsRect().width())
        height = min(area.height(), 440, chrome + ceil(document.size().height()) + 2)
        self.resize(width, height)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        position = self.pos() if self.user_placed else point + QPoint(5, 14)
        if not self.user_placed and position.y() + height > area.bottom() + 1:
            position.setY(point.y() - height - 4)
        self.move_within(position, area)

    def closeEvent(self, event):
        self.dismissed.emit()
        super().closeEvent(event)

    def move_within(self, position, area):
        self.move(max(area.left(), min(position.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))

    def eventFilter(self, surface, event):
        kind = event.type()
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if surface is self.text.viewport():
                point = event.position() + QPoint(0, self.text.verticalScrollBar().value())
                if self.text.document().documentLayout().hitTest(point, Qt.ExactHit) >= 0:
                    return False
            self.press_position = event.globalPosition().toPoint()
            self.grab_offset = self.press_position - self.pos()
            self.dragging = False
            return True
        if kind == QEvent.MouseMove and self.press_position is not None and event.buttons() & Qt.LeftButton:
            point = event.globalPosition().toPoint()
            if self.dragging or (point - self.press_position).manhattanLength() >= QApplication.startDragDistance():
                self.dragging = self.user_placed = True
                screen = QApplication.screenAt(point) or self.screen()
                self.move_within(point - self.grab_offset, screen.availableGeometry())
            return True
        if kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self.press_position is not None:
            self.press_position = None
            return True
        return False

    def hideEvent(self, event):
        self.press_position = None
        self.user_placed = False
        super().hideEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.shell.geometry().contains(event.position().toPoint()):
            self.close()
        else:
            super().mousePressEvent(event)

    def event(self, event):
        if (event.type() == QEvent.WindowDeactivate and self.dismiss_on_deactivate
                and self.isVisible() and QApplication.activePopupWidget() is None):
            self.close()
        return super().event(event)
