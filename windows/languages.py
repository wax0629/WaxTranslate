"""Source languages shared by the reader, translation models and Windows voices."""
import re
from functools import lru_cache

import pycld2


NAMES = {"en": "英语", "ja": "日语", "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语",
         "it": "意大利语", "pt": "葡萄牙语", "ru": "俄语"}
SUPPORTED = "、".join(NAMES.values())
OCR_TAGS = {"en": "en-US", "ja": "ja-JP", "ko": "ko-KR", "fr": "fr-FR", "de": "de-DE", "es": "es-ES",
            "it": "it-IT", "pt": "pt-PT", "ru": "ru-RU"}
KANA = re.compile(r"[ぁ-ゖァ-ヺｦ-ﾝ]")
HANGUL = re.compile(r"[가-힣ᄀ-ᇿㄱ-ㆎ]")
CYRILLIC = re.compile(r"[А-яЁё]")
SHORT_CYRILLIC = re.compile(r"[А-яЁё]+[.!?]?")
LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏ]")
SOURCE_SCRIPTS = {"ja": re.compile(r"[ぁ-ゖァ-ヺｦ-ﾝ一-鿿]"), "ko": HANGUL, "ru": CYRILLIC}


class UnsupportedLanguage(ValueError):
    def __init__(self, language, text):
        self.language = language
        self.text = text
        super().__init__(f"识别为{language}。支持从{SUPPORTED}译为简体中文。")


@lru_cache(maxsize=1)
def _sentence_identifier():
    from py3langid.langid import LanguageIdentifier, MODEL_FILE

    return LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)


def script_ocr_score(text, code):
    # Compare independent recognizers on the same pixels. A stray kana glyph
    # in a failed Japanese pass must not outrank a complete Korean sentence.
    count = len(SOURCE_SCRIPTS[code].findall(text))
    probability = dict(_sentence_identifier().rank(text)).get(code, 0)
    return count * (0.25 + 0.75 * probability)


def detect_source(text):
    """Return a language code, leaving ambiguous short Latin input unconfirmed."""
    try:
        reliable, _, matches = pycld2.detect(text, isPlainText=True)
    except pycld2.error:
        return ""
    name, code, percent, _ = matches[0]
    confirmed = reliable and percent >= 80 and code != "un"
    latin = LATIN.search(text)
    if not confirmed or code in ("ja", "ko"):
        if HANGUL.search(text):
            return "ko"
        if KANA.search(text):
            return "ja"
    if latin and len(re.findall(r"[^\W\d_]+", text)) < 3:
        return ""
    if confirmed and code in NAMES:
        return code if SOURCE_SCRIPTS.get(code, LATIN).search(text) else ""
    # CLD2 can confuse short Spanish sentences with Occitan. Check a second
    # offline identifier before routing a Latin sentence outside our models.
    if latin or CYRILLIC.search(text):
        candidate, confidence = _sentence_identifier().classify(text)
        if candidate in NAMES and confidence >= 0.70 and SOURCE_SCRIPTS.get(candidate, LATIN).search(text):
            return candidate
    if not confirmed:
        return ""
    others = {"nl": "荷兰语", "zh": "中文", "zh-Hant": "繁体中文", "ar": "阿拉伯语", "pl": "波兰语"}
    raise UnsupportedLanguage(others.get(code, name.title()), text)
