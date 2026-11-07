"""Offline sentence translation and conservative word alignment."""

from concurrent.futures import CancelledError
from functools import lru_cache
import re
from threading import Lock

import ctranslate2
import sentencepiece

from install_model import translation_dir
from languages import HANGUL, NAMES, SHORT_CYRILLIC, SUPPORTED, detect_source
from lexicon import lookup_entry
from reader import Passage, context_excerpt, korean_morphemes, word_spans


_engine_lock = Lock()


def engine(code):
    # lru_cache alone allows two initializations on concurrent cold requests.
    with _engine_lock:
        return _load_engine(code)


# Keep the Chinese leg and the two most recently used source models resident.
@lru_cache(maxsize=3)
def _load_engine(code):
    model = translation_dir(code)
    if model is None:
        raise ValueError(f"请在「设置 → 语言包」下载{NAMES[code]}，安装后重新翻译。")
    # SentencePiece's Windows file API cannot open some non-ASCII paths.
    tokenizer = sentencepiece.SentencePieceProcessor(model_proto=(model / "sentencepiece.model").read_bytes())
    translator = ctranslate2.Translator(str(model / "model"), device="cpu", compute_type="int8",
                                        intra_threads=4)
    return tokenizer, translator


def decoded(tokenizer, pieces):
    return tokenizer.decode(pieces).replace("▁", " ").replace("_", " ").strip()


def aligned_selection(output, selected_tokens, source_length, tokenizer, min_mass=0.40):
    target = output.hypotheses[0]
    attention = output.attention[0]
    # CT2 returns attention over the source tokens, either with or without the
    # BOS/EOS that the English-Chinese model adds. Reject unknown layouts.
    if not attention or len(attention) < len(target):
        return None
    extra = len(attention[0]) - source_length
    if extra not in (0, 2):
        return None
    indices = {i + (extra == 2) for i in selected_tokens}
    aligned = []
    for i, (piece, row) in enumerate(zip(target, attention)):
        if not piece.strip("▁") or not any(char.isalnum() for char in piece):
            continue
        peak = max(range(len(row)), key=row.__getitem__)
        if peak in indices and sum(row[k] for k in indices) >= min_mass:
            aligned.append(i)
    if not aligned or aligned[-1] - aligned[0] + 1 != len(aligned):
        return None
    gloss = decoded(tokenizer, target[aligned[0]:aligned[-1] + 1])
    full = decoded(tokenizer, target)
    prefix = decoded(tokenizer, target[:aligned[-1] + 1])
    if gloss and len(gloss) <= 24 and gloss != full and prefix.endswith(gloss) and full.startswith(prefix):
        return len(prefix) - len(gloss), len(prefix)
    return None


def strip_attached_particle(word, gloss):
    # Some int8 backends pull the preceding verb's aspect marker into a noun
    # alignment (e.g. 存入[了银行]). Trim only to an entire dictionary sense.
    if len(gloss) >= 3 and gloss.startswith(("了", "着", "过")):
        senses = re.findall(r"[\u3400-\u9fff]+", lookup_entry(word))
        if gloss not in senses and gloss[1:] in senses:
            return gloss[1:]
    return gloss


def translate_leg(passage, code):
    """Translate one model direction and carry a confident occurrence into its output."""
    tokenizer, translator = engine(code)
    source = passage.text
    tokens = tokenizer.encode(source, return_type="proto")
    pieces = [token.piece for token in tokens.pieces]
    if not pieces:
        raise ValueError("没有可翻译的原文。")
    if len(pieces) <= 200:
        batches = [pieces]
    else:
        sentences = re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*|\n+", source)
        batches = []
        for sentence in sentences:
            encoded = tokenizer.encode(sentence, out_type=str)
            batches.extend(encoded[i:i + 200] for i in range(0, len(encoded), 200))
    align = passage.selection is not None and len(pieces) <= 200
    outputs = translator.translate_batch(batches, beam_size=4, max_decoding_length=512,
                                         return_attention=align, replace_unknowns=True)
    sentence = "\n".join(decoded(tokenizer, out.hypotheses[0]) for out in outputs)
    # Some older models echo an isolated word (e.g. gatto -> "cat cat").
    if code != "en" and source.isalpha():
        words = sentence.split()
        if len(words) > 1 and len({w.casefold() for w in words}) == 1:
            return Passage(words[0])
    selection = None
    if align:
        # SentencePiece's serialized proto records UTF-8 byte offsets.
        start, end = (len(source[:pos].encode("utf-8")) for pos in passage.selection)
        selected = [i for i, part in enumerate(tokens.pieces) if part.begin < end and part.end > start]
        # The older Japanese, Korean and Italian models can spread attention
        # across unrelated words. Require a stronger link for a contextual gloss.
        selection = aligned_selection(outputs[0], selected, len(pieces), tokenizer,
                                      min_mass=0.60 if code in ("ja", "ko", "it") else 0.40)
    return Passage(sentence, selection)


