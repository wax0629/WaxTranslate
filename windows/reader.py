"""Read text in physical image pixels with the Windows OCR engine."""

import json
from pathlib import Path
import re
import subprocess
import sys
from dataclasses import dataclass, field
from math import hypot
from threading import local

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

from install_model import ocr_file
from languages import (HANGUL, KANA, LATIN, NAMES, OCR_TAGS, SHORT_CYRILLIC, SOURCE_SCRIPTS, UnsupportedLanguage,
                       detect_source, script_ocr_score)


# Keep a Latin identifier selectable in mixed text such as “看懂ChatGPT的输出”.
# Periods and underscores inside an identifier belong to it; surrounding
# punctuation and a slash separating alternatives do not.
CJK = "\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uff66-\uff9f\uac00-\ud7af"
# Pasted PDFs may represent an accent as a separate combining mark. Keep it
# with the base letter without normalizing away the original character offsets.
ALNUM = rf"(?:[^\W_{CJK}][\u0300-\u036f]*)"
WORD_TOKEN = re.compile(rf"(?i:\.net)(?:[0-9]+)?(?![A-Za-z_])|"
                        rf"[cC](?:\+\+(?:[0-9]+)?|#)|[fF]#|"
                        rf"{ALNUM}+(?:[-‐‑’'_.]{ALNUM}+)*|[{CJK}]+")
_segmenters = local()


def korean_morphemes(word):
    if not hasattr(_segmenters, "korean"):
        from mecab import MeCab
        _segmenters.korean = MeCab()
    return _segmenters.korean.parse(word)


def japanese_tokenizer():
    if not hasattr(_segmenters, "japanese"):
        from janome.tokenizer import Tokenizer
        _segmenters.japanese = Tokenizer()
    return _segmenters.japanese


def word_spans(text, source_code=""):
    japanese = source_code == "ja" or (not source_code and KANA.search(text))
    for match in WORD_TOKEN.finditer(text):
        if japanese and re.fullmatch(rf"[{CJK}]+", match.group()):
            start = match.start()
            for surface in japanese_tokenizer().tokenize(match.group(), wakati=True):
                end = start + len(surface)
                if any(c.isalpha() for c in surface):
                    yield start, end
                start = end
            continue
        if source_code in ("", "ko") and HANGUL.search(match.group()):
            # Nouns and their case particles are written together. Keep
            # conjugated verbs intact and split only tagged trailing particles.
            end = match.end()
            particles = []
            for morph in reversed(korean_morphemes(match.group())):
                if not morph.feature.pos.startswith("J") or not morph.span.start:
                    break
                start = match.start() + morph.span.start
                particles.append((start, end))
                end = start
            yield match.start(), end
            yield from reversed(particles)
            continue
        yield match.span()


@dataclass
class Word:
    text: str
    rect: QRectF


@dataclass
class Passage:
    text: str
    # Half-open character range in text. A region has no selected word.
    selection: tuple[int, int] | None = None
    # Reading evidence available at lookup time. Only the selected sentence
    # and its offset are part of a saved passage's identity.
    context: str = field(default="", compare=False, repr=False)
    context_offset: int | None = field(default=None, compare=False, repr=False)
    source_code: str = field(default="", compare=False)
    phonetic: str = field(default="", compare=False)
    ocr_line: str = field(default="", compare=False, repr=False)

    @property
    def word(self):
        return self.text[slice(*self.selection)] if self.selection else ""


def sentence_at(text, start, end):
    """Keep the sentence and the exact selected occurrence across soft line wraps."""
    left, right = 0, len(text)
    for boundary in re.finditer(r"""[。！？]+[」』”）]*\s*|[.!?]["”')]*\s+|\n[ \t]*\n""", text):
        if boundary.group().startswith(".") and re.search(
                r"\b(?:Fig|Eq|Dr|Prof|e\.g|i\.e)$", text[max(0, boundary.start() - 6):boundary.start()], re.I):
            continue
        if boundary.end() <= start:
            left = boundary.end()
        elif boundary.start() >= end:
            right = boundary.end()
            break
    source = text[left:right].rstrip()
    leading = len(source) - len(source.lstrip())
    context_start = max(0, start - 4000)
    return Passage(source[leading:].replace("\n", " "), (start - left - leading, end - left - leading),
                   text[context_start:end + 4000], start - context_start)


