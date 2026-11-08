"""Exercise settings through the same navigation, controls and close path as the desktop."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QProcess, QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QPushButton, QSystemTrayIcon

from app import Window
from notebook import Notebook


class SettingsTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.book = Notebook(Path(folder) / "words.sqlite")
        self.enterContext(patch.object(QProcess, "start"))
        self.login = Mock()
        self.login.status.return_value = "off"

    def window(self):
        window = Window(self.book, self.login)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.hide)
        self.addCleanup(window.shutdown)
        return window

    def test_navigation_and_old_preferences(self):
        old = QSettings(str(self.book.path.with_name("preferences.ini")), QSettings.IniFormat)
        old.setValue("gesture", "right")
        old.setValue("onlineTerms", True)
        old.sync()
        window = self.window()
        window.resize(610, 490)
        window.show()
        QApplication.processEvents()
        page = window.preferences
        nav = next(button for button in window.sidebar.findChildren(QPushButton) if button.accessibleName() == "设置")
        nav.click()
        self.assertIs(window.tabs.currentWidget(), page)
        self.assertTrue(nav.isChecked())
        self.assertEqual(page.trigger.currentData(), "right")
        self.assertTrue(page.auto_online.isChecked())
        self.assertEqual(page.close_behavior.currentData(), "tray")
        self.assertEqual(window.workspace.source_code, "")
        self.login.set_enabled.assert_not_called()

        page.close_behavior.setCurrentIndex(page.close_behavior.findData("quit"))
        page.source_language.setCurrentIndex(page.source_language.findData("de"))
        self.assertEqual(window.workspace.source_label.text(), "德语")
        page.trigger.setCurrentIndex(page.trigger.findData("off"))
        page.auto_online.click()
        window.tabs.setCurrentWidget(window.home)
        self.assertIn("双击单词", window.home.instructions.accessibleName())
        window.home.instructions.click()
        self.assertIs(window.tabs.currentWidget(), page)
        self.assertIs(window.focusWidget(), page.trigger)
        window.tabs.setCurrentWidget(window.library)
        tray_action = next(action for action in window.tray.contextMenu().actions() if action.text() == "设置")
        tray_action.trigger()
        self.assertIs(window.tabs.currentWidget(), page)

        reopened = self.window()
        self.assertEqual(reopened.preferences.close_behavior.currentData(), "quit")
        self.assertEqual(reopened.workspace.source_code, "de")
        self.assertEqual(reopened.trigger.currentData(), "off")
        self.assertFalse(reopened.auto_online.isChecked())
        self.login.set_enabled.assert_not_called()

    def test_login_error_repair_and_external_change(self):
        window = self.window()
        page = window.preferences
        window.tabs.setCurrentWidget(page)
        self.assertFalse(page.startup.isChecked())
        self.login.set_enabled.side_effect = PermissionError("denied")
        page.startup.click()
        self.assertFalse(page.startup.isChecked())
        self.login.set_enabled.assert_called_once_with(True)
        self.login.set_enabled.side_effect = None
        self.login.status.return_value = "moved"
        window.refresh_startup()
        self.assertFalse(page.repair_startup.isHidden())
        self.login.status.return_value = "on"
        page.repair_startup.click()
        self.assertTrue(page.startup.isChecked())
        self.assertTrue(page.repair_startup.isHidden())
        self.login.status.return_value = "blocked"
        window.tabs.setCurrentIndex(0)
        window.tabs.setCurrentWidget(page)
        self.assertFalse(page.startup.isChecked())
        self.assertFalse(page.startup.isEnabled())
        self.assertFalse(page.system_startup.isHidden())
        with patch("app.QDesktopServices.openUrl", return_value=True) as open_url:
            page.system_startup.click()
            self.assertEqual(open_url.call_args.args[0].toString(), "ms-settings:startupapps")
        self.login.status.return_value = "off"
        page.remove_startup.click()
        self.login.set_enabled.assert_called_with(False)
        self.assertTrue(page.startup.isEnabled())
        self.login.status.side_effect = PermissionError("denied")
        window.refresh_startup()
        self.assertFalse(page.retry_startup.isHidden())
        self.login.status.side_effect = None
        page.retry_startup.click()
        self.assertTrue(page.retry_startup.isHidden())

    def test_close_to_tray_or_quit(self):
        window = self.window()
        window.show()
        with patch.object(QApplication, "quit") as quit_app, patch.object(QSystemTrayIcon, "isVisible", return_value=True):
            with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
                closing = QCloseEvent()
                window.closeEvent(closing)
                self.assertFalse(closing.isAccepted())
                self.assertFalse(window.isVisible())
                quit_app.assert_not_called()
                window.preferences.close_behavior.setCurrentIndex(window.preferences.close_behavior.findData("quit"))
                window.closeEvent(QCloseEvent())
                quit_app.assert_called_once()
            with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
                window.preferences.close_behavior.setCurrentIndex(window.preferences.close_behavior.findData("tray"))
                window.closeEvent(QCloseEvent())
                self.assertEqual(quit_app.call_count, 2)
