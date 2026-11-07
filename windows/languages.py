"""Source languages shared by the reader, translation models and Windows voices."""
import re
from functools import lru_cache

import pycld2


NAMES = {"en": "英语", "fr": "法语", "de": "德语", "es": "西班牙语"}
SUPPORTED = "、".join(NAMES.values())
OCR_TAGS = {"en": "en-US", "fr": "fr-FR", "de": "de-DE", "es": "es-ES"}


class UnsupportedLanguage(ValueError):
    def __init__(self, language, text):
        self.language = language
        self.text = text
        super().__init__(f"识别为{language}。支持从{SUPPORTED}译为简体中文。")


@lru_cache(maxsize=1)
def _sentence_identifier():
    from py3langid.langid import LanguageIdentifier, MODEL_FILE

    return LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)


def detect_source(text):
    """Return a language code, leaving ambiguous short Latin input unconfirmed."""
    try:
        reliable, _, matches = pycld2.detect(text, isPlainText=True)
    except pycld2.error:
        return ""
    name, code, percent, _ = matches[0]
    latin = re.search(r"[A-Za-zÀ-ɏ]", text)
    if latin and len(re.findall(r"[^\W\d_]+", text)) < 3:
        return ""
    confirmed = reliable and percent >= 80 and code != "un"
    if confirmed and code in NAMES:
        return code
    # CLD2 can confuse short Spanish sentences with Occitan. Check a second
    # offline identifier before routing a Latin sentence outside our models.
    if latin:
        candidate, confidence = _sentence_identifier().classify(text)
        if candidate in NAMES and confidence >= 0.70:
            return candidate
    if not confirmed:
        return ""
    others = {"it": "意大利语", "pt": "葡萄牙语", "nl": "荷兰语", "ru": "俄语", "ja": "日语",
              "ko": "韩语", "zh": "中文", "zh-Hant": "繁体中文", "ar": "阿拉伯语", "pl": "波兰语"}
    raise UnsupportedLanguage(others.get(code, name.title()), text)
