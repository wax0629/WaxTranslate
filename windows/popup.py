"""The compact reading card shared by word lookups and region translations."""
from math import ceil
from urllib.parse import urlencode

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from languages import SUPPORTED
from speech import ListenButton, SpeechPlayer
from theme import APP_NAME, marked_source, plain


def action_icon(bookmark):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    painter.setPen(QPen(QColor("#474743"), 1.4,
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
    QFrame#readingCard {background:#fcfbf8; border:1px solid #c7c6c0; border-radius:14px;}
    QWidget#resultMasthead, QWidget#resultActions {background:transparent;}
    QLabel#headword {background:transparent; color:#181816;
        font:500 20px 'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI';}
    QLabel#origin {background:transparent; color:#66655f; font:12px 'Microsoft YaHei UI';}
    QPushButton {font:12px 'Microsoft YaHei UI'; border:1px solid transparent; min-height:0;
        padding:4px 6px; border-radius:4px;}
    QPushButton#bookmark, QPushButton#copy, QPushButton#dismiss, QPushButton#expand {background:transparent; color:#363634;}
    QPushButton#bookmark:hover, QPushButton#copy:hover, QPushButton#dismiss:hover, QPushButton#expand:hover
        {background:#e6e5df; color:#161615;}
    QPushButton#bookmark:disabled {color:#77766e;}
    QPushButton#dismiss {font:17px 'Segoe UI'; padding:0; border-radius:10px;}
    QPushButton:focus {border-color:#555551;}
    QTextBrowser {background:transparent; border:0; padding:0;
        selection-background-color:#d5d4ce; selection-color:#161615;}
    QScrollBar:vertical {background:transparent; width:6px; margin:1px 0;}
    QScrollBar::handle:vertical {background:#bcbcb6; border-radius:3px; min-height:22px;}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
"""


CARD_DOCUMENT = """
    p {margin:0; color:#232320; font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI';}
    .details {font-size:12px; color:#66655f; margin-bottom:5px;}
    .gloss, .translation {font-size:15px; line-height:145%;}
    .source {font-size:14px; color:#595952; line-height:140%;}
    .hit {font-weight:600; color:#242420; background-color:#e7e6e0;}
    .translation {margin-top:4px;}
    .message {font-size:14px; line-height:140%;}
    a {color:#353530;}
"""


class Headword(QLabel):
    def paintEvent(self, event):
        if self.fontMetrics().horizontalAdvance(self.text()) <= self.width():
            super().paintEvent(event)
            return
        with QPainter(self) as painter:
            painter.setPen(self.palette().windowText().color())
            painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter,
                             self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width()))


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
        outer.setContentsMargins(8, 5, 8, 11)
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
        header.setContentsMargins(22, 12, 12, 0)
        header.setSpacing(9)
        self.headword = Headword(objectName="headword")
        self.headword.setTextFormat(Qt.PlainText)
        self.headword.setMinimumWidth(0)
        self.headword.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self.headword)
        self.caption = QLabel(objectName="origin")
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.PlainText)
        header.addWidget(self.caption, 1)
        self.listen = ListenButton(player if player is not None else SpeechPlayer(self))
        self.listen.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.listen.setStyleSheet("""
            QToolButton#listen {background:transparent; border:0; padding:4px 6px;}
            QToolButton#listen:hover, QToolButton#listen:focus {background:#e6e5df;}
            QToolButton#listen::menu-button {border:0; width:12px;}
        """)
        header.addWidget(self.listen)
        close = QPushButton("×", objectName="dismiss")
        close.setAccessibleName("关闭翻译结果")
        close.setFixedSize(26, 26)
        close.setToolTip("关闭 (Esc)")
        close.clicked.connect(self.close)
        header.addWidget(close, 0, Qt.AlignTop)
        body.addWidget(self.grip)
        reading = QVBoxLayout()
        reading.setContentsMargins(22, 3, 22, 10)
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
        self.text.document().setDefaultStyleSheet(CARD_DOCUMENT)
        reading.addWidget(self.text, 1)

        self.actions = QWidget(objectName="resultActions")
        self.actions.setAttribute(Qt.WA_StyledBackground)
        footer = QHBoxLayout(self.actions)
        footer.setContentsMargins(15, 0, 15, 9)
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
        if not passage.selection:
            details = (language or "按英语翻译") + " → 简体中文"
            translation = gloss or sentence
            content = f"<p class='details'>{plain(details)}</p><p class='gloss'>{plain(translation)}</p>"
            original = content + f"<hr style='background-color:#d6d5cf'><p class='source'>{plain(passage.text)}</p>"
            self.present(origin, content, point, translation, full_context=(original, translation),
                         expand_label="查看原文")
            return
        details = language or "按英语查词"
        if pos or passage.source_code in ("", "en"):
            details += " · " + (pos or "词性待定")
        meaning = f"<p class='details'>{plain(details)}</p><p class='gloss'>{plain(gloss)}</p>"

        def with_context(part, translated, prefix="", suffix=""):
            content = meaning + (f"<hr style='background-color:#d6d5cf'>"
                                 f"<p class='source'>{prefix}{marked_source(part)}{suffix}</p>")
            if translated:
                content += f"<p class='translation'>{plain(translated)}</p>"
            return content

        full = with_context(passage, sentence)
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
                         can_save, copy_original=original_only, can_search=can_search, word=passage.word)
            return
        part, translated = excerpt
        start = passage.selection[0] - part.selection[0]
        short = with_context(part, translated, "… " if start else "",
                             " …" if start + len(part.text) < len(passage.text) else "")
        self.present(origin, short, point, translated, can_save, (full, sentence), can_search=can_search,
                     word=passage.word)

    def present(self, caption, content, point, translation="", can_save=False, full_context=None, copy_original=False,
                can_search=False, word="", expand_label="查看全句"):
        self.speech_error.hide()
        self.anchor = point
        self.default_context = content, translation
        self.full_context = full_context
        self.copy_original = copy_original
        self.expand_label = expand_label
        self.headword.setText(word)
        self.headword.setToolTip(word)
        self.headword.setVisible(bool(word))
        self.caption.setText(caption)
        self.caption.setMinimumWidth(min(112, self.caption.fontMetrics().horizontalAdvance(caption) + 2))
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
        self.expand.setText("收起" if expanded else self.expand_label)
        self.copy.setText("复制原文" if self.copy_original else "复制")
        copy_hint = "复制原文" if self.copy_original else "复制译文"
        self.copy.setAccessibleName(copy_hint)
        self.copy.setToolTip("复制语境译文" if self.full_context and self.expand_label == "查看全句" and not expanded
                             else copy_hint)
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
        margins = self.layout().contentsMargins()
        width = min(380 + margins.left() + margins.right(), area.width())
        # Lay out the real header/footer first, then measure the document at the
        # full viewport width. Short results shrink; only the text scrolls on long ones.
        self.setFixedWidth(width)
        self.layout().activate()
        self.shell.layout().activate()
        chrome = self.layout().totalSizeHint().height()
        document = self.text.document()
        document.setTextWidth(self.text.contentsRect().width())
        height = min(area.height(), 400 + margins.top() + margins.bottom(), chrome + ceil(document.size().height()) + 2)
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
