"""Recognize in-memory pixels using a downloaded Tesseract language model."""
import json
import sys


def recognize(lang, width, height, stride, single_line, hover):
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

    # A relative data path works even when the portable app or user profile
    # has characters outside the Windows ANSI code page. The caller sets cwd.
    mode = PSM.SINGLE_LINE if single_line else PSM.SPARSE_TEXT
    with PyTessBaseAPI(path=".", lang=lang, psm=mode) as api:
        api.SetImageBytes(sys.stdin.buffer.read(), width, height, 1, stride)
        api.Recognize()
        iterator = api.GetIterator()
        lines = []
        if iterator:
            for entry in iterate_level(iterator, RIL.WORD):
                if entry.Empty(RIL.WORD):
                    continue
                if not lines or entry.IsAtBeginningOf(RIL.TEXTLINE):
                    lines.append((entry.BoundingBox(RIL.TEXTLINE), []))
                symbols = []
                lines[-1][1].append((entry.GetUTF8Text(RIL.WORD), entry.BoundingBox(RIL.WORD),
                                     entry.Confidence(RIL.WORD), entry.BlanksBeforeWord(), symbols))
                if hover:
                    while not entry.Empty(RIL.SYMBOL):
                        left, _, right, _ = entry.BoundingBox(RIL.SYMBOL)
                        symbols.append((entry.GetUTF8Text(RIL.SYMBOL), left, right))
                        if entry.IsAtFinalElement(RIL.WORD, RIL.SYMBOL) or not entry.Next(RIL.SYMBOL):
                            break
        return lines


if __name__ == "__main__":
    print(json.dumps(recognize(sys.argv[1], *map(int, sys.argv[2:]))))
