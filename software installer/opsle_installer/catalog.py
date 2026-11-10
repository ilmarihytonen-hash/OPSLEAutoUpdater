import re
from dataclasses import dataclass
from pathlib import Path

import yaml


PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
CATALOG_PATH = Path(__file__).with_name("data") / "installable_software.yaml"


@dataclass(frozen=True)
class SoftwarePackage:
    name: str
    package: str
    description: str


def load_catalog(path: Path = CATALOG_PATH) -> list[SoftwarePackage]:
    try:
        with path.open(encoding="utf-8") as catalog_file:
            data = yaml.safe_load(catalog_file)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not read the software catalog: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("software"), list):
        raise ValueError("The catalog must contain a 'software' list.")

    packages: list[SoftwarePackage] = []
    seen_names: set[str] = set()
    for entry in data["software"]:
        if not isinstance(entry, dict):
            raise ValueError("Each software catalog entry must be a mapping.")

        name = entry.get("package")
        title = entry.get("name")
        description = entry.get("description")
        if (
            not isinstance(name, str)
            or not PACKAGE_NAME.fullmatch(name)
            or name in seen_names
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(description, str)
        ):
            raise ValueError(f"Invalid or duplicate software catalog entry: {entry!r}")

        seen_names.add(name)
        packages.append(
            SoftwarePackage(name=title.strip(), package=name, description=description)
        )

    if not packages:
        raise ValueError("The software catalog is empty.")
    return packages
