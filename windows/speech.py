"""User-triggered pronunciation shared by lookup and review."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QToolButton


from theme import theme_css


WORKER = Path(__file__).with_name("speech_worker.py")


class SpeechPlayer(QObject):
    changed = Signal()
    failed = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.owner = None

    def play(self, owner, text, slow=False, language="en"):
        self.stop()
        process = QProcess(self)
        self.process, self.owner = process, owner
        def send_utterance():
            if self.process is not process:
                process.kill()
                return
            process.write(json.dumps((text, slow, language), ensure_ascii=False).encode("utf-8"))
            process.closeWriteChannel()

        process.started.connect(send_utterance)
        process.finished.connect(lambda code, _status: self.finished(process, code))
        process.errorOccurred.connect(lambda error: self.finished(process, 1) if error == QProcess.FailedToStart else None)
        process.start(str(Path(sys.executable).with_name("pythonw.exe")),
                      [str(WORKER)])
        self.changed.emit()

    def finished(self, process, code):
        if process is self.process:
            owner = self.owner
            self.process = self.owner = None
            self.changed.emit()
            if code:
                message = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
                self.failed.emit(owner, message or "朗读未能启动，请重试。")
        process.deleteLater()

    def stop(self):
        process = self.process
        if process is not None:
            self.process = self.owner = None
            process.kill()
            self.changed.emit()

    def shutdown(self):
        self.stop()
        for process in self.findChildren(QProcess):
            if process.state() != QProcess.NotRunning:
                process.kill()
                process.waitForFinished(1000)


def speaker_icon(playing):
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    ink = QColor("#363634")
    painter.setPen(QPen(ink, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if playing:
        painter.setBrush(ink)
        painter.drawRoundedRect(QRectF(4.2, 4.2, 7.6, 7.6), 1, 1)
    else:
        path = QPainterPath()
        path.moveTo(2, 6)
        path.lineTo(5, 6)
        path.lineTo(8.5, 3)
        path.lineTo(8.5, 13)
        path.lineTo(5, 10)
        path.lineTo(2, 10)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawArc(QRectF(6, 4, 7, 8), -50 * 16, 100 * 16)
    painter.end()
    pix.setDevicePixelRatio(3)
    return QIcon(pix)


class ListenButton(QToolButton):
    notice = Signal(str)

    def __init__(self, player):
        super().__init__()
        self.player = player
        self.word = self.sentence = ""
        self.language = "en"
        self.sentence_language = "en"
        self.setObjectName("listen")
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self.setPopupMode(QToolButton.MenuButtonPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setStyleSheet(theme_css("""
            QToolButton#listen {font:12px 'Microsoft YaHei UI'; color:$ink;
                background:$soft; border:1px solid transparent; border-radius:14px; padding:3px 7px;}
            QToolButton#listen:hover {background:$rule;}
            QToolButton#listen:focus {border-color:$focus;}
            QToolButton#listen::menu-button {border:0; border-left:1px solid $rule;
                border-top-right-radius:4px; border-bottom-right-radius:4px; width:16px;}
        """))
        menu = QMenu(self)
        self.setMenu(menu)
        self.slow = menu.addAction("慢速读词", lambda: self.play(self.word, True))
        self.read = menu.addAction("朗读原句", lambda: self.play(self.sentence, language=self.sentence_language))
        self.slow_sentence = menu.addAction("慢速读原句", lambda: self.play(self.sentence, True, self.sentence_language))
        self.clicked.connect(self.toggle)
        self.player.changed.connect(self.update_state)
        self.player.failed.connect(self.on_error)
        self.update_state()
        self.hide()

    def set_content(self, word="", sentence="", language="en", *, sentence_language=None):
        sentence_language = sentence_language or language
        if (word, sentence, language, sentence_language) != (self.word, self.sentence, self.language, self.sentence_language):
            self.stop()
        self.word, self.sentence, self.language = word, sentence, language
        self.sentence_language = sentence_language
        self.slow.setVisible(bool(word))
        self.read.setVisible(bool(word and sentence))
        self.slow_sentence.setVisible(bool(sentence))
        self.setVisible(bool(word or sentence))
        self.update_state()

    def update_state(self):
        playing = self.player.owner is self
        self.setIcon(speaker_icon(playing))
        self.setText("停止" if playing else "听读")
        title = "停止朗读" if playing else ("朗读单词" if self.word else "朗读原文")
        self.setAccessibleName(title)
        self.setToolTip(title + "；右侧箭头可选择慢速")

    def toggle(self):
        if self.player.owner is self:
            self.stop()
        else:
            self.play(self.word or self.sentence)

    def play(self, text, slow=False, language=None):
        if text:
            self.notice.emit("")
            self.player.play(self, text, slow, language or self.language)

    def stop(self):
        if self.player.owner is self:
            self.player.stop()

    def on_error(self, owner, message):
        if owner is self:
            self.notice.emit(message)

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)
