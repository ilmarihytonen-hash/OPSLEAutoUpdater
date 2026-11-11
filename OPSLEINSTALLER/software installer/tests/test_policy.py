import json
import unittest
from unittest.mock import patch

from opsle_installer.policy import fetch_update_policy


class FakeResponse:
    status = 200

    def __init__(self, value: object, url: str = "https://policy.example/updates") -> None:
        self.body = json.dumps(value).encode("utf-8")
        self.url = url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body[:size]

    def geturl(self) -> str:
        return self.url


class PolicyTests(unittest.TestCase):
    def test_reads_unique_required_packages_from_https_manifest(self) -> None:
        response = FakeResponse(
            {
                "version": 1,
                "mandatory_after": "2026-12-01",
                "required_packages": ["opsle-agent", "opsle-agent"],
            }
        )
        with patch("opsle_installer.policy.urllib.request.urlopen", return_value=response):
            policy = fetch_update_policy("https://policy.example/updates")
        self.assertEqual(policy.mandatory_after.isoformat(), "2026-12-01")
        self.assertEqual(policy.required_packages, ("opsle-agent",))

    def test_rejects_http_policy_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            fetch_update_policy("http://policy.example/updates")

    def test_rejects_invalid_package_names(self) -> None:
        response = FakeResponse(
            {
                "version": 1,
                "mandatory_after": "2026-12-01",
                "required_packages": ["; rm -rf /"],
            }
        )
        with patch("opsle_installer.policy.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "version 1"):
                fetch_update_policy("https://policy.example/updates")

    def test_rejects_redirect_to_http(self) -> None:
        response = FakeResponse(
            {
                "version": 1,
                "mandatory_after": "2026-12-01",
                "required_packages": [],
            },
            url="http://policy.example/updates",
        )
        with patch("opsle_installer.policy.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "redirected"):
                fetch_update_policy("https://policy.example/updates")

    def test_requires_iso_mandatory_date(self) -> None:
        response = FakeResponse(
            {
                "version": 1,
                "mandatory_after": "not-a-date",
                "required_packages": [],
            }
        )
        with patch("opsle_installer.policy.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                fetch_update_policy("https://policy.example/updates")


if __name__ == "__main__":
    unittest.main()
