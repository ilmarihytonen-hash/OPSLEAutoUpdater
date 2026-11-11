import tempfile
import unittest
from pathlib import Path

from opsle_installer.config import configured_display_manager, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_default_updater_config(self) -> None:
        config = load_config()

        self.assertTrue(config.enabled)
        self.assertTrue(config.run_before_login)
        self.assertTrue(config.update_all_packages)
        self.assertTrue(config.block_login_on_failure)
        self.assertEqual(config.policy_url, "")

    def test_rejects_non_https_policy_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                """updater:
  enabled: true
  run_before_login: true
  display_manager: auto
  update_all_packages: true
  block_login_on_failure: true
  policy_url: http://example.invalid/policy
  managed_packages: []
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid updater settings"):
                load_config(path)

    def test_auto_detects_lightdm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manager_file = Path(temporary_directory) / "default-display-manager"
            manager_file.write_text("/usr/sbin/lightdm\n", encoding="utf-8")

            self.assertEqual(
                configured_display_manager(default_manager_file=manager_file),
                "lightdm.service",
            )


if __name__ == "__main__":
    unittest.main()
