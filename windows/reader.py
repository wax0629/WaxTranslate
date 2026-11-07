"""Read English text in physical image pixels with the Windows OCR engine."""

import re
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter


WORD_TOKEN = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*")


@dataclass
class Word:
    text: str
    rect: QRectF


@dataclass
class Passage:
    text: str
    # Half-open character range in text. A region has no selected word.
    selection: tuple[int, int] | None = None

    @property
    def word(self):
        return self.text[slice(*self.selection)] if self.selection else ""


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
    return Passage(excerpt, (a - left, b - left))


def line_rect(words):
    rect = QRectF(words[0].rect)
    for word in words[1:]:
        rect = rect.united(word.rect)
    return rect


def word_at_point(word, point):
    if "/" not in word.text:
        return WORD_TOKEN.search(word.text)
    # Windows supplies one ink box for e.g. "read/write", with no glyph boxes
    # or source font. Scale proportional advances into that box before hit-testing.
    font = QFont("Segoe UI")
    font.setPixelSize(64)
    metrics = QFontMetricsF(font)
    position = (point.x() - word.rect.left()) / word.rect.width() * metrics.horizontalAdvance(word.text)
    for match in WORD_TOKEN.finditer(word.text):
        left = metrics.horizontalAdvance(word.text[:match.start()])
        right = metrics.horizontalAdvance(word.text[:match.end()])
        if left <= position < right:
            return match
    return None


def passage_from_lines(lines, point):
    if not lines:
        raise ValueError("未识别到英文。请重新框选清晰、可见的文字。")
    if point is None:
        return Passage("\n".join(" ".join(w.text for w in line) for line in lines))

    hit = next(((i, j) for i, line in enumerate(lines) for j, word in enumerate(line)
                if word.rect.contains(point)), None)
    if hit is None:
        raise ValueError("光标下没有识别到词。请指向字母，或按住左 Ctrl 并用鼠标左键拖动框选。")
    anchor, column = hit
    match = word_at_point(lines[anchor][column], point)
    if not match:
        raise ValueError("请指向一个英文词。")
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
    paragraph = " ".join(pieces)
    boundaries = [m.end() for m in re.finditer(r'[.!?]["”\')]*\s+', paragraph)]
    left = max((pos for pos in boundaries if pos <= start), default=0)
    right = next((pos for pos in boundaries if pos >= end), len(paragraph))
    return Passage(paragraph[left:right].rstrip(), (start - left, end - left))


async def recognize(image, point=None):
    engine = OcrEngine.try_create_from_language(Language("en-US"))
    if engine is None:
        raise ValueError("请在 Windows 设置 → 时间和语言 → 语言和区域中，为英语安装「基本输入」和文字识别。")
    limit = OcrEngine.max_image_dimension
    if max(image.width(), image.height()) > limit:
        old = image.size()
        image = image.scaled(QSize(limit, limit), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if point is not None:
            point = QPointF(point.x() * image.width() / old.width(),
                            point.y() * image.height() / old.height())
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
    return passage_from_lines(lines, point)