def context_excerpt(passage):
    """Suggest a contiguous clause containing this occurrence for a second sense check."""
    text = passage.text
    if not passage.selection or len(WORD_TOKEN.findall(text)) <= 12:
        return None
    a, b = passage.selection
    left, right = 0, len(text)
    # A comma may introduce a list item rather than a new clause. Only
    # restart after it when the following text has an explicit subject.
    pronoun = r"(?:I|we|you|he|she|it|they)\b"
    restart = rf";\s+|,\s+(?={pronoun}|(?:the|this|that|these|those)\b)|\s+(?:and|but)\s+(?={pronoun})"
    for boundary in re.finditer(restart, text, re.I):
        if boundary.end() > a:
            break
        left = boundary.end()
    # Unpunctuated timing clauses can also end the useful context. Require a
    # pronoun so that e.g. "look after the children" stays together.
    boundary = re.search(rf"[,;]\s+|\s+(?:before|after|while|whereas|and|but)\s+(?={pronoun})",
                         text[b:], re.I)
    if boundary:
        right = b + boundary.start()
    excerpt = text[left:right]
    omitted = text[:left] + " " + text[right:]
    if len(WORD_TOKEN.findall(excerpt)) < 4 or len(WORD_TOKEN.findall(omitted)) < 4:
        return None
    if any(excerpt.count(opener) != excerpt.count(closer) for opener, closer in ("()", "[]", "{}")):
        return None
    if right < len(text) and re.match(r"(?:if|unless|whether|although|even if|until)\b", excerpt, re.I):
        return None
    # A matching dictionary sense alone cannot tell whether an omitted clause
    # negates, conditions or corrects the statement.
    if re.search(r"\b(?:no|not|never|cannot|neither|nor|without|if|unless|until|whether|only|except|rather|instead)\b|n['’]t\b",
                 omitted, re.I):
        return None
    return Passage(excerpt, (a - left, b - left), source_code=passage.source_code)


def line_rect(words):
    rect = QRectF(words[0].rect)
    for word in words[1:]:
        rect = rect.united(word.rect)
    return rect


def nearest_box(point, boxes):
    """Prefer a direct hit; accept a small miss only with a clear nearest target.

    All distances use the boxes' coordinate system (OCR pixels or Qt layout
    units). Scaling the text and pointer together preserves the decision.
    """
    candidates = []
    for key, rect in boxes:
        height = rect.height()
        if height <= 0 or rect.width() <= 0:
            continue
        dx = max(rect.left() - point.x(), point.x() - rect.right(), 0)
        dy = max(rect.top() - point.y(), point.y() - rect.bottom(), 0)
        distance = hypot(dx, dy)
        if distance == 0:
            return key
        tolerance, tie_margin = 0.42 * height, 0.09 * height
        if distance <= tolerance + tie_margin:
            candidates.append((distance, tolerance, tie_margin, key))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    distance, tolerance, tie_margin, key = candidates[0]
    if distance > tolerance or (len(candidates) > 1 and candidates[1][0] - distance <= tie_margin):
        return None
    return key


def word_at_point(word, point):
    matches = list(WORD_TOKEN.finditer(word.text))
    if len(matches) <= 1:
        return matches[0] if matches else None
    # Windows supplies one ink box for e.g. "read/write", with no glyph boxes
    # or source font. Scale proportional advances into that box before hit-testing.
    font = QFont("Segoe UI")
    font.setPixelSize(64)
    metrics = QFontMetricsF(font)
    position = (point.x() - word.rect.left()) / word.rect.width() * metrics.horizontalAdvance(word.text)
    if point.x() <= word.rect.left():
        return matches[0]
    if point.x() >= word.rect.right():
        return matches[-1]
    for match in matches:
        left = metrics.horizontalAdvance(word.text[:match.start()])
        right = metrics.horizontalAdvance(word.text[:match.end()])
        if left <= position < right:
            return match
    return None


