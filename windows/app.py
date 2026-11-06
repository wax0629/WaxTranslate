import asyncio
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
from html import escape
import sys

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget)

from reader import Passage, recognize
from translation import translate


def plain(text):
    return escape(text).replace("\n", "<br>")


def image_point(point, logical_size, image_size):
    return QPointF(point.x() * image_size.width() / logical_size.width(),
                   point.y() * image_size.height() / logical_size.height())


def image_rect(rect, logical_size, image_size):
    top = image_point(rect.topLeft(), logical_size, image_size).toPoint()
    end = image_point(QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                      logical_size, image_size).toPoint()
    return QRect(top.x(), top.y(), end.x() - top.x(), end.y() - top.y())


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#23594c"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setFont(QFont("Microsoft YaHei UI", 29, QFont.DemiBold))
    p.setPen(Qt.white)
    p.drawText(pixmap.rect(), Qt.AlignCenter, "译")
    p.end()
    return QIcon(pixmap)


class Card(QWidget):
    dismissed = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("我靠翻译 · 结果")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 15, 14)
        bar = QHBoxLayout()
        self.caption = QLabel()
        self.caption.setStyleSheet("color:#376b58; font-weight:600")
        bar.addWidget(self.caption)
        bar.addStretch()
        close = QPushButton("关闭")
        close.setToolTip("关闭浮窗 (Esc)")
        close.clicked.connect(self.close)
        bar.addWidget(close)
        layout.addLayout(bar)
        self.text = QTextBrowser()
        self.text.setFrameShape(QTextBrowser.NoFrame)
        self.text.setOpenLinks(False)
        layout.addWidget(self.text)

    def present(self, caption, content, point):
        self.caption.setText(caption)
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(410, area.width())
        self.text.setHtml(content)
        self.text.document().setTextWidth(width - 60)
        height = min(area.height(), max(106, min(400, int(self.text.document().size().height()) + 76)))
        self.resize(width, height)
        x = max(area.left(), min(point.x() + 16, area.right() - width + 1))
        y = point.y() + 22
        if y + height > area.bottom() + 1:
            y = max(area.top(), point.y() - height - 12)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.dismissed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class Selection(QWidget):
    selected = Signal(object, object)

    def __init__(self, screen, screenshot):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("框选英文 · Esc 取消")
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.screenshot = screenshot
        self.start = None
        self.selection = QRect()
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.screenshot)
        p.fillRect(self.rect(), QColor(12, 24, 23, 88))
        if self.start is not None:
            p.save()
            p.setClipRect(self.selection)
            p.drawPixmap(self.rect(), self.screenshot)
            p.restore()
            p.setPen(QPen(QColor("#9af7c8"), 2))
            p.drawRect(self.selection.adjusted(0, 0, -1, -1))
        else:
            p.fillRect(16, 16, 234, 38, QColor("#193b33"))
            p.setPen(Qt.white)
            p.drawText(QRect(16, 16, 234, 38), Qt.AlignCenter, "拖动框选英文  ·  Esc 取消")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = event.position().toPoint()
            self.selection = QRect(self.start, self.start)
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.selection = QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.start is None:
            return
        self.mouseMoveEvent(event)
        if self.selection.width() >= 4 and self.selection.height() >= 4:
            # Selection is in logical coordinates; OCR operates on image pixels.
            r = self.selection
            crop = image_rect(r, self.size(), self.screenshot.size())
            self.hide()
            self.selected.emit(self.screenshot.copy(crop).toImage(), self.mapToGlobal(r.bottomRight()))
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


def analyze(image, point, passage):
    if passage is None:
        passage = asyncio.run(recognize(image, point))
    return passage, translate(passage)


