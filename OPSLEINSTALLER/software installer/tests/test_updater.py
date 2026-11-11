import io
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import call, patch

from opsle_installer.policy import UpdatePolicy
from opsle_installer.updater import (
    parse_apt_progress,
    plymouth_is_active,
    run_apt_step,
    run_updates,
    splash_progress,
)


def make_config(**overrides: object) -> object:
    values = {
        "enabled": True,
        "run_before_login": True,
        "policy_url": "https://policy.example/updates",
        "managed_packages": ("opsle-installer",),
        "update_all_packages": True,
    }
    values.update(overrides)
    return type("Config", (), values)()


class UpdaterTests(unittest.TestCase):
    def test_runs_mandatory_updates_then_reboots(self) -> None:
        policy = UpdatePolicy(
            mandatory_after=date.today() - timedelta(days=1),
            required_packages=("opsle-agent",),
        )
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch("opsle_installer.updater.subprocess.run") as run,
            patch("opsle_installer.updater.run_apt_step") as apt_step,
            patch("opsle_installer.updater.fetch_update_policy", return_value=policy),
            patch(
                "opsle_installer.updater.installed_packages",
                return_value={"opsle-installer", "bash"},
            ),
            patch("opsle_installer.updater.splash_progress"),
        ):
            state_path = Path(temporary_directory) / "state" / "last-completed-date"
            result = run_updates(make_config(), state_path)
            self.assertEqual(
                state_path.read_text(encoding="ascii").strip(),
                policy.mandatory_after.isoformat(),
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            apt_step.call_args_list,
            [
                call(["apt-get", "update"], 0, 15, "Checking software sources..."),
                call(
                    [
                        "apt-get",
                        "install",
                        "-y",
                        "--",
                        "opsle-agent",
                        "opsle-installer",
                    ],
                    15,
                    57,
                    "Installing mandatory software updates...",
                ),
                call(["apt-get", "-y", "upgrade"], 57, 100, "Installing system updates..."),
            ],
        )
        run.assert_called_once_with(["systemctl", "reboot"], check=True)

    def test_before_deadline_only_checks_sources_and_allows_login(self) -> None:
        policy = UpdatePolicy(
            mandatory_after=date.today() + timedelta(days=1),
            required_packages=("opsle-agent",),
        )
        with (
            patch("opsle_installer.updater.subprocess.run") as run,
            patch("opsle_installer.updater.run_apt_step") as apt_step,
            patch("opsle_installer.updater.fetch_update_policy", return_value=policy),
            patch("opsle_installer.updater.splash_progress"),
        ):
            self.assertEqual(run_updates(make_config()), 0)
        apt_step.assert_called_once_with(
            ["apt-get", "update"], 0, 15, "Checking software sources..."
        )
        run.assert_not_called()

    def test_missing_policy_does_not_force_updates_or_reboot(self) -> None:
        with (
            patch("opsle_installer.updater.subprocess.run") as run,
            patch("opsle_installer.updater.run_apt_step") as apt_step,
            patch("opsle_installer.updater.fetch_update_policy", return_value=None),
            patch("opsle_installer.updater.splash_progress"),
        ):
            self.assertEqual(run_updates(make_config()), 0)
        apt_step.assert_called_once()
        run.assert_not_called()

    def test_update_failure_does_not_reboot(self) -> None:
        policy = UpdatePolicy(
            mandatory_after=date.today() - timedelta(days=1),
            required_packages=(),
        )
        with (
            patch("opsle_installer.updater.subprocess.run") as run,
            patch(
                "opsle_installer.updater.run_apt_step",
                side_effect=subprocess.CalledProcessError(1, ["apt-get"]),
            ),
            patch("opsle_installer.updater.fetch_update_policy", return_value=policy),
            patch("opsle_installer.updater.splash_progress"),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            run_updates(make_config(managed_packages=()))
        run.assert_not_called()

    def test_completed_deadline_does_not_repeat_updates_or_reboot(self) -> None:
        policy = UpdatePolicy(
            mandatory_after=date.today() - timedelta(days=1),
            required_packages=("opsle-agent",),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "last-completed-date"
            state_path.write_text(policy.mandatory_after.isoformat(), encoding="ascii")
            with (
                patch("opsle_installer.updater.subprocess.run") as run,
                patch("opsle_installer.updater.run_apt_step") as apt_step,
                patch("opsle_installer.updater.fetch_update_policy", return_value=policy),
                patch("opsle_installer.updater.splash_progress"),
            ):
                self.assertEqual(run_updates(make_config(), state_path), 0)
            apt_step.assert_called_once_with(
                ["apt-get", "update"], 0, 15, "Checking software sources..."
            )
            run.assert_not_called()

    def test_disabled_pre_login_updater_skips_everything(self) -> None:
        with (
            patch("opsle_installer.updater.subprocess.run") as run,
            patch("opsle_installer.updater.run_apt_step") as apt_step,
        ):
            self.assertEqual(run_updates(make_config(enabled=False)), 0)
        run.assert_not_called()
        apt_step.assert_not_called()

    def test_parses_apt_download_and_package_progress(self) -> None:
        self.assertEqual(parse_apt_progress("pmstatus:libc6:42:Unpacking"), 42)
        self.assertEqual(parse_apt_progress("dlstatus:https://mirror/pkg:75"), 75)
        self.assertIsNone(parse_apt_progress("status:libc6:Installed"))

    def test_splash_status_includes_localized_power_warning(self) -> None:
        with (
            patch("opsle_installer.localization.get_system_language", return_value="fr"),
            patch("opsle_installer.updater.plymouth_is_active", return_value=True),
            patch("opsle_installer.updater.subprocess.run") as run,
        ):
            splash_progress(25, "Installing system updates...")

        command = run.call_args.args[0]
        self.assertIn(
            "--status=N’éteignez pas votre ordinateur. Installation des mises à jour du système...",
            command,
        )

    def test_splash_is_skipped_when_plymouth_is_not_active(self) -> None:
        with (
            patch("opsle_installer.updater.plymouth_is_active", return_value=False),
            patch("opsle_installer.updater.subprocess.run") as run,
        ):
            splash_progress(25, "Installing system updates...")
        run.assert_not_called()

    def test_detects_plymouth_runtime_state(self) -> None:
        completed = subprocess.CompletedProcess(args=["plymouth", "--ping"], returncode=0)
        with (
            patch("opsle_installer.updater.shutil.which", return_value="/usr/bin/plymouth"),
            patch("opsle_installer.updater.subprocess.run", return_value=completed) as run,
        ):
            self.assertTrue(plymouth_is_active())
        run.assert_called_once()

    def test_reports_plymouth_inactive_when_executable_is_missing(self) -> None:
        with patch("opsle_installer.updater.shutil.which", return_value=None):
            self.assertFalse(plymouth_is_active())

    def test_apt_progress_is_monotonic_and_options_precede_package_separator(self) -> None:
        process = type("Process", (), {"stdout": io.StringIO(
            "pmstatus:pkg:50:Installing\npmstatus:pkg:25:Configuring\n"
        )})()
        process.wait = lambda: 0
        progress = []
        with (
            patch("opsle_installer.updater.subprocess.Popen", return_value=process) as popen,
            patch(
                "opsle_installer.updater.splash_progress",
                side_effect=lambda percent, message: progress.append(percent),
            ),
        ):
            run_apt_step(
                ["apt-get", "install", "-y", "--", "pkg"],
                20,
                80,
                "Installing updates...",
            )

        command = popen.call_args.args[0]
        self.assertEqual(
            command[:5],
            ["apt-get", "-o", "Dpkg::Progress-Fd=1", "-o", "APT::Status-Fd=1"],
        )
        self.assertEqual(command[-3:], ["-y", "--", "pkg"])
        self.assertEqual(progress, [20, 50, 50])


if __name__ == "__main__":
    unittest.main()
