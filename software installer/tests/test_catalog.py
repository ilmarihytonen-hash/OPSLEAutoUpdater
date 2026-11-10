import tempfile
import unittest
from pathlib import Path

from opsle_installer.catalog import load_catalog


class CatalogTests(unittest.TestCase):
    def test_loads_catalog_without_environment_fields(self) -> None:
        packages = load_catalog()

        self.assertEqual(len(packages), 7)
        self.assertEqual(packages[0].package, "firefox-esr")
        self.assertFalse(hasattr(packages[0], "environments"))

    def test_rejects_duplicate_package_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.yaml"
            path.write_text(
                """software:
  - name: First
    package: duplicate
    description: First entry.
  - name: Second
    package: duplicate
    description: Second entry.
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid or duplicate"):
                load_catalog(path)


if __name__ == "__main__":
    unittest.main()
