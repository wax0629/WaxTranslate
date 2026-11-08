import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from popup import Card
from lookup import explain
from reader import Passage


class PopupLayoutTests(unittest.TestCase):
    def test_standalone_dictionary_card_keeps_secondary_actions_in_menu(self):
        word = Passage("warehouse", (0, 9), source_code="en")
        result, excerpt, language, pos = explain(word)
        card = Card()
        self.addCleanup(card.close)
        card.show_result(word, *result, QPoint(20, 20), excerpt, language, pos, can_search=True)
        self.assertEqual(card.headword.text(), "warehouse")
        self.assertTrue(card.phonetic.isVisible())
        self.assertTrue(card.listen.isVisible())
        self.assertTrue(card.pin.isVisible())
        self.assertTrue(card.save.isVisible())
        self.assertEqual(card.text.toPlainText().splitlines(), ["名词 · 英语", "仓库"])
        self.assertLess(card.height(), 190)
        card.prepare_menu()
        actions = {action.text(): action for action in card.more.menu().actions()}
        self.assertIn("英汉词典 · ECDICT", actions)
        actions["更多释义"].trigger()
        self.assertIn("货栈", card.text.toPlainText())
        actions["复制译文"].trigger()
        self.assertEqual(QApplication.clipboard().text(), result[1])
        self.assertNotIn("warehouse", card.text.toPlainText())

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
