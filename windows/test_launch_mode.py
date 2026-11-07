import ctypes
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy, QTest
import app
import instance


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
        for quiet, tray, show in ((True, True, False), (True, False, True), (False, True, True)):
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
