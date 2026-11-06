from html import escape
import sqlite3
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from theme import label, nav_icon


class Library(QWidget):
    def __init__(self, notebook):
        super().__init__()
        self.setObjectName("library")
        self.notebook = notebook
        self.rows = []
        self.testing = False
        self.revealed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 22, 25, 20)
        layout.setSpacing(11)
        header = QHBoxLayout()
        self.heading = label("生词本", "heading")
        header.addWidget(self.heading)
        header.addStretch()
        self.status = label("", "meta")
        self.status.setWordWrap(True)
        self.review = QPushButton("开始复习")
        self.review.clicked.connect(self.toggle_review)
        header.addWidget(self.review)
        layout.addLayout(header)
        layout.addWidget(self.status)
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
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch()
        glyph = QLabel(alignment=Qt.AlignCenter)
        glyph.setPixmap(nav_icon(book=True).pixmap(32, 32))
        empty_layout.addWidget(glyph)
        empty_title = label("还没有收藏的生词", "subhead")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        hint = label("取词时点「收藏生词」，原句和释义会一起保存在这里。", "meta")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        empty_layout.addWidget(hint)
        empty_layout.addStretch()
        layout.addWidget(self.empty, 1)
        content = QHBoxLayout()
        content.setSpacing(9)
        self.list = QListWidget(objectName="words")
        self.list.setMinimumWidth(90)
        self.list.setMaximumWidth(146)
        self.list.setAccessibleName("收藏的词和语境")
        self.list.currentRowChanged.connect(self.display)
        content.addWidget(self.list, 1)
        self.detail = QTextBrowser(objectName="entry")
        self.detail.setOpenLinks(False)
        content.addWidget(self.detail, 2)
        layout.addLayout(content, 1)
        buttons = QHBoxLayout()
        self.reveal = QPushButton("查看释义")
        self.again = QPushButton("再学一次")
        self.known = QPushButton("记住了")
        self.remove = QPushButton("删除这条")
        self.remove.setProperty("role", "quiet")
        self.review.setProperty("role", "primary")
        self.known.setProperty("role", "primary")
        self.reveal.setProperty("role", "primary")
        buttons.addStretch()
        self.reveal.clicked.connect(self.show_answer)
        self.again.clicked.connect(lambda: self.grade(False))
        self.known.clicked.connect(lambda: self.grade(True))
        self.remove.clicked.connect(self.delete)
        for button in (self.reveal, self.again, self.known, self.remove):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.clock = QTimer(self, interval=30000)
        self.clock.timeout.connect(self.update_due)

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
        self.status.setText(f"已收藏 {len(self.rows)} 条   ·   待复习 {due} 条" if self.rows else "")
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
        self.empty.setVisible(not self.rows)
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
        marked = escape(context[:pos]) + "<b>" + escape(word) + "</b>" + escape(context[pos + len(word):])
        parts = [f"<p style='margin:4px 0 10px;font:bold 24pt Georgia;color:#272620'>{escape(word)}</p>",
                 f"<p style='margin:6px 0;font-size:12pt;color:#494940'>{marked}</p>"]
        if not self.testing or self.revealed:
            parts += [f"<p style='margin:14px 0 3px;color:#69695e;font-size:9pt'>{escape(row['source'])}</p>",
                      f"<p style='margin:0 0 8px;font-size:14pt'><b>{escape(row['gloss'])}</b></p>",
                      f"<p style='margin:0;color:#62625a'>{escape(row['translation'])}</p>"]
        self.detail.setHtml("".join(parts))

    def toggle_review(self):
        self.testing = not self.testing
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
