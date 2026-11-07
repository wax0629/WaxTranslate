import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QPoint, QProcess
from PySide6.QtWidgets import QApplication

from app import Window, online_meanings
from lookup import DICTIONARY, UNKNOWN, explain
from notebook import Notebook
from online_terms import search_entities
from reader import Passage, sentence_at


def selected(text, word):
    pos = text.rindex(word)
    return sentence_at(text, pos, pos + len(word))


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while not predicate():
        QApplication.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("Lookup did not reach the expected state")
        time.sleep(0.01)


class LookupTests(unittest.TestCase):
    def test_real_lookup_sources(self):
        for text, word, expected in [
            ("I used ChatGPT to draft a reply.", "ChatGPT", "OpenAI"),
            ("Codex reviewed the patch.", "Codex", "编程"),
            ("The medieval codex was written on vellum.", "codex", "手抄本"),
            ("We shipped an MVP to test the product.", "MVP", "最小可行产品"),
            ("She was named MVP after the game.", "MVP", "最有价值球员"),
            ("Please read the PRD before the design review.", "PRD", "产品需求文档"),
            ("Ciallo～(∠・ω< )⌒★", "Ciallo", "招呼"),
            ("The request must be idempotent.", "idempotent", "幂等"),
            ("Use a mutex to serialize these threads.", "mutex", "互斥"),
            ("The surgeon quickly diagnosed pneumothorax after the injury.", "pneumothorax", "气胸"),
            ("The authors introduce a query routing layer (QRL).\n\nThe QRL routes traffic.", "QRL", "query routing layer"),
            ("我们运行 ChatGPT 帮忙解释这篇中文文章中的句子。", "ChatGPT", "OpenAI"),
        ]:
            with self.subTest(word=word, text=text):
                result = explain(selected(text, word))[0]
                self.assertIn(expected, result[1])
                self.assertNotEqual(result[0], UNKNOWN)
        for word in ("ZQXJ", "florbalurp", "BlorpQuxV9"):
            self.assertEqual(explain(selected(f"Please inspect {word}.", word))[0][0], UNKNOWN)
        for text, word in (("我平常用ChatGPT修改作业。", "ChatGPT"), ("この論文ではChatGPTで結果を検証した。", "ChatGPT"),
                           ("这台CPU是新的。", "CPU")):
            result, _, language, _ = explain(selected(text, word))
            self.assertTrue(language.endswith("语境"))
            self.assertEqual(result[2], "")
        for word in ("mutex", "idempotent"):
            item = selected(f"Use {word} for this call.", word)
            with patch("lookup.translate", side_effect=ValueError("model missing")):
                self.assertEqual(explain(item)[0][0], DICTIONARY)
        incorrect = explain(selected("The surgeon quickly diagnosed pneumothorax after the injury.", "pneumothorax"))
        self.assertNotIn("肺炎", incorrect[0][2])

    def test_exact_entity_search_sends_only_term(self):
        def entity(qid, match, desc):
            return {"id": qid, "label": "ignored", "description": desc, "match": {"text": match},
                    "display": {"description": {"language": "en"}}}
        rows = [entity("Q10", "FooBarXYZ", "first"), entity("Q11", "FooBarXYZ Toolbox", "prefix match"),
                entity("Q12", "FOOBARXYZ", "second"), entity("not-an-id", "FooBarXYZ", "invalid"),
                entity("Q13", "FooBarXYZ", "first"), entity("Q14", "FooBarXYZ", "")]
        with patch("online_terms.urlopen", return_value=io.BytesIO(json.dumps({"search": rows}).encode())) as get:
            self.assertEqual(search_entities("FooBarXYZ"), [("Q10", "first", "en"), ("Q12", "second", "en")])
            request = get.call_args.args[0]
            address = urlsplit(request.full_url)
            self.assertEqual(address.hostname, "www.wikidata.org")
            self.assertEqual(parse_qs(address.query)["search"], ["FooBarXYZ"])
            self.assertIsNone(request.data)
            self.assertEqual(search_entities("FooBarXYZ&search=secret"), [])
            self.assertEqual(get.call_count, 1)
        with patch("app.search_entities", return_value=[]) as fetch:
            online_meanings("PostgreSQL’s")
            fetch.assert_called_once_with("PostgreSQL")

    def test_unknown_online_and_notebook(self):
        with TemporaryDirectory() as tmp, patch.object(QProcess, "start"):
            book = Notebook(Path(tmp) / "book.sqlite")
            window = Window(book)
            point = QPoint(40, 40)
            card = window.card
            item = selected("Please inspect BlorpQuxV9.", "BlorpQuxV9")
            try:
                with patch("app.search_entities", return_value=[("Q42", "新条目", "zh")]) as fetch:
                    window.lookup_text(item, point)
                    wait_for(card.online.isVisible)
                    self.assertFalse(card.save.isVisible())
                    fetch.assert_not_called()
                    card.online.click()
                    wait_for(card.save.isVisible)
                    fetch.assert_called_once_with(item.word)
                    self.assertIn("新条目", card.text.toPlainText())
                    self.assertIn("www.wikidata.org/wiki/Q42", card.text.toHtml())
                    card.save.click()
                    old = book.entries()[0]
                    self.assertIn("Q42", old["source"])
                    book.review(old["id"], True, now=1000)
                    schedule = book.entries()[0]
                    book.save(item, ("文中定义", "新读法", ""))
                    saved, = book.entries()
                    self.assertEqual((saved["id"], saved["due"], saved["streak"]),
                                     (schedule["id"], schedule["due"], schedule["streak"]))
                    self.assertEqual(saved["gloss"], "新读法")

                window.auto_online.setChecked(True)
                with patch("app.search_entities", side_effect=[OSError("offline"), []]) as fetch:
                    window.lookup_text(item, point)
                    wait_for(lambda: "无法连接" in card.text.toPlainText())
                    self.assertFalse(card.save.isVisible())
                    card.online.click()
                    wait_for(lambda: "没有找到同名" in card.text.toPlainText())
                    self.assertEqual(fetch.call_count, 2)
                    self.assertIn("在浏览器中搜索", card.text.toPlainText())
                    self.assertEqual(len(book.entries()), 1)
                started, release = Event(), Event()
                def delayed(_word):
                    started.set()
                    release.wait(5)
                    return [("Q1", "过期内容", "zh")]
                with patch("app.search_entities", side_effect=delayed):
                    window.lookup_text(item, point)
                    wait_for(started.is_set)
                    stale = window.online_job
                    card.close()
                    release.set()
                    wait_for(stale.done)
                    QApplication.processEvents()
                    self.assertFalse(card.isVisible())
                    self.assertIsNone(window.saved_result)
            finally:
                window.shutdown()
                window.deleteLater()
