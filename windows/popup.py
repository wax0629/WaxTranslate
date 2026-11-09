"""The compact reading card shared by word lookups and region translations."""
from math import ceil
import re
from urllib.parse import urlencode

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from languages import SUPPORTED
from lookup import DICTIONARY
from speech import ListenButton, SpeechPlayer
from theme import APP_NAME, COLORS, marked_source, plain, theme_css, ui_icon


def action_icon(bookmark):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    painter.setPen(QPen(QColor(COLORS["accent"]), 1.4,
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


CARD_STYLE = theme_css("""
    QFrame#readingCard {background:$sheet; border:1px solid $rule; border-radius:12px;}
    QWidget#resultMasthead, QWidget#resultActions {background:transparent;}
    QLabel#headword {background:transparent; color:$ink;
        font:600 27px 'Spectral','Georgia','Microsoft YaHei UI';}
    QLabel#origin, QLabel#phonetic {background:transparent; color:$muted; font:11px 'Segoe UI','Microsoft YaHei UI';}
    QPushButton {font:12px 'Microsoft YaHei UI'; border:1px solid transparent; min-height:0;
        padding:4px; border-radius:5px; background:transparent; color:$accent;}
    QPushButton:hover {background:$soft;}
    QPushButton:disabled {color:#858a7d;}
    QPushButton#bookmark {padding:4px 0;}
    QToolButton#more, QToolButton#pin {background:transparent; color:$ink; border:1px solid transparent; padding:2px; border-radius:4px;}
    QToolButton#pin:checked, QToolButton#pin:hover, QToolButton#more:hover {background:$soft;}
    QToolButton#more::menu-indicator {image:none;}
    QPushButton:focus, QToolButton:focus {border:1px solid $focus;}
    QTextBrowser {background:transparent; border:0; padding:0;
        selection-background-color:$soft; selection-color:$ink;}
    QScrollBar:vertical {background:transparent; width:6px; margin:1px 0;}
    QScrollBar::handle:vertical {background:#afb5a8; border-radius:3px; min-height:22px;}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
""")


CARD_DOCUMENT = theme_css("""
    p {margin:0; color:$ink; font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI';}
    .details {font-size:11px; color:$muted; margin-bottom:10px;}
    .gloss {font-size:17px; font-weight:600; line-height:138%; margin-bottom:10px;}
    .region {font-size:16px; font-weight:400; line-height:140%; margin-bottom:10px;}
    .source {font-family:'Spectral','Georgia','Microsoft YaHei UI'; font-size:16px; line-height:132%;}
    .hit {font-weight:600; color:$ink;}
    .translation {font-size:13px; line-height:140%; margin-top:8px;}
    .message {font-size:14px; line-height:140%;}
    a {color:$accent;}
""")


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
        header.setContentsMargins(19, 16, 14, 0)
        header.setSpacing(10)
        self.headword = Headword(objectName="headword")
        self.headword.setTextFormat(Qt.PlainText)
        self.headword.setMinimumWidth(0)
        self.headword.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self.headword)
        self.caption = QLabel(objectName="origin")
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.PlainText)
        header.addWidget(self.caption)
        self.phonetic = Headword(objectName="phonetic")
        self.phonetic.setTextFormat(Qt.PlainText)
        self.phonetic.setMinimumWidth(0)
        self.phonetic.setMaximumWidth(110)
        self.listen = ListenButton(player if player is not None else SpeechPlayer(self))
        self.listen.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.listen.setStyleSheet(theme_css("""
            QToolButton#listen {background:transparent; color:$ink; border:1px solid transparent; border-radius:4px; padding:4px;}
            QToolButton#listen:hover {background:$soft;}
            QToolButton#listen:focus {border-color:$focus;}
            QToolButton#listen::menu-button {border:0; width:10px;}
        """))
        header.addWidget(self.listen)
        header.addStretch()
        self.pin = QToolButton(objectName="pin")
        self.pin.setCheckable(True)
        self.pin.setFixedSize(26, 26)
        self.pin.setIcon(ui_icon("pin"))
        self.pin.toggled.connect(self.update_pin)
        self.update_pin(False)
        header.addWidget(self.pin)
        close = self.dismiss_button = QPushButton(ui_icon("close", COLORS["ink"]), "", objectName="dismiss")
        close.setAccessibleName("关闭翻译结果")
        close.setFixedSize(26, 26)
        close.setToolTip("关闭 (Esc)")
        close.clicked.connect(self.close)
        header.addWidget(close, 0, Qt.AlignTop)
        body.addWidget(self.grip)
        reading = QVBoxLayout()
        reading.setContentsMargins(19, 6, 19, 12)
        reading.setSpacing(6)
        body.addLayout(reading, 1)
        reading.addWidget(self.phonetic)
        self.speech_error = QLabel()
        self.speech_error.setWordWrap(True)
        self.speech_error.setTextFormat(Qt.PlainText)
        self.speech_error.setProperty("role", "warning")
        self.speech_error.hide()
        reading.addWidget(self.speech_error)
        self.listen.notice.connect(self.show_notice)

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
        footer.setContentsMargins(19, 0, 14, 16)
        footer.setSpacing(9)
        self.save = QPushButton(action_icon(True), "加入生词本", objectName="bookmark")
        self.online = QPushButton(ui_icon("globe", COLORS["accent"]), "", objectName="expand")
        self.online.setAccessibleName("查询百科参考")
        self.online.setToolTip("仅将这个词发给 Wikidata，在卡片内查看可能的含义")
        self.expand = QPushButton("查看全句", objectName="expand")
        self.expand.setCheckable(True)
        self.copy = QPushButton(action_icon(False), "复制", objectName="copy")
        self.copy.setAccessibleName("复制译文")
        self.copy.setToolTip("复制译文")
        footer.addWidget(self.save)
        footer.addStretch()
        footer.addWidget(self.expand)
        footer.addWidget(self.copy)
        footer.addWidget(self.online)
        self.more = QToolButton(objectName="more")
        self.more.setText("···")
        self.more.setToolTip("更多操作")
        self.more.setAccessibleName("更多操作")
        self.more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.more)
        menu.aboutToShow.connect(self.prepare_menu)
        self.more.setMenu(menu)
        footer.addWidget(self.more)
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

    def update_pin(self, pinned):
        label = "取消固定" if pinned else "固定浮窗"
        self.pin.setToolTip(label)
        self.pin.setAccessibleName(label)

    def prepare_menu(self):
        menu = self.more.menu()
        menu.clear()
        if self.expand_label == "更多释义" and self.full_context:
            menu.addAction(self.expand.accessibleName(), self.expand.click)
        menu.addAction(self.copy.accessibleName(), self.copy.click)
        if self.can_search:
            menu.addAction(self.online.accessibleName(), self.online.click).setEnabled(self.online.isEnabled())
        menu.addSeparator()
        menu.addAction(self.caption.text()).setEnabled(False)
        menu.addAction("关闭浮窗", self.close)

    def copy_translation(self):
        QApplication.clipboard().setText(self.translation)
        self.copy.setText("已复制" if not self.headword.text() else "")
        self.copy.setToolTip("已复制")

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
                self.show_notice("系统未能打开浏览器。")

    def show_result(self, passage, origin, gloss, sentence, point, excerpt=None, language="", pos="",
                    can_save=True, can_search=False, references=(), web_search=False):
        self.listen.set_content(passage.word, passage.text, passage.source_code or "en")
        if not passage.selection:
            details = (language or "按英语翻译") + " → 简体中文"
            translation = gloss or sentence
            content = f"<p class='details'>{plain(details)}</p><p class='region'>{plain(translation)}</p>"
            original = content + f"<hr style='background-color:#d7d8d2'><p class='source'>{plain(passage.text)}</p>"
            self.present(origin, content, point, translation, full_context=(original, translation),
                         expand_label="查看原文")
            return
        details = " · ".join(filter(None, (pos, (language or "英语") + " → 简体中文")))
        metadata = f"<p class='details'>{plain(details)}</p>"
        meaning = metadata + f"<p class='gloss'>{plain(gloss)}</p>"

        def with_context(part, translated, prefix="", suffix=""):
            content = meaning + (f"<hr style='background-color:#d7d8d2'>"
                                 f"<p class='details'>{plain(origin)} · 原句</p>"
                                 f"<p class='source'>{prefix}{marked_source(part)}{suffix}</p>")
            if translated:
                content += f"<p class='translation'>{plain(translated)}</p>"
            return content

        standalone = passage.text.strip() == passage.word
        full = meaning if standalone else with_context(passage, sentence)
        if standalone and sentence and sentence.strip() not in (passage.word, gloss.strip()):
            full += f"<p class='translation'>{plain(sentence)}</p>"
        links = [f'<a href="https://www.wikidata.org/wiki/{entity}">条目 {i}</a>'
                 for i, entity in enumerate(references, 1)]
        if web_search:
            url = "https://www.bing.com/search?" + urlencode({"q": passage.word + " 意思"})
            links.append(f'<a href="{plain(url)}">在浏览器中搜索这个词</a>')
        if links:
            full += "<p class='details'>" + "　".join(links) + "</p>"
        if excerpt is None:
            original_only = not can_save and not sentence
            translation = (sentence or passage.word) if original_only else sentence or gloss
            summary = None
            if standalone and origin == DICTIONARY and can_save and not links:
                summary = re.match(r"^([\u3400-\u9fff]{1,12})[,，;；]\s*\S", gloss)
            brief = metadata + f"<p class='gloss'>{plain(summary[1])}</p>" if summary else full
            self.present(origin, brief, point, translation, can_save, (full, translation) if summary else None,
                         copy_original=original_only, can_search=can_search, word=passage.word,
                         phonetic=passage.phonetic, expand_label="更多释义" if summary else "查看全句")
            return
        part, translated = excerpt
        start = passage.selection[0] - part.selection[0]
        short = with_context(part, translated, "… " if start else "",
                             " …" if start + len(part.text) < len(passage.text) else "")
        self.present(origin, short, point, translated, can_save, (full, sentence), can_search=can_search,
                     word=passage.word, phonetic=passage.phonetic)

    def present(self, caption, content, point, translation="", can_save=False, full_context=None, copy_original=False,
                can_search=False, word="", phonetic="", expand_label="查看全句"):
        self.speech_error.hide()
        self.anchor = point
        self.default_context = content, translation
        self.full_context = full_context
        self.copy_original = copy_original
        self.expand_label = expand_label
        self.headword.setText(word)
        self.headword.setToolTip(word)
        self.headword.setVisible(bool(word))
        self.phonetic.setText(f"/{phonetic}/" if phonetic else "")
        self.phonetic.setToolTip(self.phonetic.text())
        self.phonetic.setVisible(bool(word and phonetic))
        self.pin.setVisible(bool(word))
        if not word:
            self.pin.setChecked(False)
        self.dismiss_button.setVisible(True)
        self.caption.setText(caption)
        self.caption.setVisible(not word)
        self.caption.setMinimumWidth(min(112, self.caption.fontMetrics().horizontalAdvance(caption) + 2))
        self.save.setText("加入生词本")
        self.save.setEnabled(True)
        self.save.setVisible(can_save)
        self.online.setText("")
        self.online.setToolTip("查询百科参考，仅发送当前词语")
        self.online.setEnabled(True)
        self.can_search = can_search
        self.online.setVisible(can_search)
        self.copy.setVisible(bool(translation))
        self.more.setVisible(bool(word and can_save))
        self.expand.setChecked(False)
        self.expand.setVisible(full_context is not None and expand_label != "更多释义")
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
        self.expand.setIcon(ui_icon("collapse" if expanded else "expand", COLORS["accent"]))
        self.expand.setText("")
        self.expand.setAccessibleName("收起" if expanded else self.expand_label)
        self.expand.setToolTip(self.expand.accessibleName())
        self.copy.setText("" if self.headword.text() else "复制原文" if self.copy_original else "复制")
        copy_hint = "复制原文" if self.copy_original else "复制译文"
        self.copy.setAccessibleName(copy_hint)
        self.copy.setToolTip("复制语境译文" if self.full_context and self.expand_label == "查看全句" and not expanded
                             else copy_hint)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setHtml(content)
        self.fit_content()
        self.text.verticalScrollBar().setValue(0)

    def show_notice(self, message):
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
        width = min(365 + margins.left() + margins.right(), area.width())
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
        self.pin.setChecked(False)
        self.press_position = None
        self.user_placed = False
        super().hideEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.shell.geometry().contains(event.position().toPoint()):
            self.close()
        else:
            super().mousePressEvent(event)

    def event(self, event):
        if (event.type() == QEvent.WindowDeactivate and self.dismiss_on_deactivate and not self.pin.isChecked()
                and self.isVisible() and QApplication.activePopupWidget() is None):
            self.close()
        return super().event(event)
