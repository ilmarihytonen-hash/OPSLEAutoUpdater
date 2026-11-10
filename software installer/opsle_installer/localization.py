import ctypes
import json
import locale
import os
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path


_LOCALE_FILES = (Path("/etc/default/locale"), Path("/etc/locale.conf"))
_CATALOG_DIR = Path(__file__).with_name("locales")
_LANGUAGE_NAMES = {
    "chinese": "zh_CN",
    "dutch": "nl",
    "english": "en",
    "finnish": "fi",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "polish": "pl",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
    "swedish": "sv",
    "ukrainian": "uk",
}
_LOCALE_PATTERN = re.compile(r"^([a-zA-Z]+)(?:[_-]([a-zA-Z]+))?")


def _language_code(value: str) -> str | None:
    value = value.strip().split(".", 1)[0].split("@", 1)[0]
    match = _LOCALE_PATTERN.match(value)
    if match is None:
        return None

    language = match.group(1).lower()
    territory = (match.group(2) or "").upper()
    if language in {"c", "posix"}:
        return None
    if language == "zh":
        return "zh_CN" if not territory or territory in {"CN", "SG"} else None
    if language in {"fr", "de", "es", "it", "pt", "nl", "pl", "ru", "uk", "ja", "fi", "sv"}:
        return language
    if language == "en" or language in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES.get(language, "en")
    return None


def _codes_from_value(value: str) -> Sequence[str]:
    codes = []
    for candidate in value.split(":"):
        code = _language_code(candidate)
        if code is not None:
            codes.append(code)
    return codes


def get_system_language(
    environment: Mapping[str, str] | None = None,
    locale_files: Sequence[Path] = _LOCALE_FILES,
) -> str:
    environment = os.environ if environment is None else environment
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        codes = _codes_from_value(environment.get(key, ""))
        if codes:
            return codes[0]

    for path in locale_files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            key, separator, value = line.partition("=")
            if separator and key.strip() in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"}:
                codes = _codes_from_value(value.strip().strip("\"'"))
                if codes:
                    return codes[0]

    if os.name == "nt":
        try:
            locale_name = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(locale_name, len(locale_name)):
                code = _language_code(locale_name.value)
                if code is not None:
                    return code
        except (AttributeError, OSError):
            pass

    try:
        current_locale = locale.getlocale()[0]
    except (TypeError, ValueError):
        current_locale = None
    return _language_code(current_locale or "") or "en"


@lru_cache(maxsize=14)
def _load_catalog(language: str) -> dict[str, str]:
    catalog_path = _CATALOG_DIR / f"{language}.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load language catalog {catalog_path}: {exc}") from exc
    if not isinstance(catalog, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in catalog.items()
    ):
        raise ValueError(f"Language catalog {catalog_path} must contain string mappings.")
    return catalog


def translate(message: str, language: str | None = None) -> str:
    language = get_system_language() if language is None else (
        _language_code(language) or "en"
    )
    return _load_catalog(language).get(message, message)
