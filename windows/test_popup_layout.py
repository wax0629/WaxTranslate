import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from popup import Card
from reader import Passage


class PopupLayoutTests(unittest.TestCase):
    def test_region_starts_with_translation_and_copies_it_in_both_views(self):
        card = Card()
        self.addCleanup(card.close)
        area = QApplication.primaryScreen().availableGeometry()
        source = "Please keep this door closed."
        translated = "请保持门关闭。"
        card.show_result(Passage(source, source_code="en"), "选区译文", translated, "",
                         area.bottomRight(), language="英语")
        self.assertEqual(card.shell.width(), min(380, area.width() - 16))
        self.assertLessEqual(card.shell.height(), 400)
        self.assertTrue(area.contains(card.geometry()))
        for expanded in (False, True, False):
            with self.subTest(expanded=expanded):
                if card.expand.isChecked() != expanded:
                    card.expand.click()
                self.assertEqual(source in card.text.toPlainText(), expanded)
                self.assertIn(translated, card.text.toPlainText())
                card.copy.click()
                self.assertEqual(QApplication.clipboard().text(), translated)
        card.show_message("需要处理", "请重试。", QPoint(10, 10))
        self.assertFalse(card.expand.isVisible())
        self.assertFalse(card.headword.isVisible())
