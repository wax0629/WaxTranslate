"""Capture native Windows UI fixtures using isolated data and installed dependencies.

Pass --source-root to capture the baseline checkout with the same fixture runner.
No OCR, model inference, network request, registry write or physical input is used.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.path.insert(0, str(root / "windows"))

    from PySide6.QtCore import QPoint, QProcess, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from app import Window, app_icon
    from notebook import Notebook
    from reader import Passage
    from theme import apply_theme

    app = QApplication([])
    assert app.platformName() == "windows", "Capture on an isolated Windows desktop."
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    apply_theme(app)
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {"platform": sys.platform, "qt_platform": app.platformName(),
                "source_root": str(root), "scale": os.environ.get("QT_SCALE_FACTOR", "1"), "captures": []}

    with TemporaryDirectory(prefix="wax-visual-") as temp, patch.object(QProcess, "start"):
        book = Notebook(Path(temp) / "notebook.sqlite3")
        source = "They sat on the river bank and watched the water."
        selected = source.index("bank")
        passage = Passage(source, (selected, selected + 4), source_code="en")
        book.save(passage, ("句中释义", "河岸", "他们坐在河岸边，看着水。"))
        examples = [("Parcel", "包裹"), ("warehouse", "仓库"), ("theme", "主题"),
                    ("glance", "一瞥"), ("図書館", "图书馆"), ("OCR", "光学字符识别")]
        now = int(time.time())
        for i, (word, meaning) in enumerate(reversed(examples)):
            book.record_lookup(now - (5 - i) * 900, word=word, language="ja" if word == "図書館" else "en", gloss=meaning)
        window = Window(book)
        window.gesture_ready = True
        window.gesture_warning.hide()
        window.home.set_stats(book.activity_snapshot())

        def settle():
            app.processEvents()
            QTest.qWait(180)
            app.processEvents()

        def capture(widget, name):
            widget.repaint()
            if hasattr(widget, "text"):
                widget.text.viewport().repaint()
            settle()
            ctypes.windll.dwmapi.DwmFlush()
            # Layered/translucent Windows cards return black through their
            # HWND DC. Capture the compositor's real screen rectangle instead.
            screen = widget.screen()
            point = widget.frameGeometry().topLeft() - screen.geometry().topLeft()
            pixmap = screen.grabWindow(0, point.x(), point.y(), widget.width(), widget.height())
            assert not pixmap.isNull(), name
            assert pixmap.save(str(args.output / (name + ".png"))), name
            snapshot = dict(name=name, width=widget.width(), height=widget.height(),
                            physical_width=pixmap.width(), physical_height=pixmap.height(),
                            device_ratio=widget.devicePixelRatioF())
            if hasattr(widget, "headword"):
                snapshot.update(headword=widget.headword.text(), text=widget.text.toPlainText(),
                                can_save=widget.save.isEnabled() and widget.save.isVisible())
            metadata["captures"].append(snapshot)

        try:
            area = app.primaryScreen().availableGeometry()
            for name, width, height in (("wide", 800, 620), ("narrow", 560, 485)):
                window.resize(min(width, area.width() - 24), min(height, area.height() - 24))
                window.move(area.topLeft() + QPoint(12, 12))
                window.show()
                window.activateWindow()
                for index, page in ((0, "home"), (1, "reading"), (2, "library"), (3, "settings")):
                    window.tabs.setCurrentIndex(index)
                    if index == 0:
                        window.home.set_stats(book.activity_snapshot())
                    if index == 1:
                        window.workspace.input.setPlainText(source + "\n\nShe deposited her paycheck at the bank.")
                        window.workspace.output.setPlainText("他们坐在河岸边，看着水。\n\n她把工资支票存入银行。")
                    capture(window, page + "-" + name)
                if name == "narrow":
                    assert window.width() <= width + 2, ("narrow window expanded", window.width())
            window.tabs.setCurrentIndex(0)
            point = window.mapToGlobal(QPoint(80, 90))
            card = window.card

            def show_card(*args, **kwargs):
                # Give each fixture a fresh native presentation. Reusing a
                # layered HWND at the same height can retain the preceding
                # compositor frame even after the Qt document has changed.
                card.hide()
                card.show_result(*args, **kwargs)

            show_card(passage, "句中释义", "河岸", "他们坐在河岸边，看着水。", point, language="英语", pos="名词", can_search=True)
            capture(card, "lookup-context")
            for word, source, origin, gloss, kind in (
                ('VoiceOver','在macOS辅助功能中启用VoiceOver。','名称参考','Apple 的屏幕朗读辅助功能。','功能名称'),
                ('Redis','用Docker部署Redis，通过API访问缓存。','名称参考','一种内存数据存储系统，常用于缓存。','技术名称'),
                ('UnknownSDK','用Docker部署UnknownSDK。','暂未收录','暂未确认这个代码名称的含义。','代码名称')):
                a=source.index(word)
                show_card(Passage(source,(a,a+len(word))),origin,gloss,'',point,pos=kind,can_save=word!='UnknownSDK',can_search=True)
                capture(card,'rules-'+word)
            card.close()
            word = Passage("warehouse", (0, 9), source_code="en")
            show_card(word, "英汉词典 · ECDICT", "仓库", "", point, language="英语", pos="名词", can_search=True)
            capture(card, "lookup-word")
            card.show_message("需要处理", "这里没有识别到文字。请移动到词语中央，或从托盘菜单使用框选翻译。", point)
            capture(card, "lookup-error")
            show_card(Passage("Example. " * 90), "选区译文", "很长的示例译文。" * 90, "", point, language="英语")
            capture(card, "lookup-long")
        finally:
            window.card.close()
            window.shutdown()
            window.hide()
            window.deleteLater()
            app.processEvents()
    (args.output / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Native Windows visual fixtures: {args.output}")


if __name__ == "__main__":
    main()
