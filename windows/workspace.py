"""In-window translation for typed or pasted text."""
from threading import Event

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextLine, QTextOption
from PySide6.QtWidgets import (QApplication, QBoxLayout, QFrame, QHBoxLayout, QPlainTextEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from reader import WORD_TOKEN, sentence_at
from theme import label
from translation import translate_text


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


class ReadingEditor(QPlainTextEdit):
    lookup_requested = Signal(object, object)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & ~Qt.KeypadModifier == Qt.AltModifier:
            self.lookup_cursor()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.LeftButton:
            self.lookup_point(event.position())

    def lookup_point(self, point):
        block = self.cursorForPosition(point.toPoint()).block()
        local = point - self.blockBoundingGeometry(block).translated(self.contentOffset()).topLeft()
        layout = block.layout()
        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            if line.naturalTextRect().contains(local):
                pos = block.position() + line.xToCursor(local.x(), QTextLine.CursorOnCharacter)
                return self.lookup_at(pos)
        return False

    def lookup_cursor(self):
        cursor = self.textCursor()
        return self.lookup_at(cursor.selectionStart(), cursor.selectionEnd(), at_caret=True)

    def lookup_at(self, pos, end=None, at_caret=False):
        block = self.document().findBlock(pos)
        if not block.isValid():
            return False
        value = block.text()
        # Qt indexes UTF-16 units. Passage indexes Python characters, including
        # when the paper contains a supplementary-plane symbol before the word.
        relative = pos - block.position()
        offset = len(value.encode("utf-16-le")[:relative * 2].decode("utf-16-le", errors="ignore"))
        for word in WORD_TOKEN.finditer(value):
            if not (word.start() <= offset < word.end() or at_caret and end == pos and offset == word.end()):
                continue
            if not any(char.isalpha() for char in word.group()):
                return False
            begin = block.position() + utf16_length(value[:word.start()])
            finish = begin + utf16_length(word.group())
            if end is not None and end != pos and (pos != begin or end != finish):
                return False
            cursor = QTextCursor(self.document())
            cursor.setPosition(begin)
            cursor.setPosition(finish, QTextCursor.KeepAnchor)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
            text = self.toPlainText()
            start = len(text.encode("utf-16-le")[:begin * 2].decode("utf-16-le"))
            self.lookup_requested.emit(sentence_at(text, start, start + len(word.group())),
                                       self.viewport().mapToGlobal(self.cursorRect().bottomRight()))
            return True
        return False


class TextWorkspace(QWidget):
    completed = Signal(object)

    def __init__(self, pool):
        super().__init__()
        self.pool = pool
        self.pending = None
        self.stop = None
        self.completed.connect(self.show_result)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        self.panes = QBoxLayout(QBoxLayout.LeftToRight)
        self.panes.setSpacing(10)
        layout.addLayout(self.panes, 1)
        self.input = ReadingEditor(objectName="input")
        self.input.setPlaceholderText("粘贴英文文章，双击单词查释义…")
        self.input.setAccessibleName("英文原文")
        self.output = QPlainTextEdit(objectName="translation")
        self.output.setAccessibleName("简体中文译文")
        self.output.setReadOnly(True)
        for name, editor, panel in (("英文原文", self.input, "editor"),
                                    ("简体中文译文", self.output, "translationPane")):
            frame = QFrame(objectName=panel)
            box = QVBoxLayout(frame)
            box.setContentsMargins(15, 12, 15, 10)
            box.setSpacing(9)
            tools = QWidget()
            tools.setFixedHeight(26)
            header = QHBoxLayout(tools)
            header.setContentsMargins(0, 0, 0, 0)
            header.addWidget(label(name, "language"))
            header.addStretch()
            if editor is self.input:
                self.example = QPushButton("试读示例")
                self.example.setProperty("role", "sample")
                self.example.setToolTip("打开一段示例，试试查词、听读和收藏")
                self.lookup_hint = label("双击查词", "meta")
                self.lookup_hint.setToolTip("也可将光标放在词上，按 Alt+Enter")
                header.addWidget(self.example)
                header.addWidget(self.lookup_hint)
            box.addWidget(tools)
            editor.setTabChangesFocus(True)
            editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            editor.setMinimumSize(32, 48)
            editor.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            editor.document().setDocumentMargin(0)
            box.addWidget(editor, 1)
            self.panes.addWidget(frame, 1)
        actions = QHBoxLayout()
        self.submit = QPushButton("翻译")
        self.submit.setProperty("role", "primary")
        self.submit.clicked.connect(self.submit_or_cancel)
        actions.addWidget(self.submit)
        self.shortcut_hint = label("Ctrl + Enter", "meta")
        actions.addWidget(self.shortcut_hint)
        actions.addStretch()
        self.copy = QPushButton("复制译文")
        self.copy.setToolTip("复制整段译文 (Ctrl+Shift+C)")
        self.copy.clicked.connect(self.copy_result)
        actions.addWidget(self.copy)
        layout.addLayout(actions)
        run = QShortcut(self)
        run.setKeys([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        run.setContext(Qt.WidgetWithChildrenShortcut)
        run.activated.connect(self.translate_text)
        copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy.setContext(Qt.WidgetWithChildrenShortcut)
        copy.activated.connect(self.copy_result)
        self.escape = QShortcut(QKeySequence("Esc"), self)
        self.escape.setContext(Qt.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.reset_result)
        self.input.textChanged.connect(self.reset_result)
        self.reset_result()
        self.setFocusProxy(self.input)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = QBoxLayout.LeftToRight if event.size().width() >= 600 else QBoxLayout.TopToBottom
        self.panes.setDirection(direction)

    def reset_result(self):
        previous, self.pending = self.pending, None
        if self.stop is not None:
            self.stop.set()
            self.stop = None
        if previous is not None:
            previous.cancel()
        self.output.clear()
        self.output.setPlaceholderText("译文将在这里显示")
        self.copy.setText("复制译文")
        self.copy.setEnabled(False)
        self.set_busy(False)
        has_text = bool(self.input.toPlainText().strip())
        self.submit.setEnabled(has_text)
        self.example.setVisible(not has_text)
        self.lookup_hint.setVisible(has_text)

    def set_busy(self, busy):
        self.submit.setText("取消" if busy else "翻译")
        self.submit.setToolTip("取消本次翻译 (Esc)" if busy else "翻译文本 (Ctrl+Enter)")
        self.shortcut_hint.setText("Esc" if busy else "Ctrl + Enter")
        self.escape.setEnabled(busy)

    def submit_or_cancel(self):
        if self.pending is None:
            self.translate_text()
        else:
            self.reset_result()

    def translate_text(self):
        text = self.input.toPlainText().strip()
        if not text or self.pending is not None:
            return
        self.reset_result()
        self.set_busy(True)
        self.output.setPlaceholderText("正在本机翻译…")
        self.stop = Event()
        self.pending = self.pool.submit(translate_text, text, self.stop)
        self.pending.add_done_callback(self.completed.emit)

    def show_result(self, job):
        if job is not self.pending:
            return
        self.pending = None
        self.stop = None
        self.set_busy(False)
        try:
            translation = job.result()
        except Exception as error:
            self.output.setPlainText(str(error))
            return
        self.output.setPlainText(translation)
        self.copy.setEnabled(bool(translation))

    def copy_result(self):
        if self.copy.isEnabled():
            QApplication.clipboard().setText(self.output.toPlainText())
            self.copy.setText("已复制")
