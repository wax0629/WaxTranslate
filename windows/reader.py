"""Read text in physical image pixels with the Windows OCR engine."""

import re
from dataclasses import dataclass, field
from math import hypot

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

from languages import NAMES, OCR_TAGS, UnsupportedLanguage, detect_source


# Keep a Latin identifier selectable in mixed text such as “看懂ChatGPT的输出”.
# Periods and underscores inside an identifier belong to it; surrounding
# punctuation and a slash separating alternatives do not.
CJK = "\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af"
# Pasted PDFs may represent an accent as a separate combining mark. Keep it
# with the base letter without normalizing away the original character offsets.
ALNUM = rf"(?:[^\W_{CJK}][\u0300-\u036f]*)"
WORD_TOKEN = re.compile(rf"(?i:\.net)(?:[0-9]+)?(?![A-Za-z_])|"
                        rf"[cC](?:\+\+(?:[0-9]+)?|#)|[fF]#|"
                        rf"{ALNUM}+(?:[-‐‑’'_.]{ALNUM}+)*|[{CJK}]+")


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

    @property
    def word(self):
        return self.text[slice(*self.selection)] if self.selection else ""


def sentence_at(text, start, end):
    """Keep the sentence and the exact selected occurrence across soft line wraps."""
    left, right = 0, len(text)
    for boundary in re.finditer(r"""[.!?]["”')]*\s+|\n[ \t]*\n""", text):
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


def passage_from_lines(lines, point):
    if not lines:
        raise ValueError("未识别到文字。请重新框选清晰、可见的原文。")
    if point is None:
        return Passage("\n".join(" ".join(w.text for w in line) for line in lines))

    hit = nearest_box(point, (((i, j), word.rect) for i, line in enumerate(lines) for j, word in enumerate(line)))
    if hit is None:
        raise ValueError("光标附近没有可确定的词。请移近想查的词，或点主窗口的「开始框选」。")
    anchor, column = hit
    match = word_at_point(lines[anchor][column], point)
    if not match:
        raise ValueError("请指向一个词。")
    rects = [line_rect(line) for line in lines]

    def neighbors(direction):
        result = []
        current = rects[anchor]
        while True:
            choices = []
            for i, rect in enumerate(rects):
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
    pieces = []
    offset = 0
    for i in indices:
        for j, word in enumerate(lines[i]):
            if (i, j) == hit:
                start = offset + match.start()
                end = offset + match.end()
            pieces.append(word.text)
            offset += len(word.text) + 1
    return sentence_at(" ".join(pieces), start, end)


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


async def recognize(image, point=None, source_code=""):
    code = source_code or "en"
    engine = OcrEngine.try_create_from_language(Language(OCR_TAGS[code]))
    if engine is None and not source_code:
        # All supported sources use Latin script. Start with any installed
        # supported recognizer when English is unavailable.
        for language in OcrEngine.available_recognizer_languages:
            if language.language_tag.split("-")[0].lower() in NAMES:
                engine = OcrEngine.try_create_from_language(language)
                if engine is not None:
                    break
    if engine is None:
        raise ValueError(f"请在 Windows 设置 → 时间和语言 → 语言和区域中，为{NAMES[code]}安装文字识别，或在阅读页粘贴原文。")
    passage = await read_passage(engine, image, point)
    passage.source_code = source_code
    if not source_code:
        try:
            detected = detect_source(passage.text)
        except UnsupportedLanguage:
            return passage
        if detected and detected != engine.recognizer_language.language_tag.split("-")[0].lower():
            matched = OcrEngine.try_create_from_language(Language(OCR_TAGS[detected]))
            if matched is not None:
                try:
                    passage = await read_passage(matched, image, point)
                except ValueError:
                    pass  # The first pass already found the requested occurrence.
            passage.source_code = detected
    return passage


async def read_passage(engine, image, point):
    limit = OcrEngine.max_image_dimension
    frame, hit = image, point
    if max(frame.width(), frame.height()) > limit:
        frame = image.scaled(QSize(limit, limit), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if point is not None:
            hit = QPointF(point.x() * frame.width() / image.width(), point.y() * frame.height() / image.height())
    lines = await ocr_lines(engine, frame)
    try:
        return passage_from_lines(lines, hit)
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
    return passage_from_lines(await ocr_lines(engine, crop), (point - QPointF(left, top)) * 2)
