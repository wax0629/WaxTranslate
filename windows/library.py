from datetime import datetime, timedelta
import sqlite3
import time

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QStyle, QStyledItemDelegate, QTextBrowser, QVBoxLayout, QWidget)

from reader import Passage
from languages import NAMES
from speech import ListenButton
from theme import DOCUMENT_STYLE, label, marked_source, plain, result_html


class NotebookCover(QWidget):
    """A bookplate for the empty notebook."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(104, 96)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(52, 47)
        painter.rotate(-10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dbddce"))
        painter.drawRoundedRect(QRectF(-24, -29, 61, 72), 5, 5)
        painter.setPen(QPen(QColor("#a29f87"), 1))
        painter.setBrush(QColor("#fff9e5"))
        painter.drawRoundedRect(QRectF(-29, -34, 60, 73), 4, 4)
        painter.drawLine(QPointF(-24, 35.5), QPointF(26, 35.5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2e5244"))
        painter.drawRoundedRect(QRectF(-31, -38, 62, 71), 4, 4)
        painter.setPen(QPen(QColor("#6f8c71"), 1.3))
        painter.drawLine(QPointF(-23, -36), QPointF(-23, 31))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#c8a364"))
        painter.drawPolygon(QPolygonF([QPointF(9, -38), QPointF(18, -38),
                                       QPointF(18, -13), QPointF(13.5, -17), QPointF(9, -13)]))


class WordDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(95, 55)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(Qt.NoPen)
        if selected or option.state & QStyle.State_MouseOver:
            painter.setBrush(QColor("#e1eae1" if selected else "#efefe8"))
            painter.drawRoundedRect(bounds, 6, 6)
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor("#628371"), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(bounds, 6, 6)
        word, _, gloss = index.data().partition("\n")
        rows = ((word, QFont("Spectral"), 18, "#20392d"), (gloss, option.font, 12, "#55665d"))
        y = bounds.y() + 4
        for value, font, pixels, color in rows:
            font.setPixelSize(pixels)
            metrics = QFontMetrics(font)
            painter.setFont(font)
            painter.setPen(QColor(color))
            text = metrics.elidedText(" ".join(value.split()), Qt.ElideRight, max(0, bounds.width() - 18))
            painter.drawText(bounds.x() + 9, y + metrics.ascent(), text)
            y += metrics.height() + 1
        painter.restore()


class Library(QWidget):
    reader_requested = Signal()

    def __init__(self, notebook, player):
        super().__init__()
        self.setObjectName("library")
        self.notebook = notebook
        self.rows = []
        self.testing = False
        self.revealed = False
        self.session_count = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 23)
        layout.setSpacing(12)
        header = QHBoxLayout()
        self.heading = label("生词本", "heading")
        header.addWidget(self.heading)
        header.addStretch()
        self.listen = ListenButton(player)
        self.status = label("", "meta")
        self.status.setWordWrap(True)
        self.review = QPushButton("开始复习")
        self.review.clicked.connect(self.toggle_review)
        header.addWidget(self.review)
        layout.addLayout(header)
        layout.addWidget(self.status)
        self.speech_error = QLabel()
        self.speech_error.setProperty("role", "warning")
        self.speech_error.setWordWrap(True)
        self.speech_error.hide()
        layout.addWidget(self.speech_error)
        self.listen.notice.connect(self.show_speech_error)
        self.search = QLineEdit(objectName="search")
        self.search.setAccessibleName("搜索生词")
        self.search.setPlaceholderText("搜索单词、释义或原句")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.search.textChanged.connect(self.filter_rows)
        find = QShortcut(QKeySequence.Find, self)
        find.setContext(Qt.WidgetWithChildrenShortcut)
        find.activated.connect(self.focus_search)
        self.no_matches = label("没有找到匹配的生词", "meta")
        self.no_matches.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.no_matches)
        self.empty = QFrame(objectName="emptyBook")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(20, 18, 20, 18)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()
        empty_layout.addWidget(NotebookCover(), 0, Qt.AlignHCenter)
        empty_title = label("还没有收藏的生词", "subhead")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        hint = label("查词时点「收藏生词」，即可在这里复习原句。", "meta")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        empty_layout.addWidget(hint)
        read = QPushButton("打开阅读页")
        read.setProperty("role", "primary")
        read.clicked.connect(self.reader_requested)
        empty_layout.addSpacing(3)
        empty_layout.addWidget(read, 0, Qt.AlignHCenter)
        empty_layout.addStretch()
        layout.addWidget(self.empty, 1)
        self.entries = QWidget()
        content = self.columns = QBoxLayout(QBoxLayout.LeftToRight, self.entries)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)
        self.list = QListWidget(objectName="words")
        self.list.setItemDelegate(WordDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMinimumWidth(90)
        self.list.setMaximumWidth(196)
        self.list.setAccessibleName("收藏的词和语境")
        self.list.currentRowChanged.connect(self.display)
        content.addWidget(self.list, 1)
        sheet = QFrame(objectName="entrySheet")
        card = QVBoxLayout(sheet)
        card.setContentsMargins(14, 12, 14, 10)
        card.setSpacing(8)
        self.detail = QTextBrowser(objectName="entry")
        self.detail.setFrameShape(QFrame.NoFrame)
        self.detail.document().setDefaultStyleSheet(DOCUMENT_STYLE)
        self.detail.setOpenLinks(False)
        card.addWidget(self.detail, 1)
        card.addWidget(QFrame(objectName="hairline"))
        content.addWidget(sheet, 2)
        layout.addWidget(self.entries, 1)
        buttons = QHBoxLayout()
        self.reveal = QPushButton("查看释义")
        self.again = QPushButton("再学一次")
        self.known = QPushButton("记住了")
        self.remove = QPushButton("删除这条")
        self.remove.setProperty("role", "quiet")
        self.review.setProperty("role", "primary")
        self.known.setProperty("role", "primary")
        self.reveal.setProperty("role", "primary")
        buttons.addWidget(self.listen)
        buttons.addStretch()
        self.reveal.clicked.connect(self.show_answer)
        self.again.clicked.connect(lambda: self.grade(False))
        self.known.clicked.connect(lambda: self.grade(True))
        self.remove.clicked.connect(self.delete)
        for button in (self.reveal, self.again, self.known, self.remove):
            buttons.addWidget(button)
        card.addLayout(buttons)
        self.clock = QTimer(self, interval=30000)
        self.clock.timeout.connect(self.update_due)
        self.update_header()
        self.display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = event.size().width() < 520
        margins = (16, 16, 16, 16) if narrow else (30, 26, 30, 23)
        self.layout().setContentsMargins(*margins)
        self.columns.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        if narrow:
            self.list.setMaximumSize(16777215, 96)
        else:
            self.list.setMaximumSize(196, 16777215)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.clock.start()

    def hideEvent(self, event):
        self.clock.stop()
        super().hideEvent(event)

    def update_due(self):
        if not self.testing:
            self.update_header()

    def update_header(self):
        due = sum(row["due"] <= time.time() for row in self.rows)
        self.heading.setText("复习" if self.testing else "生词本")
        status = f"已收藏 {len(self.rows)} 条   ·   待复习 {due} 条"
        if self.rows and not due:
            next_due = datetime.fromtimestamp(min(row["due"] for row in self.rows))
            today = datetime.now().date()
            day = {today: "今天", today + timedelta(days=1): "明天"}.get(next_due.date(), next_due.strftime("%m/%d"))
            prefix = f"本轮已复习 {self.session_count} 条" if self.session_count else f"已收藏 {len(self.rows)} 条"
            status = f"{prefix}   ·   下次复习 {day} {next_due:%H:%M}"
        self.status.setText(status if self.rows else "")
        self.status.setVisible(bool(self.rows))
        self.review.setVisible(bool(self.rows))
        self.review.setText("结束复习" if self.testing else "开始复习")
        self.review.setEnabled(self.testing or due > 0)

    def refresh(self):
        current = self.current()
        try:
            rows = self.notebook.entries()
        except (OSError, sqlite3.Error) as error:
            self.rows = []
            self.list.clear()
            self.testing = False
            self.display()
            self.update_header()
            self.status.show()
            self.status.setText(f"生词本读取失败：{error}")
            return
        if self.testing and not any(r["due"] <= time.time() for r in rows):
            self.testing = False
        self.rows = rows
        self.revealed = False
        self.list.blockSignals(True)
        self.list.clear()
        selected = 0
        for index, row in enumerate(rows):
            item = QListWidgetItem(row["word"] + "\n" + row["gloss"])
            item.setToolTip(row["context"])
            self.list.addItem(item)
            if not self.testing and current and row["id"] == current["id"]:
                selected = index
        self.list.setCurrentRow(selected if rows else -1)
        self.list.blockSignals(False)
        self.update_header()
        self.filter_rows()

    def focus_search(self):
        if self.search.isVisible():
            self.search.setFocus()
            self.search.selectAll()

    def filter_rows(self):
        query = "" if self.testing else self.search.text().strip().casefold()
        first = -1
        for index, row in enumerate(self.rows):
            match = not query or any(query in row[key].casefold() for key in ("word", "gloss", "context", "translation"))
            self.list.item(index).setHidden(not match)
            if match and first == -1:
                first = index
        selected = self.list.currentItem()
        if selected is None or selected.isHidden():
            self.list.setCurrentRow(first)
        self.display()

    def current(self):
        i = self.list.currentRow()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def display(self, *_):
        row = self.current()
        self.speech_error.hide()
        if row:
            self.listen.set_content(row["word"], row["context"], row["language"])
        else:
            self.listen.set_content()
        self.empty.setVisible(not self.rows)
        self.entries.setVisible(bool(row))
        self.search.setVisible(not self.testing and bool(self.rows))
        self.no_matches.setVisible(not self.testing and bool(self.rows) and not row)
        self.list.setVisible(not self.testing and bool(row))
        self.detail.setVisible(bool(row))
        self.remove.setVisible(bool(row) and not self.testing)
        self.reveal.setVisible(self.testing and not self.revealed)
        for button in (self.again, self.known):
            button.setVisible(self.testing and self.revealed)
        if not row:
            self.detail.clear()
            return
        pos, word, context = row["position"], row["word"], row["context"]
        passage = Passage(context, (pos, pos + len(word)))
        if not self.testing or self.revealed:
            details = f"{NAMES.get(row['language'], row['language'])} · {row['source']}"
            content = result_html(passage, row["gloss"], row["translation"], details)
        else:
            content = f"<p class='word'>{plain(word)}</p><p class='source'>{marked_source(passage)}</p>"
        self.detail.setHtml(content)

    def show_speech_error(self, message):
        self.speech_error.setText(message)
        self.speech_error.setVisible(bool(message))

    def toggle_review(self):
        self.listen.stop()
        self.testing = not self.testing
        self.session_count = 0
        self.refresh()

    def show_answer(self):
        self.revealed = True
        self.display()

    def grade(self, remembered):
        row = self.current()
        if row and self.testing and self.revealed:
            try:
                self.notebook.review(row["id"], remembered)
            except (OSError, sqlite3.Error) as error:
                self.status.setText(f"复习进度保存失败：{error}")
                return
            self.listen.stop()
            self.session_count += 1
            self.refresh()

    def delete(self):
        row = self.current()
        if row and QMessageBox.question(self, "删除生词", f"删除「{row['word']}」的这条语境？") == QMessageBox.Yes:
            try:
                self.notebook.remove(row["id"])
            except (OSError, sqlite3.Error) as error:
                self.status.setText(f"删除失败：{error}")
                return
            self.refresh()
