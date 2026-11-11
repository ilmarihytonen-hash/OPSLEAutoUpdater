import logging
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from opsle_installer.apt import installed_packages, package_install_command, update_command
from opsle_installer.config import load_config
from opsle_installer.localization import translate
from opsle_installer.policy import fetch_update_policy


LOG = logging.getLogger("opsle-updater")
STATE_PATH = Path("/var/lib/opsle-updater/last-completed-date")

if TYPE_CHECKING:
    from opsle_installer.config import UpdaterConfig


def splash_progress(progress: int, message: str) -> None:
    progress = min(100, max(0, progress))
    status = f"{translate('Do not power off your computer.')} {translate(message)}"
    if not plymouth_is_active():
        LOG.info("%s (Plymouth is not active; continuing without splash.)", status)
        return
    try:
        subprocess.run(
            [
                "plymouth",
                "system-update",
                f"--progress={progress / 100:.2f}",
                f"--status={status}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        LOG.info("%s", status)


def plymouth_is_active() -> bool:
    executable = shutil.which("plymouth")
    if executable is None:
        return False
    try:
        result = subprocess.run(
            [executable, "--ping"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def parse_apt_progress(line: str) -> int | None:
    fields = line.strip().split(":")
    if fields[0] == "pmstatus" and len(fields) > 2:
        candidate = fields[2]
    elif fields[0] == "dlstatus" and len(fields) > 1:
        candidate = fields[-1]
    else:
        return None
    try:
        progress = int(candidate)
    except ValueError:
        return None
    return progress if 0 <= progress <= 100 else None


def run_apt_step(
    command: list[str], start: int, end: int, message: str
) -> None:
    splash_progress(start, message)
    LOG.info("%s", message)
    apt_options = [
        "-o",
        "Dpkg::Progress-Fd=1",
        "-o",
        "APT::Status-Fd=1",
    ]
    process = subprocess.Popen(
        [command[0], *apt_options, *command[1:]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        if process.stdout is None:
            raise RuntimeError("Could not read APT progress output.")
        last_progress = start
        for line in process.stdout:
            command_progress = parse_apt_progress(line)
            if command_progress is not None:
                mapped_progress = start + (end - start) * command_progress // 100
                last_progress = max(last_progress, mapped_progress)
                splash_progress(last_progress, message)
            else:
                LOG.info("%s", line.rstrip())
        return_code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def last_completed_date(state_path: Path) -> date | None:
    try:
        value = state_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid updater completion state in {state_path}.") from exc


def save_completed_date(state_path: Path, completed_date: date) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(f"{state_path.name}.tmp")
    temporary_path.write_text(completed_date.isoformat() + "\n", encoding="ascii")
    temporary_path.replace(state_path)


def run_updates(
    config: "UpdaterConfig | None" = None,
    state_path: Path = STATE_PATH,
) -> int:
    if config is None:
        config = load_config()
    if not config.enabled or not config.run_before_login:
        LOG.info("Pre-login updater is disabled.")
        return 0

    run_apt_step(["apt-get", "update"], 0, 15, "Checking software sources...")

    policy = fetch_update_policy(config.policy_url)
    today_utc = datetime.now(timezone.utc).date()
    if policy is None or today_utc < policy.mandatory_after:
        splash_progress(100, "No mandatory update is due. Starting login...")
        return 0

    completed_date = last_completed_date(state_path)
    if completed_date is not None and completed_date >= policy.mandatory_after:
        splash_progress(100, "Mandatory updates are already complete. Starting login...")
        return 0

    LOG.info("Mandatory update deadline reached: %s", policy.mandatory_after)
    steps: list[tuple[list[str], str]] = []

    required_packages = list(policy.required_packages)
    managed_installed = (
        sorted(set(config.managed_packages) & installed_packages())
        if config.managed_packages
        else []
    )
    packages_to_install = list(dict.fromkeys(required_packages + managed_installed))
    if packages_to_install:
        steps.append(
            (
                package_install_command(packages_to_install),
                "Installing mandatory software updates...",
            )
        )
    if config.update_all_packages:
        steps.append((update_command(), "Installing system updates..."))

    progress_start = 15
    remaining_progress = 85
    for index, (command, message) in enumerate(steps):
        progress_end = (
            100
            if index == len(steps) - 1
            else progress_start + remaining_progress // (len(steps) - index)
        )
        run_apt_step(command, progress_start, progress_end, message)
        remaining_progress -= progress_end - progress_start
        progress_start = progress_end

    if not steps:
        splash_progress(100, "No updates are configured. Starting login...")
        return 0

    save_completed_date(state_path, policy.mandatory_after)
    splash_progress(100, "Mandatory updates complete. Restarting...")
    subprocess.run(["systemctl", "reboot"], check=True)
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("/var/log/opsle-updater.log"),
        ],
    )
    config = None
    try:
        config = load_config()
        return run_updates(config)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        LOG.exception("Pre-login update failed: %s", exc)
        splash_progress(100, "Updates failed. Login remains blocked; contact your administrator.")
        if config is not None and not config.block_login_on_failure:
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