QUOTED_WORD = {"ja": "彼は「{}」と言いました。", "ko": '그는 "{}"라고 말했습니다.', "ru": "Он сказал: «{}»."}


def isolated_translation(word, code):
    if code == "ko" and word.isalpha() and HANGUL.search(word):
        morphemes = korean_morphemes(word)
        if morphemes and all(m.feature.pos in ("NNG", "NNP") for m in morphemes):
            # This model translates isolated nouns like 고양이 as "Teens".
            # A copular sentence supplies the missing grammar. Only accept
            # the nominal complement when the model preserves the frame.
            framed = translate_leg(Passage(f"이것은 {word}입니다."), code)
            noun = re.fullmatch(r"This is (?:an? |the )?([^.!?]+)[.!]?", framed.text, re.I)
            if noun:
                return Passage(noun[1])
    if code == "ja" and re.fullmatch(r"[一-鿿々]+", word):
        # Bare kanji nouns can produce clipped English output. Strip the
        # nominal frame only when the first model preserves its grammar.
        framed = translate_leg(Passage(f"それは{word}です。"), code)
        noun = re.fullmatch(r"It is (?:an? |the )?([^.!?]+)[.!]?", framed.text, re.I)
        if noun:
            return Passage(noun[1])
    if code in QUOTED_WORD and word.isalpha():
        # Short formulae such as ありがとう and 감사합니다 need a sentence for
        # these models. Extract only an intact translation of the quotation.
        framed = translate_leg(Passage(QUOTED_WORD[code].format(word)), code)
        quote = re.fullmatch(r'''He said,? ["“]([^"“”]+)["”][.!]?''', framed.text, re.I)
        if quote:
            return Passage(quote[1])
    return translate_leg(Passage(word), code)


def translate(passage):
    code = passage.source_code or detect_source(passage.text)
    if not any(c.isalpha() for c in passage.text):
        raise ValueError(f"请输入{SUPPORTED}原文。")
    if not code:
        if SHORT_CYRILLIC.fullmatch(passage.text.strip()):
            code = "ru"
        elif re.search("[A-Za-zÀ-ÖØ-öø-ÿŒœẞ]", passage.text):
            code = "en"
        else:
            raise ValueError(f"无法确定原文语言。请在设置中指定{SUPPORTED}之一。")
    intermediate = passage
    bare = passage.text.rstrip(".。!")
    short_expression = code in QUOTED_WORD and len(bare) <= 16 and bare.isalpha()
    if short_expression and (code != "ja" or len(list(word_spans(bare, "ja"))) <= 3):
        intermediate = isolated_translation(bare, code)
    elif code != "en":
        intermediate = translate_leg(passage, code)
    chinese = translate_leg(intermediate, "en")
    sentence = chinese.text
    if not passage.selection:
        return "选区译文", sentence, ""
    if passage.word == passage.text:
        return "单词参考", sentence.rstrip("。.!！") or passage.word, sentence
    if chinese.selection:
        return "句中释义", strip_attached_particle(intermediate.word, chinese.word), sentence
    word = Passage(passage.word)
    if code != "en":
        word = isolated_translation(passage.word, code)
    gloss = translate_leg(word, "en").text.rstrip("。.!！")
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


def translate_text(text, stop, source_code=""):
    # OCR line breaks may only be soft wraps. Preserve explicit paragraph
    # breaks for the editable workspace without changing the OCR entry point.
    if not any(c.isalpha() for c in text):
        raise ValueError(f"请输入{SUPPORTED}原文。")
    paragraphs = re.split(r"(\n[ \t]*\n(?:[ \t]*\n)*)", text.strip())
    result = []
    for part in paragraphs:
        if stop.is_set():
            raise CancelledError()
        if any(c.isalpha() for c in part):
            result.append(translate(Passage(part, source_code=source_code))[1])
        else:
            result.append(part)
    return "".join(result)
