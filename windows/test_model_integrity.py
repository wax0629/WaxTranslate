"""Pinned-package corruption and repair checks using isolated, tiny resources."""
from concurrent.futures import CancelledError
import hashlib
from io import BytesIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
import zipfile

import install_model as packs


class ModelIntegrityTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(packs, "MODEL_DIR", root / "profile"))
        self.enterContext(patch.object(packs, "BUNDLED_MODELS", root / "portable"))
        archive = BytesIO()
        self.files = {"model.bin": b"translation weights", "metadata.json": b'{"from_code":"fr"}'}
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, content in self.files.items():
                bundle.writestr("test-fr/" + name, content)
        self.archive = archive.getvalue()
        self.package = packs.ModelPackage("test-fr", hashlib.sha256(self.archive).hexdigest(), files=tuple(self.files))
        self.ocr = b"verified recognition model"
        self.enterContext(patch.dict(packs.MODELS, fr=self.package))
        self.enterContext(patch.dict(packs.OCR_MODELS, fr=("fra", len(self.ocr), hashlib.sha256(self.ocr).hexdigest())))
        self.original_downloader = packs.download_resource
        self.transfer = self.enterContext(patch.object(packs, "download_resource", side_effect=self.download))

    def download(self, url, destination, cancel):
        destination.write_bytes(self.ocr if url.endswith(".traineddata") else self.archive)

    def test_nonempty_truncated_model_is_detected_and_reinstalled(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        (model / "model.bin").write_bytes(b"x")
        self.assertFalse(packs.language_ready("fr"))
        packs.install_language("fr")
        self.assertTrue(packs.language_ready("fr"))
        for name, expected in self.files.items():
            self.assertEqual((model / name).read_bytes(), expected)

    def test_same_size_corruption_invalidates_cached_translation_and_ocr_checks(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        ocr = packs.ocr_file("fr")
        (model / "model.bin").write_bytes(b"x" * len(self.files["model.bin"]))
        ocr.write_bytes(b"x" * len(self.ocr))
        self.assertIsNone(packs.translation_dir("fr"))
        self.assertIsNone(packs.ocr_file("fr"))
        packs.install_language("fr")
        self.assertTrue(packs.language_ready("fr"))
        self.assertEqual(packs.ocr_file("fr").read_bytes(), self.ocr)

    def test_ready_package_can_be_explicitly_repaired(self):
        packs.install_language("fr")
        before = self.transfer.call_count
        packs.install_language("fr")
        self.assertEqual(self.transfer.call_count, before)
        packs.install_language("fr", repair=True)
        self.assertEqual(self.transfer.call_count, before + 2)
        self.assertTrue(packs.language_ready("fr"))

    def test_failed_or_cancelled_repair_preserves_previous_installation(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        before = {name: (model / name).read_bytes() for name in self.files}
        with patch.object(packs, "download_resource", side_effect=lambda url, dest, cancel: dest.write_bytes(b"bad")):
            with self.assertRaisesRegex(ValueError, "checksum"):
                packs.install_language("fr", repair=True)
        cancel = Event()
        cancel.set()
        with self.assertRaises(CancelledError):
            packs.install_language("fr", repair=True, cancel=cancel)
        self.assertTrue(packs.language_ready("fr"))
        self.assertEqual(before, {name: (model / name).read_bytes() for name in self.files})

    def test_repair_overrides_damaged_read_only_portable_copy(self):
        packs.install_language("fr")
        shutil.copytree(packs.MODEL_DIR, packs.BUNDLED_MODELS)
        shutil.rmtree(packs.MODEL_DIR)
        bundled = packs.BUNDLED_MODELS / self.package.name
        (bundled / "model.bin").write_bytes(b"x")
        self.assertFalse(packs.language_ready("fr"))
        packs.install_language("fr", repair=True)
        self.assertEqual(packs.translation_dir("fr"), packs.MODEL_DIR / self.package.name)
        self.assertEqual((bundled / "model.bin").read_bytes(), b"x")

    def test_legacy_nonempty_garbage_is_not_a_ready_model(self):
        package = packs.MODELS["en"]
        model = packs.MODEL_DIR / package.name
        for name in package.files:
            file = model / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"x")
        self.assertFalse(packs.complete_model(model, package))

    def test_failed_publish_restores_previous_model_directory(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        rename = Path.rename
        def fail_publish(source, target):
            if source.name == self.package.name and source.parent != packs.MODEL_DIR and target == model:
                raise OSError("simulated replacement failure")
            return rename(source, target)
        with patch.object(Path, "rename", fail_publish):
            with self.assertRaisesRegex(OSError, "replacement failure"):
                packs.install_language("fr", repair=True)
        self.assertTrue(packs.language_ready("fr"))
        self.assertEqual((model / "model.bin").read_bytes(), self.files["model.bin"])

    def test_cancel_during_transfer_preserves_existing_resources(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        cancel = Event()
        class Interrupted(BytesIO):
            def read(self, size=-1):
                data = super().read(size)
                cancel.set()
                return data
        # Use the real downloader; cancellation happens after its first read.
        with patch.object(packs, "download_resource", self.original_downloader), \
             patch("urllib.request.urlopen", return_value=Interrupted(self.ocr)):
            with self.assertRaises(CancelledError):
                packs.install_language("fr", repair=True, cancel=cancel)
        self.assertTrue(packs.language_ready("fr"))
        self.assertEqual((model / "model.bin").read_bytes(), self.files["model.bin"])

    def test_cancel_after_extraction_does_not_publish_partial_model(self):
        packs.install_language("fr")
        model = packs.translation_dir("fr")
        cancel = Event()
        write = packs.write_model_manifest
        def cancel_after_manifest(directory, package):
            write(directory, package)
            cancel.set()
        with patch.object(packs, "write_model_manifest", side_effect=cancel_after_manifest):
            with self.assertRaises(CancelledError):
                packs.install_language("fr", repair=True, cancel=cancel)
        self.assertTrue(packs.language_ready("fr"))
        self.assertEqual((model / "model.bin").read_bytes(), self.files["model.bin"])
