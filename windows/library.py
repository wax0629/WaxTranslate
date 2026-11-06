from html import escape
import sqlite3
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)


class Library(QWidget):
    def __init__(self, notebook):
        super().__init__()
        self.notebook = notebook
        self.rows = []
        self.testing = False
        self.revealed = False
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.review = QPushButton("开始复习")
        self.review.clicked.connect(self.toggle_review)
        header.addWidget(self.status, 1)
        header.addWidget(self.review)
        layout.addLayout(header)
        self.list = QListWidget()
        self.list.setMaximumHeight(120)
        self.list.currentRowChanged.connect(self.display)
        layout.addWidget(self.list)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        layout.addWidget(self.detail, 1)
        buttons = QHBoxLayout()
        self.reveal = QPushButton("查看释义")
        self.again = QPushButton("再学一次")
        self.known = QPushButton("记住了")
        self.remove = QPushButton("删除这条")
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
        self.status.setText(f"{len(self.rows)} 条生词 · {due} 条待复习" if self.rows else "在取词浮窗中点「收藏生词」，即可在这里复习。")
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
            item = QListWidgetItem(row["word"] + "    " + row["gloss"])
            item.setToolTip(row["context"])
            self.list.addItem(item)
            if not self.testing and current and row["id"] == current["id"]:
                selected = index
        self.list.setCurrentRow(selected if rows else -1)
        self.list.blockSignals(False)
        self.update_header()
        self.display()

    def current(self):
        i = self.list.currentRow()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def display(self, *_):
        row = self.current()
        self.list.setVisible(not self.testing and bool(self.rows))
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
        parts = [f"<h2>{escape(word)}</h2>", f"<p>{marked}</p>"]
        if not self.testing or self.revealed:
            parts += [f"<p>{escape(row['source'])} · <b>{escape(row['gloss'])}</b></p>",
                      f"<p>{escape(row['translation'])}</p>"]
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
