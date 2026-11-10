"""Combine document, terminology, dictionary and translation evidence for a word."""
import re

from card_policy import automatic_context, bounded_context, chinese_context, local_reference, needs_confirmation
from lexicon import lookup_details
from reader import Passage
from terminology import resolve_term
from languages import NAMES, SHORT_CYRILLIC, UnsupportedLanguage, detect_source
from translation import translate, translate_lookup
from word_details import part_of_speech


UNKNOWN = "暂未收录"
DICTIONARY = "英汉词典 · ECDICT"
DICTIONARY_POS = {"n": "名词", "v": "动词", "vi": "不及物动词", "vt": "及物动词",
                  "a": "形容词", "adj": "形容词", "adv": "副词", "prep": "介词",
                  "pron": "代词", "conj": "连词", "num": "数词", "abbr": "缩写", "interj": "感叹词"}


def reference_word(word):
    if word.lower().replace("’", "'") in {"it's", "that's", "what's", "who's", "there's", "here's",
                                            "he's", "she's", "how's", "where's", "let's"}:
        return word
    return re.sub(r"(?<=[A-Za-z0-9])['’][sS]$", "", word)


def sentence_translation(text):
    try:
        return translate(Passage(text, source_code="en"))[1]
    except (ValueError, RuntimeError, OSError):
        return ""


def term_context_translation(passage):
    """Return full and compact translations with the exact source of each.

    A failed language pack/model must not remove the already known explanation.
    """
    if not automatic_context(passage, confirmed=True):
        return "", None
    if not passage.source_code:
        try:
            passage.source_code = detect_source(passage.text) or "en"
        except UnsupportedLanguage:
            return "", None

    def translated(part):
        try:
            return translate(Passage(part.text, source_code=passage.source_code))[1]
        except (ValueError, RuntimeError, OSError):
            return ""
    full = translated(passage)
    part, _ = bounded_context(passage)
    excerpt = (part, translated(part)) if part.text != passage.text else None
    return full, excerpt


def preserves_reference(word, gloss, translated):
    if word.casefold() in translated.casefold():
        return True
    # A verified reference should not sit above a sentence which silently
    # substitutes another condition, product or technical term.
    return any(sense in translated for sense in re.findall(r"[\u3400-\u9fff]{2,}", gloss))


def surrounding_script(text):
    letters = len(re.findall(r"[A-Za-z]", text))
    scripts = (("日语", r"[\u3040-\u30ff]"), ("韩语", r"[\uac00-\ud7af]"), ("汉字", r"[\u3400-\u9fff]"))
    counts = [(label, len(re.findall(pattern, text))) for label, pattern in scripts]
    count = sum(size for _, size in counts)
    if count >= 2 and count > letters:
        return next(label + "语境" for label, size in counts if size)
    return ""