def join_ocr_words(words, code, anchor=None):
    parts = []
    length = anchor_start = 0
    for word in words:
        # Japanese OCR often gives one box per character. Keep adjacent
        # Latin words separate, e.g. a product name in Japanese prose.
        if parts and (code != "ja" or (parts[-1][-1:].isascii() and word.text[:1].isascii())):
            parts.append(" ")
            length += 1
        if word is anchor:
            anchor_start = length
        parts.append(word.text)
        length += len(word.text)
    return "".join(parts), anchor_start


def passage_from_lines(lines, point, source_code=""):
    if not lines:
        raise ValueError("未识别到文字。请重新框选清晰、可见的原文。")
    if point is None:
        return Passage("\n".join(join_ocr_words(line, source_code)[0] for line in lines))

    hit = nearest_box(point, (((i, j), word.rect) for i, line in enumerate(lines) for j, word in enumerate(line)))
    if hit is None:
        raise ValueError("光标附近没有可确定的词。请移近想查的词，或点主窗口的「框选翻译」。")
    anchor, column = hit
    hit_word = lines[anchor][column]
    match = word_at_point(hit_word, point)
    if not match:
        raise ValueError("请指向一个词。")
    rects = [line_rect(line) for line in lines]
    japanese_anchor = source_code == "ja" and any(KANA.search(w.text) for w in lines[anchor])

    def neighbors(direction):
        result = []
        current = rects[anchor]
        while True:
            choices = []
            for i, rect in enumerate(rects):
                # An adjacent Latin credit under a Japanese title is a separate
                # label even when both start at the same x and use the same size.
                if japanese_anchor and all(w.text.isascii() for w in lines[i]):
                    continue
                height = max(current.height(), rect.height())
                step = direction * (rect.center().y() - current.center().y())
                overlap = min(current.right(), rect.right()) - max(current.left(), rect.left())
                if (0.6 * height <= step <= 2.1 * height
                        and min(rect.height(), current.height()) >= 0.63 * height
                        and overlap >= 0.4 * min(current.width(), rect.width())
                        and abs(rect.left() - current.left()) <= 2.5 * height):
                    choices.append((step + 0.15 * abs(rect.left() - current.left()), i))
            if not choices:
                return result
            _, index = min(choices)
            result.append(index)
            current = rects[index]

    indices = neighbors(-1)[::-1] + [anchor] + neighbors(1)
    text, offset = join_ocr_words((word for i in indices for word in lines[i]), source_code, hit_word)
    start, end = offset + match.start(), offset + match.end()
    if source_code in ("ja", "ko") and re.fullmatch(rf"[{CJK}]+", match.group()):
        # Locate the pointed character in its OCR box, then recover the word
        # across box boundaries using the same segmentation as the editor.
        metrics = QFontMetricsF(QFont("Yu Gothic UI" if source_code == "ja" else "Malgun Gothic", 24))
        advance = metrics.horizontalAdvance(hit_word.text)
        x = (point.x() - hit_word.rect.left()) * advance / max(1, hit_word.rect.width())
        char = next((n for n in range(len(hit_word.text))
                     if metrics.horizontalAdvance(hit_word.text[:n + 1]) > x), len(hit_word.text) - 1)
        position = offset + char
        for a, b in word_spans(text, source_code):
            if a <= position < b:
                start, end = a, b
                break
        else:
            raise ValueError("请指向一个词。")
    passage = sentence_at(text, start, end)
    if len(indices) > 1:
        passage.ocr_line = join_ocr_words(lines[anchor], source_code)[0]
    return passage


async def ocr_lines(engine, image):
    image = image.convertToFormat(QImage.Format_ARGB32)
    writer = DataWriter()
    try:
        writer.write_bytes(image.constBits())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, image.width(), image.height(), BitmapAlphaMode.IGNORE)
        try:
            result = await engine.recognize_async(bitmap)
        finally:
            bitmap.close()
    finally:
        writer.close()
    lines = []
    for line in result.lines:
        words = []
        for item in line.words:
            box = item.bounding_rect
            rect = QRectF(box.x, box.y, box.width, box.height)
            if words and rect.left() - words[-1].rect.right() > 2.7 * max(rect.height(), words[-1].rect.height()):
                lines.append(words)
                words = []
            words.append(Word(item.text, rect))
        if words:
            lines.append(words)
    return lines


