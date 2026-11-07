import ctypes
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, Qt, Signal
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QPushButton, QSystemTrayIcon
import app
import instance
from notebook import Notebook


class LaunchModeTests(unittest.TestCase):
    def test_real_event_distinguishes_manual_and_quiet_activation(self):
        class Owner(QObject):
            aboutToQuit = Signal()

        owner = Owner()
        name = r"Local\WaxTranslate.Test." + uuid4().hex
        with patch.object(instance, "EVENT_NAME", name):
            notifier = instance.activation_event(owner, activate_existing=False)
            self.assertIsNotNone(notifier)
            self.addCleanup(lambda: owner.aboutToQuit.emit())
            activated = QSignalSpy(notifier.activated)
            self.assertIsNone(instance.activation_event(owner, activate_existing=False))
            QTest.qWait(100)
            self.assertEqual(activated.count(), 0)
            self.assertIsNone(instance.activation_event(owner))
            self.assertTrue(activated.count() or activated.wait(3000))

    def test_cold_start_visibility(self):
        for quiet, tray, show in ((True, True, False), (False, True, False), (True, False, True), (False, False, True)):
            with (self.subTest(quiet=quiet, tray=tray),
                  patch.object(sys, "argv", ["app.py"] + (["--background"] if quiet else [])),
                  patch.object(app, "QApplication") as application,
                  patch.object(app, "Window") as window, patch.object(app, "apply_theme"),
                  patch.object(app, "app_icon"), patch.object(instance, "activation_event") as activate,
                  patch.object(ctypes.windll.shell32, "SetCurrentProcessExplicitAppUserModelID")):
                window.return_value.tray.isVisible.return_value = tray
                app.main()
                activate.assert_called_once_with(application.return_value, activate_existing=not quiet)
                self.assertEqual(window.return_value.show.call_count, int(show))
                application.return_value.exec.assert_called_once_with()

    def test_tray_minimize_and_shell_fallback(self):
        with TemporaryDirectory() as folder, patch.object(QProcess, "start"), \
                patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True) as available:
            window = app.Window(Notebook(Path(folder) / "book.sqlite"))
            try:
                window.open_home()
                self.assertEqual(window.windowType(), Qt.Tool)
                window.maximize_button.click()
                self.assertTrue(window.isMaximized())
                self.assertEqual(window.maximize_button.accessibleName(), "还原")
                window.maximize_button.click()
                self.assertFalse(window.isMaximized())
                close = window.sidebar.findChild(QPushButton, "closeWindow")
                close.click()
                self.assertFalse(window.isVisible())
                window.open_home()
                window.preferences.close_behavior.setCurrentIndex(window.preferences.close_behavior.findData("quit"))
                next(b for b in window.sidebar.findChildren(QPushButton) if b.accessibleName() == "最小化").click()
                QApplication.processEvents()
                self.assertFalse(window.isVisible(), "Minimize must allow reading to continue, even with quit-on-close")
                window.tray_clicked(QSystemTrayIcon.DoubleClick)
                self.assertTrue(window.isVisible())
                self.assertFalse(window.isMinimized())
                available.return_value = False
                window.showMinimized()
                QApplication.processEvents()
                self.assertEqual(window.windowType(), Qt.Window)
                self.assertTrue(window.isVisible(), "Without the tray, keep a taskbar entry")
                self.assertTrue(window.isMinimized())
                window.open_home()
                self.assertFalse(window.isMinimized())
                available.return_value = True
                window.open_home()
                self.assertEqual(window.windowType(), Qt.Tool)
            finally:
                window.shutdown()
                window.hide()
                window.deleteLater()
