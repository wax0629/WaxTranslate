"""Combine document, terminology, dictionary and translation evidence for a word."""
import re

from lexicon import lookup_info
from reader import Passage
from terminology import resolve_term
from translation import UnsupportedLanguage, source_language, translate, translate_lookup
from word_details import part_of_speech


UNKNOWN = "暂未收录"
DICTIONARY = "英汉词典 · ECDICT"


def reference_word(word):
    if word.lower().replace("’", "'") in {"it's", "that's", "what's", "who's", "there's", "here's",
                                            "he's", "she's", "how's", "where's", "let's"}:
        return word
    return re.sub(r"(?<=[A-Za-z0-9])['’][sS]$", "", word)


def sentence_translation(text):
    try:
        return translate(Passage(text))[1]
    except (ValueError, RuntimeError, OSError):
        return ""


def preserves_reference(word, gloss, translated):
    if word.casefold() in translated.casefold():
        return True
    # A verified reference should not sit above a sentence which silently
    # substitutes another condition, product or technical term.
    return any(sense in translated for sense in re.findall(r"[\u3400-\u9fff]{2,}", gloss))


def explain(passage):
    if not passage.selection:
        language = source_language(passage.text)
        result, excerpt = translate_lookup(passage)
        return result, excerpt, language, ""

    word = passage.word
    term = resolve_term(passage, passage.context)
    entry, common = lookup_info(word) if not term else ("", False)
    base = reference_word(word)
    if not term and not entry and base != word:
        entry, common = lookup_info(base)
    # Preserve identifiers as printed. MT attention is not a definition of
    # an abbreviation or product name, even when it yields Chinese characters.
    identifier = bool(re.search(r"[a-z][A-Z]|\d|[+#_.]", word) or len(word) > 1 and word.isupper())
    english_context = True
    try:
        language = source_language(passage.text)
    except UnsupportedLanguage as error:
        cjk_context = error.language in ("中文", "繁体中文", "日语", "韩语")
        named = term and (term[0] == "文中定义" or term[2] not in ("缩写", "名称") or word.istitle())
        if not (word.isascii() and (identifier or cjk_context or named)):
            raise
        language = error.language + "语境"
        english_context = False
    start, end = passage.selection
    has_sentence = any(c.isalnum() for c in passage.text[:start] + passage.text[end:])
    pos = term[2] if term else (part_of_speech(passage) if english_context else "")
    if term:
        origin, gloss, _ = term
        if origin == "文中定义" and gloss.isascii():
            translated = sentence_translation(gloss).rstrip("。.")
            if re.search(r"[\u3400-\u9fff]", translated):
                gloss += " · " + translated
    elif entry:
        if common and english_context and has_sentence and not identifier:
            try:
                result, excerpt = translate_lookup(passage)
            except (ValueError, RuntimeError, OSError):
                pass
            else:
                if result[0] == "句中释义" and re.search(r"[\u3400-\u9fff]", result[1]):
                    return result, excerpt, language, pos
                return (DICTIONARY, entry, result[2]), None, language, pos
        origin, gloss = DICTIONARY, entry
    else:
        origin, gloss = UNKNOWN, "本机资料和附近原文里都没有找到可靠解释。"
    sentence = sentence_translation(passage.text) if has_sentence and english_context else ""
    if sentence and not preserves_reference(word, "" if origin == UNKNOWN else gloss, sentence):
        sentence = ""
    return (origin, gloss, sentence), None, language, pos