def explain(passage):
    if passage.selection:
        special = local_reference(passage)
        if special:
            origin, gloss, kind = special
            sentence, excerpt = term_context_translation(passage)
            return (origin, gloss, sentence), excerpt, "中文语境" if chinese_context(passage) else NAMES.get(passage.source_code, "英语"), kind
        if needs_confirmation(passage) and not resolve_term(passage, passage.local_context):
            message = "可能指 Apple 的屏幕朗读功能，当前片段不足以确认。" if passage.word == "VoiceOver" else "暂未确认这个代码名称的含义。"
            return (UNKNOWN, message, ""), None, "中文语境" if chinese_context(passage) else "", "代码名称"
    # Determine the route before consulting English terminology, POS or ECDICT.
    # Unsupported mixed-script text may still contain an English identifier.
    try:
        code = passage.source_code or detect_source(passage.text)
        if not code and passage.local_context and passage.text != passage.local_context.strip():
            code = detect_source(passage.local_context)
    except UnsupportedLanguage as error:
        if not passage.selection:
            raise
        unsupported = error
        code = ""
    else:
        unsupported = None
    language = NAMES.get(code, "")
    if not code and not unsupported and SHORT_CYRILLIC.fullmatch(passage.text.strip()):
        code = "ru"
        language = "按俄语查词" if passage.selection else "按俄语翻译"
    passage.source_code = code
    if code and code != "en":
        if passage.selection and (passage.structure in ("title", "fragment", "code", "path") or not passage.has_complete_context):
            word = Passage(passage.word, (0, len(passage.word)), source_code=code)
            origin, gloss, _ = translate(word)
            return (origin, gloss, ""), None, language, ""
        if passage.word.isascii() and passage.word:
            term = resolve_term(passage, passage.local_context)
            if term:
                origin, gloss, pos = term
                sentence, excerpt = term_context_translation(passage)
                return (origin, gloss, sentence), excerpt, language + "语境", pos
        return translate(passage), None, language, ""
    if not passage.selection:
        result, excerpt = translate_lookup(passage)
        return result, excerpt, language, ""

    word = passage.word
    term = resolve_term(passage, passage.local_context)
    entry, common, passage.phonetic, dictionary_pos = lookup_details(word) if not term else ("", False, "", "")
    base = reference_word(word)
    if not term and not entry and base != word:
        entry, common, _, dictionary_pos = lookup_details(base)
    # Preserve identifiers as printed. MT attention is not a definition of
    # an abbreviation or product name, even when it yields Chinese characters.
    identifier = bool(re.search(r"[a-z][A-Z]|\d|[+#_.]", word) or len(word) > 1 and word.isupper())
    start, end = passage.selection
    surrounding = passage.text[:start] + " " + passage.text[end:]
    english_context = not chinese_context(passage)
    if unsupported:
        cjk_context = unsupported.language in ("中文", "繁体中文", "日语", "韩语")
        named = term and (term[0] == "文中定义" or term[2] not in ("缩写", "名称") or word.istitle())
        if not (word.isascii() and (identifier or cjk_context or named)):
            raise unsupported
        language = unsupported.language + "语境"
        english_context = False
    if not language and word.isascii():
        language = surrounding_script(surrounding)
        english_context = not language
    has_sentence = any(c.isalnum() for c in surrounding)
    pos = term[2] if term else (part_of_speech(passage) if english_context else "")
    if term:
        origin, gloss, _ = term
        if origin == "文中定义" and not re.search(r"[\u3400-\u9fff]", gloss) and re.search("[A-Za-z]", gloss):
            translated = sentence_translation(gloss).rstrip("。.")
            if re.search(r"[\u3400-\u9fff]", translated):
                gloss = translated + "（机译）\n" + gloss
        sentence, excerpt = term_context_translation(passage)
        return (origin, gloss, sentence), excerpt, language, pos
    elif entry:
        if common and english_context and has_sentence and not identifier and passage.structure not in ("title", "path", "code", "fragment") and passage.has_complete_context:
            try:
                result, excerpt = translate_lookup(passage)
            except (ValueError, RuntimeError, OSError):
                pass
            else:
                if result[0] == "句中释义" and re.search(r"[\u3400-\u9fff]", result[1]):
                    return result, excerpt, language, pos
                return (DICTIONARY, entry, result[2]), None, language, pos
        origin, gloss = DICTIONARY, entry
        if not has_sentence:
            language = language or "英语"
            pos = pos or DICTIONARY_POS.get(dictionary_pos, "")
    else:
        origin, gloss = UNKNOWN, "本机资料和附近原文里都没有找到可靠解释。"
        if not english_context and not identifier and word.isascii():
            try:
                candidate = translate(Passage(word, source_code='en'))[1].rstrip('。.!！')
                if candidate and candidate.casefold() != word.casefold():
                    origin,gloss = '单词参考',candidate
            except (ValueError, RuntimeError, OSError):
                pass
    sentence = sentence_translation(passage.text) if has_sentence and english_context and passage.structure not in ("title", "path", "code", "fragment") and passage.has_complete_context else ""
    if sentence and not preserves_reference(word, "" if origin == UNKNOWN else gloss, sentence):
        sentence = ""
    return (origin, gloss, sentence), None, language, pos
