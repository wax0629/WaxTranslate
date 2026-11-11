"""Portable regressions for mixed-script context routing (no desktop input)."""
from types import SimpleNamespace
import unittest

from card_policy import automatic_context, chinese_context


def selected(text, word="API", code=""):
    start = text.index(word)
    return SimpleNamespace(text=text, word=word, selection=(start, start + len(word)),
                           source_code=code, structure="sentence", has_complete_context=True)


class ContextLanguageTests(unittest.TestCase):
    def test_foreign_sentence_with_chinese_name_keeps_automatic_translation(self):
        for code in ("", "en"):
            for name in ("Beijing", "北京", "上海"):
                passage = selected(f"The API returns a label named {name}.", code=code)
                with self.subTest(code=code, name=name):
                    self.assertFalse(chinese_context(passage))
                    self.assertTrue(automatic_context(passage, confirmed=True))

    def test_chinese_sentences_keep_manual_translation_with_english_identifiers(self):
        for text in ("调用 API 查询北京。", "这个API接口返回数据。", "用Docker部署Redis，通过API访问缓存。"):
            for code in ("", "en", "zh"):
                with self.subTest(text=text, code=code):
                    passage = selected(text, code=code)
                    self.assertTrue(chinese_context(passage))
                    self.assertFalse(automatic_context(passage, confirmed=True))

    def test_japanese_and_korean_contexts_do_not_route_to_chinese(self):
        for text, code in (("東京のAPIを利用します。", "ja"), ("漢字 API 설명입니다.", "ko"),
                           ("東京のAPIを利用します。", ""), ("漢字 API 설명입니다.", "")):
            with self.subTest(text=text, code=code):
                self.assertFalse(chinese_context(selected(text, code=code)))
