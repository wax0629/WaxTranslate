"""Keep the native Mac glossary data equal to the Windows glossary."""
import json
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
terms = runpy.run_path(str(root / "windows/terminology.py"))
names = {"acronyms": "ACRONYMS", "names": "NAMES", "contextNames": "CONTEXT_NAMES",
         "senses": "SENSES", "multiple": "MULTIPLE", "lowercaseCues": "_LOWERCASE_CUES"}
content = json.dumps({key: terms[value] for key, value in names.items()}, ensure_ascii=False, indent=2) + "\n"
path = root / "Assets/Lexicon/reading-terms.json"
if "--check" in sys.argv:
    if not path.is_file() or path.read_text() != content:
        sys.exit("术语数据与 Windows 不一致，请运行 python3 scripts/sync-reading-terms.py")
else:
    path.write_text(content)
