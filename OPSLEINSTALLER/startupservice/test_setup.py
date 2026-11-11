"""Safety and headless UI tests for the first-start setup wizard."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from setup_core import (
    SOFTWARE_CATALOG_PATH,
    SystemSetupBackend,
    build_command_plan,
    load_setup_info,
    load_software_catalog,
    mark_setup_complete,
    save_setup_info,
    validate_setup_data,
)


VALID_DATA = {
    "locale": "en_US.UTF-8",
    "keyboard": "us",
    "timezone": "Europe/London",
    "full_name": "Test User",
    "username": "testuser",
    "password": "test-password-123",
    "desktop": "xfce",
    "theme": "dark",
    "software": ["firefox"],
    "eula_accepted": True,
}


class SetupCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_software_catalog(SOFTWARE_CATALOG_PATH)

    def test_catalog_has_recommendations_and_package_names(self):
        self.assertTrue(any(app["recommended"] for app in self.catalog))
        self.assertTrue(all(app["packages"] for app in self.catalog))

    def test_command_plan_applies_locale_and_keyboard_before_install_hook(self):
        commands = build_command_plan(VALID_DATA, self.catalog)
        locale_command = ["localectl", "set-locale", "LANG=en_US.UTF-8"]
        keyboard_command = ["localectl", "set-keymap", "us"]
        sources_command = [
            "/bin/sh",
            str(Path(__file__).with_name("configure-apt-sources.sh")),
        ]
        custom_command = ["/bin/sh", str(Path(__file__).with_name("custom-install.sh"))]

        self.assertEqual(commands[0], sources_command)
        self.assertLess(commands.index(locale_command), commands.index(keyboard_command))
        self.assertLess(commands.index(keyboard_command), commands.index(custom_command))
        self.assertLess(
            commands.index(sources_command),
            commands.index(["apt-get", "update"]),
        )
        self.assertTrue(Path(sources_command[1]).is_file())
        self.assertTrue(Path(custom_command[1]).is_file())

    def test_rejects_shell_metacharacters_in_username(self):
        data = dict(VALID_DATA, username="user;touch")
        with self.assertRaisesRegex(ValueError, "Username"):
            validate_setup_data(data, self.catalog)

    def test_requires_explicit_eula_acceptance(self):
        data = dict(VALID_DATA, eula_accepted=False)
        with self.assertRaisesRegex(ValueError, "EULA"):
            validate_setup_data(data, self.catalog)

    def test_simulation_never_calls_the_system_command_runner(self):
        def must_not_run(*args, **kwargs):
            self.fail(f"Preview mode attempted to run {args!r} with {kwargs!r}.")

        backend = SystemSetupBackend(simulate=True, command_runner=must_not_run)
        backend.apply(VALID_DATA, self.catalog)
        self.assertTrue(backend.simulated_steps)
        self.assertTrue(
            any("no system changes" in step for step in backend.simulated_steps)
        )

    def test_debug_mode_writes_redacted_command_plan_without_running_commands(self):
        def must_not_run(*args, **kwargs):
            self.fail(f"Debug mode attempted to run {args!r} with {kwargs!r}.")

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "setup-debug.log"
            backend = SystemSetupBackend(
                command_runner=must_not_run,
                debug=True,
                debug_log_path=report_path,
            )
            self.assertTrue(backend.simulate)
            console = StringIO()
            with redirect_stdout(console):
                backend.apply(VALID_DATA, self.catalog)

            report = report_path.read_text(encoding="utf-8")
            console_output = console.getvalue()
            self.assertEqual(
                backend.debug_commands, build_command_plan(VALID_DATA, self.catalog)
            )
            self.assertIn('["apt-get", "install"', report)
            self.assertIn('Would run: ["apt-get", "install"', console_output)
            self.assertIn("chpasswd", report)
            self.assertIn("password supplied via stdin; redacted", report)
            self.assertIn("Would write: ~/.config/gtk-3.0/settings.ini", report)
            self.assertIn("gtk-theme-name=Adwaita-dark", console_output)
            self.assertNotIn(VALID_DATA["password"], report)
            self.assertNotIn(VALID_DATA["password"], console_output)
            self.assertIn("No system commands were executed.", report)

    def test_setup_info_saves_all_setup_fields_except_password(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "setup-info.json"
            save_setup_info(VALID_DATA, destination)
            saved = json.loads(destination.read_text(encoding="utf-8"))

        self.assertNotIn("password", saved)
        self.assertEqual(saved["username"], VALID_DATA["username"])
        self.assertEqual(saved["software"], VALID_DATA["software"])
        self.assertEqual(saved["eula_accepted"], VALID_DATA["eula_accepted"])
        self.assertIn("saved_at", saved)
        self.assertFalse(saved["already_done"])

    def test_setup_info_excludes_password_and_confirmation_fields(self):
        setup_data = dict(
            VALID_DATA,
            language="en",
            password_confirm="another-secret",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "setup-info.json"
            save_setup_info(setup_data, destination)
            saved = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(saved["language"], "en")
        self.assertFalse(saved["already_done"])
        self.assertNotIn("password", saved)
        self.assertNotIn("password_confirm", saved)

    def test_completion_marker_is_written_for_one_time_service_condition(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "setup-complete"
            self.assertEqual(mark_setup_complete(marker), marker)
            self.assertEqual(marker.read_text(encoding="utf-8"), "completed\n")

    def test_systemd_units_are_separate_and_startup_waits_for_updater(self):
        service_dir = (
            Path(__file__).resolve().parent.parent
            / "software installer"
            / "linux"
        )
        startup_unit = (service_dir / "startupservice.service").read_text(
            encoding="utf-8"
        )
        updater_unit = (service_dir / "opsle-system-update.service").read_text(
            encoding="utf-8"
        )

        self.assertIn("After=display-manager.service", startup_unit)
        self.assertNotIn("Requires=opsle-system-update.service", startup_unit)
        self.assertIn(
            "ConditionPathExists=!/var/lib/startupservice/setup-complete",
            startup_unit,
        )
        self.assertIn("Before=display-manager.service", updater_unit)
        updater_installer = (
            service_dir / "install_system_updater.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--defer-until-first-setup", updater_installer)
        self.assertIn(
            "ConditionPathExists=/var/lib/startupservice/setup-complete",
            updater_installer,
        )


class SetupWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.setup_info_path = Path(self.temporary_directory.name) / "setup-info.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_preview_wizard_runs_to_completion(self):
        from setup_ui import SetupWizard

        wizard = SetupWizard(
            test_mode=True,
            catalog=load_software_catalog(),
            setup_info_path=self.setup_info_path,
        )
        self.assertTrue(self.setup_info_path.is_file())
        initial = json.loads(self.setup_info_path.read_text(encoding="utf-8"))
        self.assertEqual(initial["setup_status"], "wizard_started")
        self.assertNotIn("password", initial)
        self.assertEqual(wizard.pages.count(), 11)
        wizard.fields["full_name"].setText(VALID_DATA["full_name"])
        wizard.fields["username"].setText(VALID_DATA["username"])
        wizard.fields["password"].setText(VALID_DATA["password"])
        wizard.fields["password_confirm"].setText(VALID_DATA["password"])
        wizard.fields["software"]["firefox"].setChecked(True)
        in_progress = json.loads(self.setup_info_path.read_text(encoding="utf-8"))
        self.assertEqual(in_progress["full_name"], VALID_DATA["full_name"])
        self.assertEqual(in_progress["username"], VALID_DATA["username"])
        self.assertNotIn(VALID_DATA["password"], self.setup_info_path.read_text(encoding="utf-8"))

        self.assertEqual(wizard.step_progress.value(), 1)
        self.assertTrue(wizard.back_button.isHidden())
        self.assertFalse(wizard.next_button.isHidden())
        self.assertFalse(wizard.step_indicator.isHidden())
        self.assertEqual(wizard.sidebar_steps[0][1].text(), "1")
        self.assertEqual(wizard.next_button.text(), wizard._t("next"))
        wizard.next_button.click()
        self.assertEqual(wizard.pages.currentIndex(), 1)
        self.assertEqual(wizard.step_progress.value(), 2)
        self.assertFalse(wizard.back_button.isHidden())
        wizard.back_button.click()
        self.assertEqual(wizard.pages.currentIndex(), 0)
        self.assertEqual(wizard.step_progress.value(), 1)

        for expected_page in range(1, wizard.REVIEW_PAGE + 1):
            wizard.next_button.click()
            self.assertEqual(wizard.pages.currentIndex(), expected_page)
            self.assertEqual(wizard.step_progress.value(), expected_page + 1)
        self.assertIn("10", wizard.step_indicator.text())
        wizard.eula_checkbox.setChecked(True)

        wizard._start_install()
        from PyQt6.QtCore import QElapsedTimer

        timer = QElapsedTimer()
        timer.start()
        while not wizard.setup_finished and timer.elapsed() < 5000:
            self.application.processEvents()
        self.application.processEvents()
        self.assertEqual(wizard.pages.currentIndex(), wizard.COMPLETE_PAGE)
        self.assertTrue(wizard.test_mode)
        self.assertEqual(wizard.progress.value(), 100)
        completed = json.loads(self.setup_info_path.read_text(encoding="utf-8"))
        self.assertEqual(completed["setup_status"], "completed")
        self.assertEqual(completed["install_progress"], 100)
        self.assertFalse(completed["already_done"])
        self.assertNotIn("password", completed)
        wizard.close()

    def test_language_list_uses_installed_translations_and_sets_locale(self):
        from setup_ui import SetupWizard, load_translations

        translations = load_translations()
        expected_languages = {
            "da",
            "de",
            "en",
            "es",
            "fi",
            "fr",
            "it",
            "ja",
            "nl",
            "pl",
            "pt",
            "ru",
            "sv",
            "uk",
            "zh_CN",
        }
        self.assertEqual(set(translations), expected_languages)
        english_keys = set(translations["en"])
        self.assertTrue(
            all(set(translation) == english_keys for translation in translations.values())
        )

        wizard = SetupWizard(
            test_mode=True,
            catalog=load_software_catalog(),
            setup_info_path=self.setup_info_path,
        )
        language_list = wizard.fields["language"]
        self.assertEqual(language_list.count(), len(wizard.translations))
        self.assertEqual(language_list.currentData(), "en")
        self.assertEqual(wizard._setup_data()["locale"], "en_US.UTF-8")

        language_list.setCurrentIndex(language_list.findData("da"))
        self.assertEqual(wizard.heading.text(), wizard.translations["da"]["heading"])
        self.assertEqual(wizard._setup_data()["locale"], "da_DK.UTF-8")
        saved = json.loads(self.setup_info_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["language"], "da")
        self.assertEqual(saved["locale"], "da_DK.UTF-8")
        wizard.close()

    def test_eula_file_is_displayed_and_requires_acceptance(self):
        from setup_ui import EULA_PATH, SetupWizard

        eula_contents = EULA_PATH.read_text(encoding="utf-8").strip()
        self.assertTrue(eula_contents)
        wizard = SetupWizard(
            catalog=load_software_catalog(),
            setup_info_path=self.setup_info_path,
        )
        self.assertEqual(wizard.eula_text.toPlainText(), eula_contents)
        self.assertTrue(wizard.eula_available)
        self.assertFalse(wizard.start_button.isEnabled())
        wizard.eula_checkbox.setChecked(True)
        self.assertTrue(wizard.start_button.isEnabled())
        wizard.hide()

    def test_debug_kill_switch_closes_wizard(self):
        from setup_ui import SetupWizard

        wizard = SetupWizard(
            debug_mode=True,
            setup_info_path=self.setup_info_path,
        )
        self.assertIsNotNone(wizard.kill_switch_shortcut)
        self.assertTrue(
            wizard.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        self.assertTrue(
            wizard.windowFlags() & Qt.WindowType.FramelessWindowHint
        )
        wizard.show()
        self.application.processEvents()
        QTest.keyClick(
            wizard,
            Qt.Key.Key_Q,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.application.processEvents()
        self.assertFalse(wizard.isVisible())

    def test_non_debug_wizard_has_no_kill_switch_and_rejects_close(self):
        from setup_ui import SetupWizard

        wizard = SetupWizard(
            setup_info_path=self.setup_info_path,
        )
        self.assertIsNone(wizard.kill_switch_shortcut)
        self.assertFalse(wizard.close())
        self.assertFalse(wizard.isVisible())
        wizard.hide()

    def test_enter_advances_the_current_wizard_step(self):
        from setup_ui import SetupWizard

        wizard = SetupWizard(
            test_mode=True,
            setup_info_path=self.setup_info_path,
        )
        wizard.show()
        self.application.processEvents()
        wizard.fields["language"].setFocus()
        QTest.keyClick(wizard.fields["language"], Qt.Key.Key_Return)
        self.application.processEvents()

        self.assertEqual(wizard.pages.currentIndex(), wizard.KEYBOARD_PAGE)
        wizard.pages.setCurrentIndex(wizard.ACCOUNT_PAGE)
        wizard.fields["full_name"].setText(VALID_DATA["full_name"])
        wizard.fields["username"].setText(VALID_DATA["username"])
        wizard.fields["username"].setFocus()
        QTest.keyClick(wizard.fields["username"], Qt.Key.Key_Return)
        self.application.processEvents()
        self.assertEqual(wizard.pages.currentIndex(), wizard.PASSWORD_PAGE)
        wizard.close()

    def test_network_dialog_requires_connection_before_continue(self):
        from setup_ui import NetworkDialog, NetworkWorker

        with patch.object(
            NetworkWorker,
            "run",
            lambda worker: worker.completed.emit(False, "No internet connection."),
        ):
            dialog = NetworkDialog()
            dialog.worker.wait(1000)
            self.application.processEvents()
            self.assertFalse(dialog.continue_button.isEnabled())
            self.assertIn("No internet connection", dialog.status.text())
            dialog.close()

        with patch.object(
            NetworkWorker,
            "run",
            lambda worker: worker.completed.emit(True, "Internet connection is available."),
        ):
            dialog = NetworkDialog()
            dialog.worker.wait(1000)
            self.application.processEvents()
            self.assertTrue(dialog.continue_button.isEnabled())
            dialog.close()

    def test_completed_summary_blocks_restarting_the_wizard(self):
        from setup_ui import SetupWizard

        save_setup_info(VALID_DATA, self.setup_info_path, already_done=True)
        self.assertTrue(load_setup_info(self.setup_info_path)["already_done"])
        with self.assertRaisesRegex(RuntimeError, "already marked complete"):
            SetupWizard(
                test_mode=True,
                setup_info_path=self.setup_info_path,
            )

    def test_debug_wizard_saves_summary_and_finishes_without_reboot(self):
        from PyQt6.QtCore import QElapsedTimer
        from setup_ui import SetupWizard

        with tempfile.TemporaryDirectory() as directory:
            info_path = Path(directory) / "setup-info.json"
            debug_path = Path(directory) / "setup-debug.log"
            wizard = SetupWizard(
                debug_mode=True,
                setup_info_path=info_path,
                debug_log_path=debug_path,
            )
            wizard.fields["full_name"].setText(VALID_DATA["full_name"])
            wizard.fields["username"].setText(VALID_DATA["username"])
            wizard.fields["password"].setText(VALID_DATA["password"])
            wizard.fields["password_confirm"].setText(VALID_DATA["password"])
            wizard.pages.setCurrentIndex(wizard.REVIEW_PAGE)
            wizard.eula_checkbox.setChecked(True)

            console = StringIO()
            with redirect_stdout(console):
                wizard._start_install()
                timer = QElapsedTimer()
                timer.start()
                while not wizard.setup_finished and timer.elapsed() < 5000:
                    self.application.processEvents()
                self.application.processEvents()

            self.assertEqual(wizard.pages.currentIndex(), wizard.COMPLETE_PAGE)
            self.assertTrue(wizard.reboot_button.isHidden())
            self.assertTrue(info_path.is_file())
            self.assertTrue(debug_path.is_file())
            saved = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["setup_status"], "completed")
            self.assertNotIn("password", saved)
            self.assertNotIn(
                VALID_DATA["password"],
                debug_path.read_text(encoding="utf-8"),
            )
            self.assertIn("No reboot was performed", console.getvalue())
            wizard.close()


if __name__ == "__main__":
    unittest.main()