def read_from_pack(image, point, code):
    """Use confidence at the hit for hover, or across the selected lines for a region."""
    if image.isNull():
        raise ValueError("未识别到文字。请重新框选清晰、可见的原文。")
    model = ocr_file(code)
    if model is None:
        raise ValueError(f"请在「设置 → 语言包」下载{NAMES[code]}识字和翻译资源。")
    frame = image
    single_line = False
    ink_height = 0
    if point is not None:
        width, height = min(image.width(), 1200), min(image.height(), 96)
        left = max(0, min(image.width() - width, int(point.x()) - width // 2))
        top = max(0, min(image.height() - height, int(point.y()) - height // 2))
        frame = image.copy(left, top, width, height)
        point = point - QPointF(left, top)
    if frame.height() <= 64 or point is not None:
        gray = frame.convertToFormat(QImage.Format_Grayscale8)
        data, stride = gray.constBits(), gray.bytesPerLine()
        bands = []
        for y in range(gray.height()):
            row = data[y * stride:y * stride + gray.width()]
            if max(row) - min(row) >= 45:
                if not bands or y - bands[-1][1] > 3:
                    bands.append([y, y])
                else:
                    bands[-1][1] = y
        single_line = len(bands) == 1 and frame.height() <= 64
        if single_line:
            ink_height = bands[0][1] - bands[0][0] + 1
        if point is not None and not single_line:
            # Neighbouring titles can use different scripts. Use a clean strip
            # only when the pointer is actually inside a separated line of ink.
            for index, (top, bottom) in enumerate(bands):
                if top <= point.y() <= bottom and 3 <= bottom - top < 64:
                    above = (bands[index - 1][1] + top) // 2 + 1 if index else max(0, top - 7)
                    below = (bands[index + 1][0] + bottom) // 2 if index + 1 < len(bands) else min(frame.height(), bottom + 8)
                    frame = frame.copy(0, above, frame.width(), below - above)
                    point -= QPointF(0, above)
                    single_line = True
                    ink_height = bottom - top + 1
                    break
    if single_line and frame.width() >= 4 * frame.height():
        # A little background around a tightly selected label keeps thin edge
        # strokes from being interpreted as part of the image boundary.
        padded = QImage(frame.width() + 8, frame.height() + 8, QImage.Format_RGB32)
        padded.fill(frame.pixelColor(0, 0))
        with QPainter(padded) as painter:
            painter.drawImage(4, 4, frame)
        frame = padded
        if point is not None:
            point += QPointF(4, 4)
    # Enlarge small antialiased labels while bounding the cost of a full-screen region.
    if point is not None or (single_line and code == "en"):
        zoom = 2
    else:
        zoom = 3 if image.height() <= 64 else 1.5
    if ink_height:
        # Large screen fonts already have enough detail. Over-enlarging CJK
        # strokes can change a well-defined character into another character.
        zoom = min(zoom, max(1, 40 / ink_height))
    factor = min(zoom, 3200 / max(frame.width(), frame.height()))
    pixels = frame.scaled(max(1, round(frame.width() * factor)), max(1, round(frame.height() * factor)),
                          Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_Grayscale8)
    if point is not None:
        point = QPointF(point.x() * pixels.width() / frame.width(), point.y() * pixels.height() / frame.height())
    command = [str(Path(sys.executable).with_name("python.exe")), str(Path(__file__).with_name("ocr_worker.py")),
               model.stem, str(pixels.width()), str(pixels.height()), str(pixels.bytesPerLine()), str(int(single_line))]
    try:
        job = subprocess.run(command, cwd=model.parent, input=bytes(pixels.constBits()), capture_output=True,
                             check=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"{NAMES[code]}离线识字失败，请检查语言包后重试。") from error

    def rect(bounds):
        x, y, right, bottom = bounds
        return QRectF(x, y, right - x, bottom - y)

    lines, line_boxes, confidence = [], [], []
    recognized = json.loads(job.stdout)
    for bounds, tokens in recognized:
        words = []
        for text, box, _, blanks in tokens:
            if code in ("ja", "ko") and words and not blanks:
                # Tesseract tokenizes CJK internally. Reassemble the printed
                # unspaced run before mapping to a Japanese or Korean morpheme.
                words[-1].text += text
                words[-1].rect = words[-1].rect.united(rect(box))
            else:
                words.append(Word(text, rect(box)))
        if len(words) == 1:
            words[0].rect = rect(bounds)
        lines.append(words)
        line_boxes.append(rect(bounds))
        confidence.append(sum(token[2] for token in tokens) / len(tokens))
    if point is not None:
        hit = nearest_box(point, enumerate(line_boxes))
        if hit is None:
            raise ValueError("光标附近没有可确定的词。请指向标题文字。")
        # Sparse labels on adjacent rows can be unrelated (song and artist).
        tokens = recognized[hit][1]
        token = nearest_box(point, ((i, rect(data[1])) for i, data in enumerate(tokens)))
        confidence = [tokens[token][2] if token is not None else min(data[2] for data in tokens)]
        lines = [lines[hit]]
    passage = passage_from_lines(lines, point, code)
    passage.source_code = code
    return passage, sum(confidence) / len(confidence)


# A Hangul jamo on its own can be indistinguishable from a Latin stroke.
# Manual Korean OCR still returns the recognizer's literal text.
SCRIPT_LETTERS = {**SOURCE_SCRIPTS, "ko": re.compile(r"[가-힣]")}


def detected_language(text):
    try:
        return detect_source(text)
    except UnsupportedLanguage:
        return ""  # Preserve the original for the translation layer's unsupported-language message.


def script_reading(passage, code, hover):
    native = SCRIPT_LETTERS[code]
    text = (passage.ocr_line or passage.text) if hover else passage.text
    target = passage.word if hover else text
    count = len(native.findall(text))
    if not native.search(target) or count * 4 < sum(c.isalnum() for c in text):
        return False
    if code == "ja" and not KANA.search(text):
        return False
    try:
        detected = detect_source(text)
    except UnsupportedLanguage:
        return False
    return detected == code or (code == "ru" and not detected and SHORT_CYRILLIC.fullmatch(text.strip()))


async def recognize(image, point=None, source_code=""):
    installed = {lang.language_tag.split("-")[0].lower(): lang for lang in OcrEngine.available_recognizer_languages}

    async def read_native(code):
        language = installed.get(code) or Language(OCR_TAGS[code])
        engine = OcrEngine.try_create_from_language(language)
        if engine is None:
            raise ValueError("没有可用的系统识字引擎。")
        return await read_passage(engine, image, point)

    if source_code:
        try:
            passage = await read_native(source_code)
        except (ValueError, OSError):
            passage = read_from_pack(image, point, source_code)[0]
        passage.source_code = source_code
        return passage

    first = "en" if ocr_file("en") else next((code for code in NAMES if code in installed), "en")
    native_reads = {}

    async def system_read(code):
        if code not in native_reads:
            try:
                native_reads[code] = await read_native(code)
            except (ValueError, OSError):
                native_reads[code] = None
        return native_reads[code]

    def target(reading):
        return (reading.word if point is not None else reading.text).strip().casefold()

    initial = await system_read(first)
    if initial:
        detected = detected_language(initial.ocr_line or initial.text)
        if detected:
            refined = await system_read(detected) if detected != first and detected in installed else None
            if detected not in SCRIPT_LETTERS:
                chosen = refined or initial
                chosen.source_code = detected
                return chosen
            # Nearby writing can identify a sentence, but a second recognizer
            # must not silently replace the Latin word under the pointer.
            same_hit = refined and point is not None and target(refined) == target(initial)
            if same_hit and LATIN.search(target(initial)) and script_reading(refined, detected, False):
                refined.source_code = detected
                return refined
            if script_reading(initial, detected, point is not None):
                chosen = refined if refined and script_reading(refined, detected, point is not None) else initial
                chosen.source_code = detected
                return chosen

    # Keep the native Latin hypothesis eligible for an independent match even
    # when its offline pack is missing or fails to read this particular label.
    latin = initial if initial and LATIN.search(target(initial)) and all(
        not c.isalpha() or LATIN.fullmatch(c) for c in target(initial)) else None
    latin_confidence = 0
    punctuation = False
    if first == "en" and ocr_file("en"):
        try:
            packed, confidence = read_from_pack(image, point, "en")
        except ValueError:
            pass
        else:
            sample = target(packed)
            letters = "".join(c for c in sample if c.isalpha())
            agrees = initial and target(initial) == sample
            if not letters and confidence >= 85 and any(c.isdigit() for c in sample):
                packed.source_code = ""
                if agrees:
                    return packed
                latin, latin_confidence = packed, confidence
            punctuation = not letters and confidence >= 55
            if re.fullmatch(r"[A-Za-zÀ-ɏ]+", letters) and confidence >= 55:
                latin = packed
                latin_confidence = confidence
                latin.source_code = detected_language(packed.text)
                if agrees and detected_language(initial.text) not in SCRIPT_LETTERS:
                    latin = initial
                    latin.source_code = detected_language(initial.text)
                if (agrees and confidence >= 60) or confidence >= 95 or (len(letters) >= 3 and confidence >= 85):
                    return latin

    # Short or marginal Latin readings can also be corroborated by a model
    # trained on another script: these recognizers can read Latin titles too.
    candidates = []
    for offline in (False, True):
        if offline and candidates and latin is None:
            break
        for code, native in SCRIPT_LETTERS.items():
            if offline:
                if not ocr_file(code):
                    continue
                try:
                    candidate, confidence = read_from_pack(image, point, code)
                except ValueError:
                    continue
                if confidence < 55:
                    continue
                # A weak, isolated glyph among marks is poor evidence against
                # a punctuation-only read (e.g. three dashes read as kana).
                if punctuation and confidence < 80 and len(native.findall(target(candidate))) <= 1:
                    continue
            else:
                if code not in installed:
                    continue
                candidate = await system_read(code)
                if candidate is None:
                    continue
                if punctuation and len(native.findall(target(candidate))) <= 1:
                    continue  # Check an isolated stroke with the local pack.
            if latin and target(candidate) == target(latin):
                return latin
            if script_reading(candidate, code, point is not None):
                candidate.source_code = code
                candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return max(candidates, key=lambda p: script_ocr_score(p.text, p.source_code))
    if latin and latin_confidence >= 80:
        return latin
    if initial and any(c.isalnum() for c in target(initial)) and detected_language(initial.text) not in SCRIPT_LETTERS:
        return initial
    raise ValueError("未识别到可靠的原文。请框选清晰的文字或在设置中指定原文语言。")


async def read_passage(engine, image, point):
    code = engine.recognizer_language.language_tag.split("-")[0].lower()
    limit = OcrEngine.max_image_dimension
    frame, hit = image, point
    if max(frame.width(), frame.height()) > limit:
        frame = image.scaled(QSize(limit, limit), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if point is not None:
            hit = QPointF(point.x() * frame.width() / image.width(), point.y() * frame.height() / image.height())
    lines = await ocr_lines(engine, frame)
    try:
        return passage_from_lines(lines, hit, code)
    except ValueError:
        if point is None:
            raise
        # A delimiter or a tie between close boxes is a targeting decision.
        # Retry only when the OCR engine found no nearby ink box at all.
        for line in lines:
            for word in line:
                margin = word.rect.height() * 0.51
                if word.rect.adjusted(-margin, -margin, margin, margin).contains(hit):
                    raise
    # Windows OCR can skip a small label completely at native resolution.
    # Give it one larger view of the original pixels, bounded even on a 4K screen.
    width = min(image.width(), 1200, limit // 2)
    height = min(image.height(), 320, limit // 2)
    left = max(0, min(image.width() - width, int(point.x()) - width // 2))
    top = max(0, min(image.height() - height, int(point.y()) - height // 2))
    crop = image.copy(left, top, width, height)
    crop = crop.scaled(2 * width, 2 * height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return passage_from_lines(await ocr_lines(engine, crop), (point - QPointF(left, top)) * 2, code)
