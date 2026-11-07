"""Recognize in-memory pixels using a downloaded Tesseract language model."""
import json
import sys


def recognize(lang, width, height, stride, single_line):
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
                lines[-1][1].append((entry.GetUTF8Text(RIL.WORD), entry.BoundingBox(RIL.WORD),
                                     entry.Confidence(RIL.WORD), entry.BlanksBeforeWord()))
        return lines


if __name__ == "__main__":
    print(json.dumps(recognize(sys.argv[1], *map(int, sys.argv[2:]))))
