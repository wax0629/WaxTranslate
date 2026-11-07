"""Offline sentence translation and conservative word alignment."""

from concurrent.futures import CancelledError
from functools import lru_cache
from pathlib import Path
import re

import ctranslate2
import pycld2
import sentencepiece

from install_model import MODEL, PACKAGE
from reader import Passage, context_excerpt


class UnsupportedLanguage(ValueError):
    def __init__(self, language, text):
        self.language = language
        self.text = text
        super().__init__(f"识别为{language}。当前离线模型支持英语译为简体中文。")


def source_language(text):
    """Return a supported, detected source or leave short/ambiguous input unconfirmed."""
    try:
        reliable, _, matches = pycld2.detect(text, isPlainText=True)
    except pycld2.error:
        return ""
    name, code, percent, _ = matches[0]
    if not reliable or percent < 80 or code == "un":
        return ""
    # Isolated Latin words (e.g. "description") can be shared by languages.
    if re.search(r"[A-Za-zÀ-ɏ]", text) and len(re.findall(r"[^\W\d_]+", text)) < 3:
        return ""
    if code == "en":
        return "英语"
    languages = {"fr": "法语", "de": "德语", "es": "西班牙语", "it": "意大利语", "pt": "葡萄牙语",
                 "nl": "荷兰语", "ru": "俄语", "ja": "日语", "ko": "韩语", "zh": "中文",
                 "zh-Hant": "繁体中文", "ar": "阿拉伯语", "pl": "波兰语"}
    raise UnsupportedLanguage(languages.get(code, name.title()), text)


@lru_cache(maxsize=1)
def engine():
    bundled = Path(__file__).resolve().parent.parent / "models" / PACKAGE
    model = bundled if bundled.is_dir() else MODEL
    if not (model / "model/model.bin").is_file():
        raise ValueError("缺少英译中模型。请运行 windows\\setup.cmd 安装后重试。")
    # SentencePiece's Windows file API cannot open some non-ASCII paths.
    tokenizer = sentencepiece.SentencePieceProcessor(model_proto=(model / "sentencepiece.model").read_bytes())
    translator = ctranslate2.Translator(str(model / "model"), device="cpu", compute_type="int8",
                                        intra_threads=4)
    return tokenizer, translator


def decoded(tokenizer, pieces):
    return tokenizer.decode(pieces).replace("▁", " ").replace("_", " ").strip()


def aligned_gloss(output, selected_tokens, source_length, tokenizer):
    target = output.hypotheses[0]
    attention = output.attention[0]
    # CT2 returns attention over the source tokens, either with or without the
    # language prefix and EOS added by this model. Reject unknown layouts.
    if not attention or len(attention) < len(target):
        return ""
    extra = len(attention[0]) - source_length
    if extra not in (0, 2):
        return ""
    indices = {i + (extra == 2) for i in selected_tokens}
    aligned = []
    for i, (piece, row) in enumerate(zip(target, attention)):
        if not piece.strip("▁") or not any(char.isalnum() for char in piece):
            continue
        peak = max(range(len(row)), key=row.__getitem__)
        if peak in indices and sum(row[k] for k in indices) >= 0.40:
            aligned.append(i)
    if not aligned or aligned[-1] - aligned[0] + 1 != len(aligned):
        return ""
    gloss = decoded(tokenizer, target[aligned[0]:aligned[-1] + 1])
    full = decoded(tokenizer, target)
    return gloss if gloss and len(gloss) <= 24 and gloss != full else ""


def translate(passage):
    tokenizer, translator = engine()
    source = passage.text
    if not re.search("[A-Za-z]", source):
        raise ValueError("当前 Windows 开发版支持英文译为简体中文。请选取英文。")
    tokens = tokenizer.encode(source, return_type="proto")
    pieces = [token.piece for token in tokens.pieces]
    if not pieces:
        raise ValueError("没有可翻译的英文。")
    if len(pieces) <= 200:
        batches = [pieces]
    else:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", source)
        batches = []
        for sentence in sentences:
            encoded = tokenizer.encode(sentence, out_type=str)
            batches.extend(encoded[i:i + 200] for i in range(0, len(encoded), 200))
    align = passage.selection is not None and len(pieces) <= 200
    outputs = translator.translate_batch(batches, beam_size=4, max_decoding_length=512,
                                         return_attention=align, replace_unknowns=True)
    sentence = "\n".join(decoded(tokenizer, out.hypotheses[0]) for out in outputs)
    if not passage.selection:
        return "选区译文", sentence, ""
    if align:
        # SentencePiece's serialized proto records UTF-8 byte offsets.
        start, end = (len(source[:pos].encode("utf-8")) for pos in passage.selection)
        selected = [i for i, part in enumerate(tokens.pieces) if part.begin < end and part.end > start]
        gloss = aligned_gloss(outputs[0], selected, len(pieces), tokenizer)
        if gloss:
            return "句中释义", gloss, sentence
    single = translator.translate_batch([tokenizer.encode(passage.word, out_type=str)], beam_size=4)[0]
    gloss = decoded(tokenizer, single.hypotheses[0])
    gloss = gloss.rstrip("。.!！")
    return "单词参考", gloss or passage.word, sentence


def translate_lookup(passage):
    result = translate(passage)
    excerpt = context_excerpt(passage)
    if excerpt is not None:
        try:
            origin, gloss, sentence = translate(excerpt)
        except (RuntimeError, ValueError):
            return result, None
        # Accept the shorter reading only when the model can align the same
        # word sense to this occurrence using the excerpt alone.
        if origin == "句中释义" and gloss == result[1] and sentence:
            return result, (excerpt, sentence)
    return result, None


def translate_text(text, stop):
    # OCR line breaks may only be soft wraps. Preserve explicit paragraph
    # breaks for the editable workspace without changing the OCR entry point.
    if not re.search("[A-Za-z]", text):
        raise ValueError("请输入英文原文。当前支持英文译为简体中文。")
    paragraphs = re.split(r"(\n[ \t]*\n(?:[ \t]*\n)*)", text.strip())
    result = []
    for part in paragraphs:
        if stop.is_set():
            raise CancelledError()
        if re.search("[A-Za-z]", part):
            source_language(part)
            result.append(translate(Passage(part))[1])
        else:
            result.append(part)
    return "".join(result)
