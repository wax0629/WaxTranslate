"""A repaired language pack must be used by the next translation request."""
from pathlib import Path
import os
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class TranslationResourceTests(unittest.TestCase):
    def test_verified_legacy_packages_remain_usable_without_manifest(self):
        import install_model as packs
        available = [(code, packs.translation_dir(code)) for code in ("en", "es")]
        available = [(code, source) for code, source in available if source is not None]
        self.assertTrue(available, "Requires an installed English or Spanish package")
        root = Path(self.enterContext(TemporaryDirectory()))
        for code, source in available:
            with self.subTest(code=code):
                package = packs.MODELS[code]
                legacy = root / package.name
                for name in package.files:
                    dest = legacy / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.link(source / name, dest)
                    except OSError:
                        shutil.copy2(source / name, dest)
                self.assertFalse((legacy / packs.MODEL_MANIFEST).exists())
                self.assertTrue(packs.complete_model(legacy, package))
                # Never write a shared link: detach this temporary file first.
                binary = legacy / "model/model.bin"
                binary.unlink()
                binary.write_bytes(b"x")
                self.assertFalse(packs.complete_model(legacy, package))
                self.assertTrue(packs.complete_model(source, package))

    def test_repaired_files_reload_resident_engine_and_invalid_files_are_rejected(self):
        import translation
        root = Path(self.enterContext(TemporaryDirectory()))
        (root / "model").mkdir()
        (root / "model/model.bin").write_bytes(b"old weights")
        (root / "sentencepiece.model").write_bytes(b"tokenizer")
        package = SimpleNamespace(files=("model/model.bin", "sentencepiece.model"))
        self.enterContext(patch.dict(translation.MODELS, en=package))
        location = self.enterContext(patch.object(translation, "translation_dir", return_value=root))
        tokenizer = self.enterContext(patch.object(translation.sentencepiece, "SentencePieceProcessor", side_effect=[object(), object()]))
        models = self.enterContext(patch.object(translation.ctranslate2, "Translator", side_effect=[object(), object()]))
        translation._load_engine.cache_clear()
        self.addCleanup(translation._load_engine.cache_clear)
        first = translation.engine("en")
        self.assertIs(translation.engine("en"), first)
        (root / "model/model.bin").write_bytes(b"new weights")
        second = translation.engine("en")
        self.assertIsNot(first, second)
        self.assertIs(translation.engine("en"), second)
        self.assertEqual(tokenizer.call_count, 2)
        self.assertEqual(models.call_count, 2)
        location.return_value = None
        with self.assertRaisesRegex(ValueError, "修复"):
            translation.engine("en")
        self.assertEqual(models.call_count, 2)