class Window(QWidget):
    finished = Signal(int, object, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("我靠翻译 · WaxTranslate")
        self.card = Card()
        self.card.dismissed.connect(self.invalidate)
        self.overlay = None
        self.ticket = 0
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.finished.connect(self.show_result)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)
        heading = QLabel("我靠翻译")
        heading.setStyleSheet("font-size:25px; font-weight:650")
        layout.addWidget(heading)
        layout.addWidget(QLabel("指向英文，看它在这句话里的意思。"))
        for label, keys in [("悬停取词", "Alt + Shift + T"), ("框选翻译", "Alt + Shift + R")]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            shortcut = QLabel(keys)
            shortcut.setStyleSheet("color:#36584f; background:#e8eee8; padding:4px 8px")
            row.addWidget(shortcut)
            layout.addLayout(row)
        actions = QHBoxLayout()
        for label, action in [("试译示例", self.demo), ("框选英文", lambda: self.begin(True))]:
            button = QPushButton(label)
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.tray.setToolTip("我靠翻译 · Alt + Shift + T")
        menu = QMenu(self)
        menu.addAction("打开我靠翻译", self.open_home)
        menu.addAction("框选翻译", lambda: self.begin(True))
        menu.addSeparator()
        menu.addAction("退出", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        if self.tray.isSystemTrayAvailable():
            self.tray.show()
        self.registered = []
        user = ctypes.windll.user32
        user.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        user.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        for index, key in enumerate("TR", 1):
            if user.RegisterHotKey(int(self.winId()), index, 0x4005, ord(key)):  # NOREPEAT | ALT | SHIFT
                self.registered.append(index)
            else:
                warning = QLabel(f"Alt + Shift + {key} 已被占用。请关闭冲突程序后重新打开我靠翻译。")
                warning.setWordWrap(True)
                layout.addWidget(warning)
        self.setMinimumWidth(320)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def open_home(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.open_home()

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam in (1, 2):  # WM_HOTKEY
            self.begin(msg.wParam == 2)
            return True, 0
        return super().nativeEvent(event_type, message)

    def invalidate(self):
        self.ticket += 1
        if self.pending is not None:
            self.pending.cancel()
        self.card.hide()
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None

    def demo(self):
        self.invalidate()
        text = "They sat on the river bank and watched the water."
        start = text.index("bank")
        self.submit(QCursor.pos(), passage=Passage(text, (start, start + 4)))

    def begin(self, region):
        point = QCursor.pos()
        self.invalidate()
        ticket = self.ticket
        QTimer.singleShot(80, lambda: self.capture(ticket, point, region))

    def capture(self, ticket, point, region):
        if ticket != self.ticket:
            return
        screen = QApplication.screenAt(point)
        if not screen:
            return
        local = point - screen.geometry().topLeft()
        height = screen.size().height()
        if region:
            shot = screen.grabWindow(0)
        else:
            band = max(1, height // 4)
            top = max(0, min(local.y() - band // 2, height - band))
            shot = screen.grabWindow(0, 0, top, screen.size().width(), band)
        if shot.isNull():
            self.card.present("截图失败", "请返回普通桌面后重试。", point)
            return
        if region:
            overlay = Selection(screen, shot)
            self.overlay = overlay
            overlay.destroyed.connect(lambda: self.clear_overlay(overlay))
            overlay.selected.connect(lambda image, pos: self.submit(pos, image=image))
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()
        else:
            logical = screen.size()
            logical.setHeight(band)
            hit = image_point(QPointF(local.x(), local.y() - top), logical, shot.size())
            self.submit(point, image=shot.toImage(), hit=hit)

    def clear_overlay(self, closed):
        if self.overlay is closed:
            self.overlay = None

    def submit(self, point, image=None, hit=None, passage=None):
        ticket = self.ticket
        self.card.present("本机英译中", "正在读取并翻译…", point)
        future = self.pool.submit(analyze, image, hit, passage)
        self.pending = future

        def completed(job):
            if not job.cancelled():
                self.finished.emit(ticket, point, job)
        future.add_done_callback(completed)

    def show_result(self, ticket, point, job):
        if ticket != self.ticket:
            return
        try:
            passage, (origin, gloss, sentence) = job.result()
        except Exception as error:
            self.card.present("需要处理", plain(str(error)), point)
            return
        title = f"<b style='font-size:17pt'>{plain(passage.word)}</b><br>" if passage.word else ""
        content = title + f"<b style='font-size:14pt;color:#215a46'>{plain(gloss)}</b>"
        context = plain(passage.text)
        if passage.selection:
            a, b = passage.selection
            context = plain(passage.text[:a]) + "<b>" + plain(passage.word) + "</b>" + plain(passage.text[b:])
        content += f"<p>{context}</p>"
        if sentence:
            content += f"<p>{plain(sentence)}</p>"
        self.card.present(origin, content, point)

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            QApplication.quit()

    def shutdown(self):
        for index in self.registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), index)
        self.invalidate()
        self.tray.hide()
        self.pool.shutdown(wait=True, cancel_futures=True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("我靠翻译")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet("QWidget {background:#fafbf8;color:#1e2d28} "
                      "QPushButton {background:#eaf0ea;border:1px solid #bdcbc0;border-radius:4px;padding:5px 12px} "
                      "QPushButton:hover {background:#dce8dc} QMenu::item:selected {background:#dce8dc}")
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
