import unittest

from opsle_installer.apt import package_install_command, update_command


class AptCommandTests(unittest.TestCase):
    def test_system_update_command_is_noninteractive(self) -> None:
        self.assertEqual(update_command(), ["apt-get", "-y", "upgrade"])

    def test_install_commands_pass_selected_package_names_as_arguments(self) -> None:
        self.assertEqual(
            package_install_command(["firefox-esr", "vlc"]),
            ["apt-get", "install", "-y", "--", "firefox-esr", "vlc"],
        )

    def test_upgrade_command_only_upgrades_installed_packages(self) -> None:
        self.assertEqual(
            package_install_command(["vlc"], upgrade_only=True),
            ["apt-get", "install", "-y", "--only-upgrade", "--", "vlc"],
        )


if __name__ == "__main__":
    unittest.main()
