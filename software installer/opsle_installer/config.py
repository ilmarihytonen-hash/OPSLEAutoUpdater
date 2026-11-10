import re
from dataclasses import dataclass
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
DISPLAY_MANAGERS = {
    "auto": None,
    "lightdm": "lightdm.service",
    "gdm": "gdm3.service",
    "sddm": "sddm.service",
}
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")


@dataclass(frozen=True)
class UpdaterConfig:
    enabled: bool
    run_before_login: bool
    display_manager: str
    update_all_packages: bool
    block_login_on_failure: bool
    policy_url: str
    managed_packages: tuple[str, ...]


def load_config(path: Path = CONFIG_PATH) -> UpdaterConfig:
    try:
        with path.open(encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not read configuration: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("updater"), dict):
        raise ValueError("Configuration must contain an 'updater' mapping.")
    settings = data["updater"]
    enabled = settings.get("enabled")
    run_before_login = settings.get("run_before_login")
    display_manager = settings.get("display_manager")
    update_all = settings.get("update_all_packages")
    block_login = settings.get("block_login_on_failure")
    policy_url = settings.get("policy_url")
    managed_packages = settings.get("managed_packages")

    if (
        not isinstance(enabled, bool)
        or not isinstance(run_before_login, bool)
        or not isinstance(display_manager, str)
        or display_manager not in DISPLAY_MANAGERS
        or not isinstance(update_all, bool)
        or not isinstance(block_login, bool)
        or not isinstance(policy_url, str)
        or (policy_url and not policy_url.startswith("https://"))
        or not isinstance(managed_packages, list)
        or any(
            not isinstance(package, str) or not PACKAGE_NAME.fullmatch(package)
            for package in managed_packages
        )
    ):
        raise ValueError("Invalid updater settings in config.yaml.")

    return UpdaterConfig(
        enabled=enabled,
        run_before_login=run_before_login,
        display_manager=display_manager,
        update_all_packages=update_all,
        block_login_on_failure=block_login,
        policy_url=policy_url,
        managed_packages=tuple(managed_packages),
    )


def configured_display_manager(
    path: Path = CONFIG_PATH,
    default_manager_file: Path = Path("/etc/X11/default-display-manager"),
) -> str:
    config = load_config(path)
    if config.display_manager != "auto":
        return DISPLAY_MANAGERS[config.display_manager] or "display-manager.service"

    try:
        executable = default_manager_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(
            "Could not detect the display manager. Set display_manager in config.yaml."
        ) from exc

    manager = Path(executable).name.lower()
    detected = {
        "lightdm": "lightdm.service",
        "gdm3": "gdm3.service",
        "gdm": "gdm3.service",
        "sddm": "sddm.service",
    }.get(manager)
    if detected is None:
        raise ValueError(
            f"Unsupported display manager {manager!r}; set a supported manager in config.yaml."
        )
    return detected
