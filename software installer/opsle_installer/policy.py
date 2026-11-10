import json
from dataclasses import dataclass
from datetime import date
import urllib.error
import urllib.request

from opsle_installer.catalog import PACKAGE_NAME


@dataclass(frozen=True)
class UpdatePolicy:
    mandatory_after: date
    required_packages: tuple[str, ...]


def fetch_update_policy(url: str, timeout: float = 10.0) -> UpdatePolicy | None:
    if not url:
        return None
    if not url.startswith("https://"):
        raise ValueError("The update policy URL must use HTTPS.")

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "OPSLE-Installer/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError(f"Update policy returned HTTP {response.status}.")
            if not response.geturl().startswith("https://"):
                raise ValueError("Update policy redirected to a non-HTTPS URL.")
            raw = response.read(1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not retrieve update policy: {exc}") from exc

    if len(raw) > 1024 * 1024:
        raise ValueError("Update policy response exceeds 1 MiB.")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Update policy is not valid JSON: {exc}") from exc

    if (
        not isinstance(manifest, dict)
        or type(manifest.get("version")) is not int
        or manifest["version"] != 1
        or not isinstance(manifest.get("mandatory_after"), str)
        or not isinstance(manifest.get("required_packages"), list)
        or any(
            not isinstance(package, str) or not PACKAGE_NAME.fullmatch(package)
            for package in manifest["required_packages"]
        )
    ):
        raise ValueError(
            "Update policy must be version 1 with a YYYY-MM-DD mandatory_after date "
            "and package-name entries."
        )

    try:
        mandatory_after = date.fromisoformat(manifest["mandatory_after"])
    except ValueError as exc:
        raise ValueError("Update policy mandatory_after must be a YYYY-MM-DD date.") from exc

    return UpdatePolicy(
        mandatory_after=mandatory_after,
        required_packages=tuple(dict.fromkeys(manifest["required_packages"])),
    )
