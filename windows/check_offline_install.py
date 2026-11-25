"""Exercise the two reading directions using only the installed Qt app and its models."""
import os
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import QApplication
from install_model import BUNDLED_MODELS, translation_dir
from workspace import TextWorkspace


def main():
    root = Path(sys.executable).resolve().parents[1]
    assert BUNDLED_MODELS == root / "models"
    assert not (Path(os.environ["LOCALAPPDATA"]) / "WaxTranslate" / "models").exists()
    evidence = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = TextWorkspace(pool)
        reader.resize(900, 500)
        reader.show()
        app.processEvents()
        if evidence:
            assert reader.grab().save(str(evidence / "before.png"))
        for code, source, expected in (("en", "Thank you.", "谢"), ("zh", "谢谢你。", "thank")):
            assert translation_dir(code).is_relative_to(BUNDLED_MODELS)
            reader.set_source_language("")
            reader.input.setPlainText(source)
            reader.translate_text()
            deadline = time.monotonic() + 45
            while reader.pending is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            assert reader.pending is None, "Translation timed out"
            target = reader.output.toPlainText()
            assert expected in target.casefold(), (source, target)
            print(source, "=>", target, flush=True)
            if evidence:
                assert reader.grab().save(str(evidence / (code + ".png")))
        reader.close()


if __name__ == "__main__":
    main()
