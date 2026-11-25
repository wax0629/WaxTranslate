"""Check the installed dylib and both real model files on the runner's native CPU."""
import ctypes as c
from pathlib import Path
import sys

contents = Path(sys.argv[1]) / "Contents"
engine = c.CDLL(str(contents / "Frameworks/libWaxTranslation.dylib")).wax_translate
engine.argtypes = [c.c_char_p, c.c_char_p, c.c_int, c.c_int, c.POINTER(c.c_int), c.POINTER(c.c_int)]
engine.restype = c.c_void_p
free = c.CDLL(None).free
free.argtypes = [c.c_void_p]

for pair, source, expected, word in (
    ("en-zh", "Thank you.", "谢", ""),
    ("zh-en", "谢谢你。", "thank", ""),
    ("en-zh", "I sat on the river bank.", "岸", "bank"),
):
    model = contents / "Resources/OfflineModels" / pair
    lo, hi = c.c_int(-1), c.c_int(-1)
    offset = source.index(word) if word else -1
    ptr = engine(bytes(model), source.encode(), offset, offset + len(word), c.byref(lo), c.byref(hi))
    assert ptr, f"{pair} failed to translate"
    try:
        data = c.string_at(ptr)
        text = data.decode()
        assert expected in text.lower(), text
        if word:
            assert 0 <= lo.value < hi.value <= len(data)
            assert expected in data[lo.value:hi.value].decode()
        print(pair, source, "→", text.replace("▁", " ").strip())
    finally:
        free(ptr)
