import unittest
from unittest.mock import patch

from opsle_installer.terminal import find_terminal


class TerminalTests(unittest.TestCase):
    def test_prefers_system_terminal_alternative(self) -> None:
        with patch(
            "opsle_installer.terminal.shutil.which",
            side_effect=lambda name: "/usr/bin/x-terminal-emulator" if name == "x-terminal-emulator" else None,
        ):
            self.assertEqual(find_terminal(), "/usr/bin/x-terminal-emulator")

    def test_falls_back_to_konsole(self) -> None:
        with patch(
            "opsle_installer.terminal.shutil.which",
            side_effect=lambda name: "/usr/bin/konsole" if name == "konsole" else None,
        ):
            self.assertEqual(find_terminal(), "/usr/bin/konsole")

    def test_returns_none_when_no_terminal_is_available(self) -> None:
        with patch("opsle_installer.terminal.shutil.which", return_value=None):
            self.assertIsNone(find_terminal())


if __name__ == "__main__":
    unittest.main()
