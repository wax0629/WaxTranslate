import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
import zipfile

from PySide6.QtWidgets import QApplication

import install_model as packs
from settings_page import SettingsPage


class LanguagePackTests(unittest.TestCase):
    def test_settings_installs_retries_and_publishes_verified_resources(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(packs, "MODEL_DIR", root / "profile"))
        self.enterContext(patch.object(packs, "BUNDLED_MODELS", root / "portable"))
        self.assertEqual(packs.DEFAULT_LANGUAGES, ("en", "ja", "ko"))
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("test-fr/model.bin", b"translation")
        package = packs.ModelPackage("test-fr", hashlib.sha256(archive.getvalue()).hexdigest(), files=("model.bin",))
        ocr = b"verified test recognition model"
        self.enterContext(patch.dict(packs.MODELS, fr=package))
        self.enterContext(patch.dict(packs.OCR_MODELS, fr=("fra", len(ocr), hashlib.sha256(ocr).hexdigest())))
        proceed = Event()
        valid = False

        def download(url, destination, cancel):
            if not proceed.wait(4):
                raise TimeoutError()
            if url.endswith(".traineddata"):
                destination.write_bytes(ocr)
            else:
                destination.write_bytes(archive.getvalue() if valid else b"damaged archive")

        transfer = self.enterContext(patch.object(packs, "download_resource", side_effect=download))
        page = SettingsPage()
        self.addCleanup(page.stop_downloads)
        page.pack_choice.setCurrentIndex(page.pack_choice.findData("fr"))
        page.download.click()
        self.assertFalse(page.download.isEnabled())
        job = page.pack_job
        page.start_pack()
        self.assertIs(page.pack_job, job)
        proceed.set()

        def finish():
            deadline = time.monotonic() + 8
            while page.pack_job is not None and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)
            self.assertIsNone(page.pack_job)

        finish()
        self.assertIn("安装失败", page.pack_status.text())
        self.assertFalse(packs.language_ready("fr"))
        self.assertIsNone(packs.translation_dir("fr"))
        self.assertTrue(page.download.isEnabled())
        valid = True
        page.download.click()
        finish()
        self.assertTrue(packs.language_ready("fr"))
        self.assertFalse(page.download.isEnabled())
        self.assertIn("已安装", page.pack_choice.currentText())
        self.assertEqual((packs.translation_dir("fr") / "model.bin").read_bytes(), b"translation")
        self.assertEqual(packs.ocr_file("fr").read_bytes(), ocr)
        self.assertEqual(transfer.call_count, 3)
        packs.install_language("fr")
        self.assertEqual(transfer.call_count, 3)
