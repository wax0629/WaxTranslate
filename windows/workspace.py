"""In-window translation for typed or pasted text."""
from threading import Event

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextLine, QTextOption
from PySide6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QFrame, QHBoxLayout, QPlainTextEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from reader import WORD_TOKEN, nearest_box, sentence_at
from theme import label
from translation import translate_text


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


class ReadingEditor(QPlainTextEdit):
    lookup_requested = Signal(object, object)
    article_pasted = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.single_click = False
        self.press_position = None

    def insertFromMimeData(self, source):
        first_paste = self.document().isEmpty() and source.hasText() and source.text().strip()
        super().insertFromMimeData(source)
        if first_paste and not self.document().isEmpty():
            self.article_pasted.emit()

    def mousePressEvent(self, event):
        self.press_position = None
        if self.single_click and event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier:
            self.press_position = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.press_position is not None and
                (event.position() - self.press_position).manhattanLength() >= QApplication.startDragDistance()):
            self.press_position = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        press, self.press_position = self.press_position, None
        super().mouseReleaseEvent(event)
        if (press is not None and event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier
                and (event.position() - press).manhattanLength() < QApplication.startDragDistance()
                and not self.textCursor().hasSelection()):
            self.lookup_point(event.position())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & ~Qt.KeypadModifier == Qt.AltModifier:
            self.lookup_cursor()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.press_position = None
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.LeftButton:
            self.lookup_point(event.position())

    def lookup_point(self, point):
        if not self.viewport().rect().contains(point.toPoint()):
            return False
        current = self.cursorForPosition(point.toPoint()).block()
        boxes = []
        for block in (current, current.previous(), current.next()):
            if not block.isValid() or not block.isVisible():
                continue
            origin = self.blockBoundingGeometry(block).translated(self.contentOffset()).topLeft()
            local = point - origin
            layout = block.layout()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                rect = line.naturalTextRect()
                if not rect.adjusted(-line.height(), -line.height(), line.height(), line.height()).contains(local):
                    continue
                if rect.contains(local):
                    index = line.xToCursor(local.x(), QTextLine.CursorOnCharacter)
                    if index < line.textStart() + line.textLength():
                        if self.lookup_at(block.position() + index):
                            return True
                        # A deliberate hit on a slash, punctuation or a number
                        # does not select an adjacent token.
                        char = block.text().encode("utf-16-le")[index * 2:(index + 1) * 2]
                        if not char.decode("utf-16-le", errors="ignore").isspace():
                            return False
                boxes.extend(self.nearby_words(block, line, local.x(), origin))
        hit = nearest_box(point, boxes)
        return self.lookup_at(hit) if hit is not None else False

    @staticmethod
    def nearby_words(block, line, x, origin):
        # Text positions returned by Qt are UTF-16 units. Limit geometry
        # work to words near the pointer on this visual (possibly wrapped) line.
        low, high = sorted((line.xToCursor(x - line.height()), line.xToCursor(x + line.height())))
        value = block.text()
        previous = units = 0
        for match in WORD_TOKEN.finditer(value):
            start = units + utf16_length(value[previous:match.start()])
            units = start + utf16_length(match.group())
            previous = match.end()
            if units < low or not any(c.isalpha() for c in match.group()):
                continue
            if start > high:
                break
            left = max(start, line.textStart())
            right = min(units, line.textStart() + line.textLength())
            if right <= left:
                continue
            a, b = sorted((line.cursorToX(left)[0], line.cursorToX(right)[0]))
            yield block.position() + start, QRectF(a, line.y(), b - a, line.height()).translated(origin)

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
        sheet = QFrame(objectName="readingSheet")
        layout.addWidget(sheet)
        spread = QVBoxLayout(sheet)
        spread.setContentsMargins(1, 1, 1, 1)
        spread.setSpacing(0)
        self.panes = QBoxLayout(QBoxLayout.LeftToRight)
        self.panes.setSpacing(0)
        spread.addLayout(self.panes, 1)
        self.input = ReadingEditor(objectName="input")
        self.input.setPlaceholderText("在这里粘贴英文文章…")
        self.input.setAccessibleName("英文原文")
        self.output = QPlainTextEdit(objectName="translation")
        self.output.setAccessibleName("简体中文译文")
        self.output.setReadOnly(True)
        self.binding = QFrame(objectName="binding")
        self.binding.setMinimumSize(1, 1)
        self.headers = []
        for name, editor, panel in (("English", self.input, "editor"),
                                    ("简体中文", self.output, "translationPane")):
            frame = QFrame(objectName=panel)
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 12, 16, 13)
            box.setSpacing(10)
            toolbar = QWidget()
            self.headers.append(toolbar)
            header = QHBoxLayout(toolbar)
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)
            language = label(name, "sourceLanguage" if editor is self.input else "targetLanguage")
            header.addWidget(language)
            header.addStretch()
            if editor is self.input:
                self.example = QPushButton("试读示例")
                self.example.setProperty("role", "sample")
                self.example.setToolTip("打开一段示例，试试查词、听读和收藏")
                self.lookup_hint = QCheckBox("单击查词")
                self.lookup_hint.setToolTip("开启后单击查词，拖动仍可选字。关闭后可双击查词或按 Alt+Enter。")
                self.lookup_hint.toggled.connect(self.set_single_click)
                self.lookup_hint.clicked.connect(self.keep_reading_preference)
                self.user_chose_mode = False
                self.input.article_pasted.connect(self.start_reading)
                self.example.clicked.connect(self.start_reading)
                header.addWidget(self.example)
                header.addWidget(self.lookup_hint)
            else:
                self.copy = QPushButton("复制译文")
                self.copy.setProperty("role", "quiet")
                self.copy.setToolTip("复制整段译文 (Ctrl+Shift+C)")
                self.copy.clicked.connect(self.copy_result)
                header.addWidget(self.copy)
                self.panes.addWidget(self.binding)
            box.addWidget(toolbar)
            box.addWidget(QFrame(objectName="hairline"))
            editor.setTabChangesFocus(True)
            editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            editor.setMinimumSize(32, 48)
            editor.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            editor.document().setDocumentMargin(0)
            box.addWidget(editor, 1)
            self.panes.addWidget(frame, 1)
        spread.addWidget(QFrame(objectName="hairline"))
        actions = QHBoxLayout()
        actions.setContentsMargins(15, 10, 15, 10)
        actions.setSpacing(9)
        self.submit = QPushButton("翻译")
        self.submit.setProperty("role", "primary")
        self.submit.clicked.connect(self.submit_or_cancel)
        actions.addWidget(self.submit)
        self.shortcut_hint = label("Ctrl + Enter", "shortcut")
        actions.addWidget(self.shortcut_hint)
        actions.addStretch()
        spread.addLayout(actions)
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

    def set_single_click(self, checked):
        self.input.single_click = checked

    def keep_reading_preference(self):
        self.user_chose_mode = True

    def start_reading(self):
        if not self.user_chose_mode:
            self.lookup_hint.setChecked(True)

    def event(self, event):
        if event.type() == QEvent.LayoutRequest and self.headers:
            # Give both sides of the spread one baseline, including when a
            # font change or the sample-to-reading switch changes a button's hint.
            height = max(34, *(h.layout().sizeHint().height() for h in self.headers))
            for toolbar in self.headers:
                if toolbar.minimumHeight() != height:
                    toolbar.setMinimumHeight(height)
        return super().event(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        horizontal = event.size().width() >= 600
        self.panes.setDirection(QBoxLayout.LeftToRight if horizontal else QBoxLayout.TopToBottom)
        if horizontal:
            self.binding.setMinimumSize(4, 1)
            self.binding.setMaximumSize(4, 16777215)
        else:
            self.binding.setMinimumSize(1, 1)
            self.binding.setMaximumSize(16777215, 1)

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
