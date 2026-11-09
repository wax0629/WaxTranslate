"""Acceptance checks for query boundaries, pronunciation and saved context."""
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QProcess, QUrl
from PySide6.QtWidgets import QApplication

from app import Window, analyze
from card_policy import chinese_context
from notebook import Notebook
from lookup import DICTIONARY, UNKNOWN, explain
from popup import Card
from reader import Passage, sentence_at


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while not predicate():
        QApplication.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("Card did not reach the expected state")
        time.sleep(0.01)


class CardRuleTests(unittest.TestCase):
    def test_real_semantic_acceptance_matrix(self):
        samples = (
            ("They sat on the river bank and watched the water.", "bank", "句中释义", "岸", False),
            ("She deposited her paycheck at the bank.", "bank", "句中释义", "银行", False),
            ("The film uses a voice-over to narrate the story.", "voice-over", DICTIONARY, "画外音", False),
            ("在macOS辅助功能中启用VoiceOver。", "VoiceOver", "名称参考", "屏幕朗读", False),
            ("人工听音与VoiceOver", "VoiceOver", UNKNOWN, "不足以确认", False),
            ("• 更新README文档\n• 下一项API", "README", "惯用名称参考", "项目说明文件", False),
            ("字段用INTEGER存储整数。", "INTEGER", "术语参考", "整数", False),
            ("模型输入的token与访问token含义不同。", "token", "语境术语参考", "词元", False),
            ("模型输入的token与访问token含义不同。", "token", "语境术语参考", "令牌", True),
            ("用Docker部署UnknownSDK。", "UnknownSDK", UNKNOWN, "暂未确认", False),
        )
        for source, word, origin, meaning, last in samples:
            with self.subTest(source=source, word=word, last=last):
                start = source.rindex(word) if last else source.index(word)
                passage = sentence_at(source, start, start + len(word))
                result = explain(passage)[0]
                self.assertEqual(result[0], origin)
                self.assertIn(meaning, result[1])
                if chinese_context(passage):
                    self.assertEqual(result[2], "")

    def test_word_and_context_use_their_own_speech_languages(self):
        card = Card()
        self.addCleanup(card.close)
        source = "用Docker部署Redis，通过API访问缓存。"
        start = source.index("Redis")
        passage = Passage(source, (start, start + 5), source_code="en")
        card.show_result(passage, "名称参考", "内存数据存储系统", "", QPoint(10, 10))
        with patch.object(card.listen.player, "play") as play:
            card.listen.click()
            self.assertEqual(play.call_args.args[1:], ("Redis", False, "en"))
            card.listen.read.trigger()
            self.assertEqual(play.call_args.args[1:], (source, False, "zh"))
            card.listen.slow_sentence.trigger()
            self.assertEqual(play.call_args.args[1:], (source, True, "zh"))
        french = Passage("Du pain frais", (3, 7), source_code="fr", structure="title")
        card.show_result(french, "单词参考", "面包", "", QPoint(10, 10))
        with patch.object(card.listen.player, "play") as play:
            card.listen.slow.trigger()
            self.assertEqual(play.call_args.args[1:], ("pain", True, "fr"))

    def test_cjk_context_respects_japanese_and_korean(self):
        for passage in (Passage("東京銀行", (2, 4), source_code="ja"),
                        Passage("漢字 설명 API", (6, 9), source_code="ko")):
            with self.subTest(source=passage.text):
                self.assertFalse(chinese_context(passage))
        self.assertTrue(chinese_context(Passage("中文里的API", (4, 7), source_code="en")))

    def test_chinese_context_and_foreign_title_do_not_translate_automatically(self):
        source = "文档介绍cache的实现。"
        start = source.index("cache")
        passage = Passage(source, (start, start + 5), source_code="en")
        with patch("lookup.sentence_translation") as sentence:
            result = explain(passage)[0]
        self.assertEqual(result[0], DICTIONARY)
        self.assertEqual(result[2], "")
        sentence.assert_not_called()
        french = Passage("Du pain frais", (3, 7), source_code="fr", structure="title")
        result = explain(french)[0]
        self.assertEqual(result[0], "单词参考")
        self.assertIn("面包", result[1])
        self.assertEqual(result[2], "")

    def test_title_action_uses_full_translation_instead_of_word_lookup(self):
        passage = Passage("Keep this door closed", (10, 14), source_code="en", structure="title")
        card = Card()
        self.addCleanup(card.close)
        requests = []
        card.term_requested.connect(requests.append)
        card.show_result(passage, "单词参考", "门", "", QPoint(10, 10))
        card.open_reference(QUrl("waxcard://title"))
        whole, = requests
        self.assertIsNone(whole.selection)
        self.assertEqual(whole.text, passage.text)
        result = analyze(None, None, whole)[1]
        self.assertEqual(result[0], "选区译文")
        self.assertIn("门", result[1])

    def test_inline_term_click_keeps_the_occurrence_in_the_evidence(self):
        source = "🐾 模型输入的token与访问token含义不同。"
        last = source.rindex("token")
        passage = sentence_at(source, last, last + 5)
        first = passage.text.index("token")
        card = Card()
        self.addCleanup(card.close)
        requests = []
        card.term_requested.connect(requests.append)
        card.show_result(passage, "语境术语参考", "令牌", "", QPoint(10, 10))
        card.open_reference(QUrl(f"waxterm://term/{first}/{first + 5}"))
        changed, = requests
        self.assertEqual(changed.word, "token")
        self.assertEqual(changed.selection, (first, first + 5))
        self.assertEqual(changed.context_offset, source.index("token"))

    def test_definitions_do_not_leak_from_another_paragraph(self):
        source = "The authors introduce a query routing layer (QRL).\n\nThe QRL routes traffic."
        start = source.rindex("QRL")
        passage = sentence_at(source, start, start + 3)
        self.assertIn("query routing layer", passage.context)
        self.assertNotIn("query routing layer", passage.local_context)
        self.assertEqual(explain(passage)[0][0], UNKNOWN)

    def test_editor_preserves_list_heading_and_comment_boundaries(self):
        examples = (
            ("Read this README\n• Next item API", "README", "Read this README"),
            ("# README\nUse the API below", "README", "# README"),
            ("// avoid leaking data\ntype Account struct {", "avoid", "avoid leaking data"),
            ("type Account struct {\n// avoid leaking data", "avoid", "avoid leaking data"),
            ("// 🐾 avoid duplicates\n// then avoid leaking data\ntype Account struct {",
             "avoid", "🐾 avoid duplicates then avoid leaking data"),
        )
        for source, word, expected in examples:
            with self.subTest(source=source):
                start = source.rindex(word)
                passage = sentence_at(source, start, start + len(word))
                self.assertEqual(passage.text, expected)
                self.assertEqual(passage.word, word)
                self.assertEqual(passage.selection[0], expected.rindex(word))
                self.assertNotIn("type Account", passage.context)
        wrapped = "They sat on the river\nbank and watched the water."
        start = wrapped.index("bank")
        self.assertEqual(sentence_at(wrapped, start, start + 4).text,
                         "They sat on the river bank and watched the water.")

    def test_manual_translation_keeps_saved_scope_and_discards_closed_results(self):
        with TemporaryDirectory() as temp, patch.object(QProcess, "start"):
            book = Notebook(Path(temp) / "notebook.sqlite3")
            window = Window(book)
            card = window.card
            source = "用Docker部署Redis，通过API访问缓存。"
            start = source.index("Redis")
            try:
                window.lookup_text(Passage(source, (start, start + 5)), QPoint(10, 10))
                wait_for(lambda: window.saved_result is not None and card.save.isEnabled())
                translated = Future()
                with patch.object(window.pool, "submit", return_value=translated):
                    card.open_reference(QUrl("waxcard://translate"))
                translated.set_result("Use Docker to deploy Redis and access the cache through the API.")
                wait_for(lambda: bool(card.rule_translation))
                card.save.click()
                saved, = book.entries()
                self.assertEqual(saved["context"], source)
                self.assertEqual(saved["position"], start)
                self.assertEqual(saved["source"], "名称参考")
                self.assertEqual(saved["translation"], card.rule_translation)
                window.library.refresh()
                with patch.object(window.player, "play") as play:
                    window.library.listen.read.trigger()
                    self.assertEqual(play.call_args.args[1:], (source, False, "zh"))
                card.open_reference(QUrl("waxcard://translate"))
                late = Future()
                late.set_running_or_notify_cancel()
                with patch.object(window.pool, "submit", return_value=late):
                    card.open_reference(QUrl("waxcard://translate"))
                card.close()
                late.set_result("Closed query must not reappear")
                QApplication.processEvents()
                self.assertFalse(card.isVisible())
                self.assertIsNone(window.saved_result)
                self.assertNotIn("Closed query", book.entries()[0]["translation"])
            finally:
                window.shutdown()
                window.deleteLater()
