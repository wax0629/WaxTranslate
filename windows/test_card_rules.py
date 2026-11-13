"""Acceptance checks for query boundaries, pronunciation and saved context."""
from concurrent.futures import Future
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QProcess, QUrl
from PySide6.QtWidgets import QApplication

from app import Window, analyze
from card_policy import automatic_context, bounded_context, chinese_context
from notebook import Notebook
from lookup import CHECKING_PHRASE, DICTIONARY, UNKNOWN, explain
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
    def test_phrase_ranges_across_editor_ocr_and_card(self):
        from PySide6.QtCore import QPointF, QRectF
        from reader import Word, passage_from_lines
        from card_policy import local_reference, phrase_range_choices
        source = "The ablation study removes one model component."
        words = [Word(word, QRectF(i*110, 20, 95, 25)) for i, word in enumerate(source.split())]
        picked = passage_from_lines([words], QPointF(250, 32), "en")
        for passage in (picked, sentence_at(source, 13, 18, "en")):
            self.assertEqual((passage.word, passage.anchor), ("ablation study", (13, 18)))
            self.assertIn("消融实验", local_reference(passage)[1])
        concurrent = sentence_at("A race condition compromises memory safety.", 7, 16, "en")
        self.assertEqual((concurrent.word, local_reference(concurrent)[2]), ("race condition", "英语术语"))
        for sentence in ("A laser ablation study compared ceramic cutting angles against a physical model.",
                         "The ablation study used a model to predict the temperature of the tissue.",
                         "The patient joined a catheter ablation study using a heart model.",
                         "We built a model, but the cardiac ablation study was separate."):
            a = sentence.index("study")
            self.assertEqual(sentence_at(sentence, a, a+5, "en").word, "study")
        text = "📖 The old housing cracked, but the battery housing stayed dry."
        a = text.rindex("housing")
        hit = sentence_at(text, a, a+7, "en")
        card, requested = Card(), []
        card.term_requested.connect(requested.append)
        try:
            card.show_result(hit, "句中释义", "外壳", "电池外壳保持干燥。", QPoint(10,10))
            menu = card.range_button.menu()
            self.assertFalse(card.range_button.isHidden())
            action = next(action for action in menu.actions() if action.text().endswith("battery housing"))
            action.trigger()
            adjusted, = requested
            self.assertEqual((adjusted.word, adjusted.anchor), ("battery housing", hit.selection))
            self.assertIn(("只查指向的词", hit.selection), phrase_range_choices(adjusted))
            with patch("lookup.translate_lookup", return_value=(("句中释义", "外壳保持", "外壳保持干燥。"), None)), \
                    patch("lookup.translate", return_value=("选区译文", "电池外壳", "")):
                checked = explain(adjusted)[0]
                self.assertEqual(checked, ("短语参考", "电池外壳", "外壳保持干燥。"))
            result = explain(adjusted)[0]
            self.assertNotEqual(result[0], UNKNOWN)
            self.assertTrue(result[1] and result[1] != adjusted.word, result)
            card.show_result(adjusted, *result, QPoint(10, 10))
            with patch.object(card.listen.player, "play") as play:
                card.listen.click()
                self.assertEqual(play.call_args.args[1:], ("battery housing", False, "en"))
            with TemporaryDirectory() as temp:
                book = Notebook(Path(temp)/"notebook.sqlite3")
                book.save(adjusted, result)
                saved, = book.entries()
                self.assertEqual((saved["position"], saved["word"], saved["context"]), (adjusted.selection[0], adjusted.word, adjusted.text))
            isolated = sentence_at("The battery, housing and cap arrived.", 13, 20, "en")
            self.assertNotIn("包含左词", [label for label, span in phrase_range_choices(isolated)])
        finally:
            card.close()

    def test_conflicting_phrase_evidence_preserves_the_selected_occurrence(self):
        text = "One support team stayed behind while another support team did not return."
        head = text.rindex("team")
        hit = sentence_at(text, head, head + len("team"), "en")
        start = text.rindex("support team")
        phrase = hit.selecting(start, head + len("team"), anchor=hit.selection)
        marked = text[:start] + '"support team"' + text[head + len("team"):]
        target = "一支后勤队留守，另一支救援队没有返回。"
        def check(reference, probe, expected, calls, sentence=target):
            previews = []
            def translate_input(part):
                self.assertEqual(previews, [(CHECKING_PHRASE, "", sentence)])
                self.assertIn(part.text, ("support team", marked))
                result = reference if part.text == "support team" else probe
                if isinstance(result, Exception):
                    raise result
                return "选区译文", result, ""
            with patch("lookup.translate_lookup", return_value=(("句中释义", "救援队", sentence), None)), \
                    patch("lookup.translate", side_effect=translate_input) as translation:
                result = explain(phrase, on_phrase=lambda partial, language, kind: previews.append(partial))[0]
                self.assertEqual(result[:2], expected)
                self.assertEqual(result[2], sentence)
                self.assertEqual(translation.call_count, calls)

        correct = target.replace("救援队", "“救援队”")
        check("支持团队", correct, ("句中释义", "救援队"), 2)
        check("救援队。", "", ("句中释义", "救援队"), 1)
        for probe in (target, correct.replace("没有", "已经"), target.replace("后勤队", "“后勤队”"),
                      correct.replace("“救援队”", "“救”援队"), RuntimeError("model unavailable")):
            with self.subTest(probe=probe):
                check("支持团队", probe, ("短语参考", "支持团队"), 2)
        check("支持团队", correct, ("短语参考", "支持团队"), 1, target.replace("后勤队", "救援队"))
        check(OSError("reference failed"), correct, ("句中释义", "救援队"), 2)
        check(OSError("reference failed"), target, (UNKNOWN, "未能确认这组词的中文释义。"), 2)

        with TemporaryDirectory() as temp, patch.object(QProcess, "start"):
            window = Window(Notebook(Path(temp)/"notebook.sqlite3"))
            try:
                ticket = window.ticket
                preview = CHECKING_PHRASE, "", target
                window.show_ready_phrase(ticket, QPoint(), phrase, preview, "英语", "英语词组")
                self.assertIn(target, window.card.text.toPlainText())
                self.assertIsNone(window.saved_result)
                self.assertTrue(window.card.copy.isHidden() and window.card.save.isHidden())
                completed = Future()
                final = "句中释义", "救援队", target
                completed.set_result((phrase, final, None, "英语", "英语词组"))
                window.show_result(ticket, QPoint(), completed)
                self.assertEqual(window.saved_result, (phrase, final))
                window.card.save.click()
                saved, = window.notebook.entries()
                self.assertEqual((saved["gloss"], saved["position"]), ("救援队", phrase.selection[0]))
                window.invalidate()
                window.show_ready_phrase(ticket, QPoint(), phrase, preview, "英语", "英语词组")
                self.assertFalse(window.card.isVisible())
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_glossary_translation_replaces_only_a_confirmed_occurrence(self):
        from lookup import phrase_context_translation
        from terminology import selected_phrase
        source = "The ablation study did not remove the model component."
        part = sentence_at(source, 13, 18, "en")
        phrase = selected_phrase(part)
        text = "衰减研究对照组认为衰减研究没有移除组件。"
        start = text.rindex("衰减研究")
        aligned = Passage(text, (start, start + 4))
        with patch("lookup.translate_leg", side_effect=[aligned, Passage("衰减研究")]):
            self.assertEqual(phrase_context_translation(part, phrase), "衰减研究对照组认为消融实验没有移除组件。")
        with patch("lookup.translate_leg", side_effect=[aligned, Passage("消融研究")]):
            self.assertEqual(phrase_context_translation(part, phrase), text)
        card = Card()
        try:
            card.show_result(part, "术语参考", phrase["translation"], text, QPoint(10, 10))
            self.assertIn("术语用词待核对", card.text.toPlainText())
        finally:
            card.close()

    def test_local_phrase_displays_and_saves_while_sentence_is_pending(self):
        from threading import Event
        release = Event()
        text = "The ablation study removes one model component."
        hit = sentence_at(text, 13, 18, "en")
        def delayed(part, code):
            if not release.wait(10):
                raise TimeoutError("test did not release the worker")
            return Passage("消融实验移除了一个模型组件。", (0, 4))
        with TemporaryDirectory() as temp, patch.object(QProcess, "start"), patch("lookup.translate_leg", side_effect=delayed):
            window = Window(Notebook(Path(temp)/"notebook.sqlite3"))
            try:
                window.lookup_text(hit, QPoint(10,10))
                wait_for(lambda: window.card.headword.text() == "ablation study")
                self.assertIn("消融实验", window.card.text.toPlainText())
                self.assertTrue(window.card.rule_waiting)
                window.card.save.click()
                self.assertEqual(window.notebook.entries()[0]["word"], "ablation study")
                release.set()
                wait_for(lambda: not window.card.rule_waiting)
                self.assertIn("消融实验移除了", window.card.text.toPlainText())
                self.assertFalse(window.card.save.isEnabled())
                saved, = window.notebook.entries()
                self.assertEqual(saved["translation"], "消融实验移除了一个模型组件。")
                window.stats_pool.submit(lambda: None).result(timeout=5)
                self.assertEqual(window.notebook.activity_snapshot().total, 1)
                stale_ticket = window.ticket
                window.card.close()
                window.show_ready_phrase(stale_ticket, QPoint(), hit, ("术语参考","旧结果",""), "英语", "英语术语")
                self.assertFalse(window.card.isVisible())
                with patch("lookup.translate_leg", side_effect=ValueError("offline model unavailable")):
                    window.lookup_text(hit, QPoint(10, 10))
                    wait_for(lambda: bool(window.card.rule_error))
                    self.assertIn("消融实验", window.card.text.toPlainText())
                    self.assertFalse(window.card.rule_waiting)
            finally:
                release.set()
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_manual_context_routes_english_sentence_with_chinese_proper_name(self):
        with TemporaryDirectory() as temp, patch.object(QProcess, "start"):
            window = Window(Notebook(Path(temp) / "notebook.sqlite3"))
            try:
                for source, code, chinese in (("The API returns a label named 北京.", "en", False),
                                               ("调用 API 查询北京。", "", True),
                                               ("東京のAPIを利用します。", "ja", False),
                                               ("漢字 API 설명입니다.", "ko", False)):
                    passage = Passage(source, (source.index("API"), source.index("API") + 3), source_code=code)
                    def submit(work):
                        result = Future()
                        result.set_result(work())
                        return result
                    with self.subTest(source=source), patch.object(window.pool, "submit", side_effect=submit), \
                         patch("translation.translate", return_value=("选区译文", "译文", "")) as foreign, \
                         patch("translation.translate_leg", return_value=SimpleNamespace(text="English context")) as zh:
                        window.translate_card_context(("isolated-request", passage))
                        if chinese:
                            zh.assert_called_once()
                            self.assertEqual(zh.call_args.args[1], "zh")
                            foreign.assert_not_called()
                        else:
                            foreign.assert_called_once()
                            self.assertEqual(foreign.call_args.args[0].source_code, code)
                            zh.assert_not_called()
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()

    def test_known_foreign_terms_automatically_show_source_and_translation(self):
        for word, source, code, expected in (
            ('API', 'The API returns a response.', 'en', '应用程序编程接口'),
            ('VoiceOver', 'Enable VoiceOver in macOS accessibility settings.', 'en', '屏幕朗读'),
            ('Redis', 'Deploy Redis as the application cache.', 'en', '内存'),
            ('API', "Cette API permet aux applications de communiquer entre elles.", 'fr', '应用程序编程接口'),
        ):
            with self.subTest(word=word, source=source):
                start = source.index(word)
                passage = Passage(source, (start, start+len(word)), source_code=code)
                result, excerpt, language, pos = explain(passage)
                self.assertIn(expected, result[1])
                self.assertRegex(result[2], r'[\u3400-\u9fff]')
                card = Card()
                try:
                    card.show_result(passage, *result, QPoint(10,10), excerpt=excerpt, language=language, pos=pos)
                    text = card.text.toPlainText()
                    self.assertIn(source, text)
                    self.assertIn(result[2], text)
                    self.assertNotIn('查看相关原文', text)
                    self.assertNotIn('翻译这段原文', text)
                finally:
                    card.close()

    def test_chinese_terms_stay_manual_and_standalone_terms_do_not_translate(self):
        for word, source in (
            ('API', '这个API接口返回数据。'),
            ('VoiceOver', '在macOS辅助功能中启用VoiceOver。'),
            ('Redis', '用Redis作为应用缓存。'),
        ):
            start = source.index(word)
            passage = Passage(source, (start,start+len(word)))
            with patch('lookup.translate', side_effect=AssertionError('Chinese context must stay manual')):
                result = explain(passage)[0]
            self.assertEqual(result[2], '')
            self.assertFalse(automatic_context(passage, confirmed=True))
        standalone = Passage('API', (0,3), source_code='en')
        with patch('lookup.translate', side_effect=AssertionError('Standalone known term has no sentence')):
            self.assertEqual(explain(standalone)[0][2], '')
        for structure in ('title','path','fragment'):
            passage = Passage('The API returns data.', (4,7), source_code='en', structure=structure)
            self.assertFalse(automatic_context(passage, confirmed=True))
        item = Passage('• The API returns data.', (6,9), source_code='en', structure='list')
        self.assertTrue(automatic_context(item, confirmed=True))

    def test_automatic_term_context_keeps_excerpt_and_saved_full_translation_matched(self):
        source = 'Before sending a request, ' + 'the client checks each field and ' * 12 + 'the API returns a response.'
        start = source.index('API')
        passage = Passage(source,(start,start+3),source_code='en')
        def translated(part):
            return '选区译文', '译文：'+part.text, ''
        with patch('lookup.translate', side_effect=translated):
            result, excerpt, language, pos = explain(passage)
        compact, offset = bounded_context(passage)
        self.assertGreater(offset,0)
        self.assertEqual(excerpt[0].text, compact.text)
        self.assertEqual(excerpt[1], '译文：'+compact.text)
        self.assertEqual(result[2], '译文：'+source)
        card = Card()
        try:
            card.show_result(passage,*result,QPoint(10,10),excerpt=excerpt,language=language,pos=pos)
            self.assertEqual(card.rule_translation,excerpt[1])
            self.assertNotIn(result[2],card.text.toPlainText())
            card.open_reference(QUrl('waxcard://expand'))
            self.assertEqual(card.rule_translation,result[2])
            self.assertIn(source,card.text.toPlainText())
            card.open_reference(QUrl('waxcard://expand'))
            self.assertEqual(card.rule_translation,excerpt[1])
            with TemporaryDirectory() as temp:
                book=Notebook(Path(temp)/'notebook.sqlite3')
                book.save(passage,result)
                saved,=book.entries()
                self.assertEqual(saved['context'],source)
                self.assertEqual(saved['translation'],'译文：'+source)
        finally:
            card.close()

    def test_failed_automatic_context_retains_term_explanation_and_retries(self):
        source='Deploy Redis as the application cache.'
        start=source.index('Redis')
        passage=Passage(source,(start,start+5),source_code='en')
        with patch('lookup.translate',side_effect=ValueError('Missing model')):
            result,excerpt,language,pos=explain(passage)
        self.assertIn('内存',result[1])
        self.assertEqual(result[2],'')
        card=Card()
        requests=[]
        card.context_requested.connect(requests.append)
        try:
            card.show_result(passage,*result,QPoint(10,10),excerpt=excerpt,language=language,pos=pos)
            self.assertIn(source,card.text.toPlainText())
            self.assertIn('重试句译',card.text.toPlainText())
            self.assertTrue(card.save.isEnabled())
            card.open_reference(QUrl('waxcard://translate'))
            request,part=requests[-1]
            self.assertEqual(part.text,source)
            self.assertTrue(card.finish_context(request,'部署Redis作为应用缓存。'))
            self.assertIn('内存',card.text.toPlainText())
            self.assertIn('部署Redis作为应用缓存。',card.text.toPlainText())
        finally:
            card.close()

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
        from speech_worker import SpeechUnavailable, modern_voice_audio
        with patch("winrt.windows.media.speechsynthesis.SpeechSynthesizer", SimpleNamespace(all_voices=[])):
            with self.assertRaisesRegex(SpeechUnavailable, "添加中文声音"):
                asyncio.run(modern_voice_audio(source, False, "zh"))

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
                self.assertNotIn("type Account", passage.local_context)
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
