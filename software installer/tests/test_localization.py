import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opsle_installer.localization import get_system_language, translate


class LocalizationTests(unittest.TestCase):
    def test_reads_system_language_from_environment(self) -> None:
        self.assertEqual(
            get_system_language({"LANG": "fr_CA.UTF-8"}, locale_files=()),
            "fr",
        )

    def test_uses_locale_file_when_environment_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            locale_file = Path(temporary_directory) / "locale"
            locale_file.write_text('LANG="sv_SE.UTF-8"\n', encoding="utf-8")

            self.assertEqual(
                get_system_language({}, locale_files=(locale_file,)),
                "sv",
            )

    def test_uses_first_language_from_language_priority_list(self) -> None:
        self.assertEqual(
            get_system_language({"LANGUAGE": "uk:en", "LANG": "en_US.UTF-8"}, ()),
            "uk",
        )

    def test_ignores_c_locale_and_uses_platform_default(self) -> None:
        with patch("opsle_installer.localization.locale.getlocale", return_value=(None, None)):
            system_language = get_system_language({}, locale_files=())
            self.assertEqual(
                get_system_language({"LANG": "C.UTF-8"}, locale_files=()),
                system_language,
            )

    def test_translates_warning_and_preserves_unknown_messages(self) -> None:
        self.assertEqual(
            translate("Do not power off your computer.", "ja"),
            "コンピューターの電源を切らないでください。",
        )
        self.assertEqual(translate("Unknown message", "fr"), "Unknown message")


if __name__ == "__main__":
    unittest.main()
