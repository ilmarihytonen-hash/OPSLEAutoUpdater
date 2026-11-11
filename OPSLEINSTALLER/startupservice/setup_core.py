"""Validated setup data and system configuration backends."""

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from app_paths import writable_path


SOFTWARE_CATALOG_PATH = Path(__file__).with_name("software.yaml")
CUSTOM_INSTALL_SCRIPT_PATH = Path(__file__).with_name("custom-install.sh")
CONFIGURE_APT_SOURCES_SCRIPT_PATH = Path(__file__).with_name(
    "configure-apt-sources.sh"
)
SETUP_COMPLETION_MARKER_PATH = Path("/var/lib/startupservice/setup-complete")
USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*$")
LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}_[A-Z]{2}(?:@[A-Za-z0-9_-]+)?\.UTF-8$")
KEYBOARD_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

DESKTOP_PACKAGES = {
    "xfce": ["xfce4", "lightdm"],
    "kde": ["kde-plasma-desktop", "sddm"],
}

DISPLAY_MANAGER_SERVICES = {"xfce": "lightdm.service", "kde": "sddm.service"}
SETUP_INFO_FIELDS = (
    "language",
    "locale",
    "keyboard",
    "timezone",
    "full_name",
    "username",
    "desktop",
    "theme",
    "software",
    "school_server",
    "eula_accepted",
)


def load_software_catalog(path=SOFTWARE_CATALOG_PATH):
    """Load and validate the user-visible software choices from YAML."""
    try:
        with open(path, "r", encoding="utf-8") as catalog_file:
            entries = yaml.safe_load(catalog_file)
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"Could not load the software catalog: {error}") from error

    if not isinstance(entries, list) or not entries:
        raise ValueError("The software catalog must contain a non-empty list.")

    catalog = []
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each software catalog entry must be an object.")
        software_id = entry.get("id")
        name = entry.get("name")
        description = entry.get("description")
        packages = entry.get("packages")
        if (
            not isinstance(software_id, str)
            or not re.fullmatch(r"[a-z0-9-]+", software_id)
            or software_id in seen_ids
        ):
            raise ValueError("Software entries need unique, lowercase IDs.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Software entry {software_id} needs a name.")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Software entry {software_id} needs a description.")
        if (
            not isinstance(packages, list)
            or not packages
            or any(
                not isinstance(package, str)
                or not PACKAGE_PATTERN.fullmatch(package)
                for package in packages
            )
        ):
            raise ValueError(f"Software entry {software_id} has invalid packages.")
        seen_ids.add(software_id)
        catalog.append(
            {
                "id": software_id,
                "name": name.strip(),
                "description": description.strip(),
                "packages": packages,
                "recommended": bool(entry.get("recommended", False)),
            }
        )
    return catalog


def validate_setup_data(data, catalog):
    """Validate form data before it can reach a system command."""
    if not isinstance(data, dict):
        raise ValueError("Setup information is missing.")
    locale = data.get("locale")
    keyboard = data.get("keyboard")
    timezone = data.get("timezone")
    username = data.get("username")
    full_name = data.get("full_name")
    password = data.get("password")
    desktop = data.get("desktop")
    theme = data.get("theme")
    eula_accepted = data.get("eula_accepted")
    if not isinstance(locale, str) or not LOCALE_PATTERN.fullmatch(locale):
        raise ValueError("Choose a supported language.")
    if not isinstance(keyboard, str) or not KEYBOARD_PATTERN.fullmatch(keyboard):
        raise ValueError("Choose a supported keyboard layout.")
    if not isinstance(timezone, str) or not TIMEZONE_PATTERN.fullmatch(timezone):
        raise ValueError("Choose a valid time zone.")
    if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must start with a lowercase letter or underscore and "
            "contain only lowercase letters, numbers, underscores, or hyphens."
        )
    if (
        not isinstance(full_name, str)
        or not full_name.strip()
        or "\n" in full_name
        or "\r" in full_name
        or ":" in full_name
    ):
        raise ValueError("Enter a valid name without line breaks or colons.")
    if (
        not isinstance(password, str)
        or len(password) < 8
        or "\n" in password
        or "\r" in password
        or ":" in password
    ):
        raise ValueError("Choose a password with at least 8 characters.")
    if desktop not in DESKTOP_PACKAGES:
        raise ValueError("Choose XFCE or KDE Plasma.")
    if theme not in ("light", "dark"):
        raise ValueError("Choose a light or dark theme.")
    if eula_accepted is not True:
        raise ValueError("You must agree to the EULA before continuing.")

    selected_ids = data.get("software", [])
    if not isinstance(selected_ids, list) or any(
        not isinstance(item, str) for item in selected_ids
    ):
        raise ValueError("The software selection is invalid.")
    entries = {item["id"]: item for item in catalog}
    if len(set(selected_ids)) != len(selected_ids) or any(
        item not in entries for item in selected_ids
    ):
        raise ValueError("The software selection contains an unknown app.")


def _selected_packages(data, catalog):
    selected = set(data["software"])
    app_packages = [
        package
        for app in catalog
        if app["id"] in selected
        for package in app["packages"]
    ]
    return list(dict.fromkeys(DESKTOP_PACKAGES[data["desktop"]] + app_packages))


def build_command_plan(data, catalog):
    """Return the system commands setup would run, without secret values."""
    packages = _selected_packages(data, catalog)
    return [
        ["/bin/sh", str(CONFIGURE_APT_SOURCES_SCRIPT_PATH)],
        ["locale-gen", data["locale"]],
        ["localectl", "set-locale", f"LANG={data['locale']}"],
        ["localectl", "set-keymap", data["keyboard"]],
        ["timedatectl", "set-timezone", data["timezone"]],
        [
            "adduser",
            "--disabled-password",
            "--gecos",
            data["full_name"].strip(),
            data["username"],
        ],
        ["chpasswd"],
        ["apt-get", "update"],
        ["apt-get", "upgrade", "-y"],
        ["apt-get", "install", "-y", "--", *packages],
        ["/bin/sh", str(CUSTOM_INSTALL_SCRIPT_PATH)],
        ["systemctl", "enable", DISPLAY_MANAGER_SERVICES[data["desktop"]]],
    ]


def build_theme_plan(data):
    """Return the theme files setup would write inside the new user's home."""
    if data["desktop"] == "xfce":
        theme_name = "Adwaita-dark" if data["theme"] == "dark" else "Adwaita"
        return [
            (
                ".config/gtk-3.0/settings.ini",
                "[Settings]\n"
                f"gtk-theme-name={theme_name}\n"
                "gtk-icon-theme-name=Adwaita\n",
            ),
            (
                ".config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<channel name="xsettings" version="1.0">\n'
                '  <property name="Net" type="empty">\n'
                f'    <property name="ThemeName" type="string" value="{theme_name}"/>\n'
                '    <property name="IconThemeName" type="string" value="Adwaita"/>\n'
                "  </property>\n"
                "</channel>\n",
            ),
        ]
    color_scheme = "BreezeDark" if data["theme"] == "dark" else "BreezeLight"
    return [
        (
            ".config/kdeglobals",
            "[General]\n"
            f"ColorScheme={color_scheme}\n"
            "[KDE]\n"
            "widgetStyle=Breeze\n",
        )
    ]


def _write_private_json(path, contents):
    serialized = json.dumps(contents, ensure_ascii=False, indent=2) + "\n"
    _write_private_text(path, serialized)


def _write_private_text(path, contents):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(f".{destination.name}.tmp")
    try:
        descriptor = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(contents)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_setup_info(path=None):
    """Load the setup summary, returning an empty object when it does not exist."""
    source = Path(path or writable_path("setup-info.json"))
    try:
        with source.open(encoding="utf-8") as input_file:
            setup_info = json.load(input_file)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load setup information: {error}") from error
    if not isinstance(setup_info, dict):
        raise ValueError(f"Setup information in {source} must be a JSON object.")
    if not isinstance(setup_info.get("already_done", False), bool):
        raise ValueError("The already_done setup flag must be true or false.")
    return setup_info


def mark_setup_complete(path=SETUP_COMPLETION_MARKER_PATH):
    """Create the system marker used to keep the first-boot unit one-shot."""
    marker = Path(path)
    _write_private_text(marker, "completed\n")
    return marker


def save_setup_info(
    data,
    path=None,
    status=None,
    wizard_step=None,
    install_progress=None,
    current_stage=None,
    already_done=False,
):
    """Save setup choices, explicitly excluding all password fields."""
    setup_info = {
        key: data[key]
        for key in SETUP_INFO_FIELDS
        if key in data
    }
    setup_info["saved_at"] = datetime.now(timezone.utc).isoformat()
    setup_info["already_done"] = already_done
    if status is not None:
        setup_info["setup_status"] = status
    if wizard_step is not None:
        setup_info["wizard_step"] = wizard_step
    if install_progress is not None:
        setup_info["install_progress"] = install_progress
    if current_stage is not None:
        setup_info["current_stage"] = current_stage
    destination = path or writable_path("setup-info.json")
    _write_private_json(destination, setup_info)
    return Path(destination)


def _format_debug_report(data, catalog):
    lines = [
        "Startup Service debug plan",
        "No system commands were executed.",
        "Password input to chpasswd is supplied via stdin and is not recorded.",
        "",
        "Planned commands (JSON argument arrays):",
    ]
    for command in build_command_plan(data, catalog):
        annotation = (
            "  (password supplied via stdin; redacted)"
            if command[0] == "chpasswd"
            else ""
        )
        lines.append(
            f"Would run: {json.dumps(command, ensure_ascii=False)}{annotation}"
        )
    lines.extend(
        [
            "",
            "Planned non-command operations:",
            "- Verify the username is not already in use.",
            "- School-server integration is not configured; no connection is made.",
            "- APT upgrade and install commands use DEBIAN_FRONTEND=noninteractive.",
            "",
            "Theme files that would be written under the new user's home:",
        ]
    )
    for relative_path, contents in build_theme_plan(data):
        lines.append(f"Would write: ~/{relative_path}")
        lines.extend(f"  {line}" for line in contents.rstrip("\n").splitlines())
    return "\n".join(lines) + "\n"


def save_debug_report(data, catalog, path=None):
    """Write a development report with planned commands and redacted password input."""
    destination = path or writable_path("setup-debug.log")
    destination = Path(destination)
    _write_private_text(destination, _format_debug_report(data, catalog))
    return destination


class SystemSetupBackend:
    """Apply setup choices, or safely simulate the entire process."""

    def __init__(
        self,
        simulate=False,
        command_runner=subprocess.run,
        debug=False,
        debug_log_path=None,
    ):
        self.simulate = simulate or debug
        self.command_runner = command_runner
        self.debug = debug
        self.debug_log_path = debug_log_path
        self.simulated_steps = []
        self.debug_commands = []

    def _progress(self, callback, message):
        if callback:
            callback(message)

    @staticmethod
    def _report_progress(callback, value):
        if callback:
            callback(value)

    @staticmethod
    def check_network_connection():
        """Check reachability of the distribution's official package mirror."""
        mirror_url = "https://deb.debian.org/debian/"
        release_path = Path("/etc/os-release")
        if release_path.is_file():
            for line in release_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ID=") and line.partition("=")[2].strip('"') == "ubuntu":
                    mirror_url = "https://archive.ubuntu.com/ubuntu/"
                    break
        try:
            request = urllib.request.Request(
                mirror_url,
                method="HEAD",
                headers={"User-Agent": "StartupService/1.0"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.status < 500, (
                    "Internet connection is available."
                    if response.status < 500
                    else f"Package mirror returned HTTP {response.status}."
                )
        except (OSError, TimeoutError) as error:
            return False, f"No internet connection to the package mirror: {error}"

    @staticmethod
    def connect_wifi(ssid, password):
        """Connect through NetworkManager using a temporary, private keyfile."""
        if not ssid or any(character in ssid for character in ("\x00", "\n", "\r")):
            raise ValueError("Enter a valid Wi-Fi network name.")
        if not password or any(
            character in password for character in ("\x00", "\n", "\r")
        ):
            raise ValueError("Enter a valid Wi-Fi password.")
        nmcli = shutil.which("nmcli")
        if nmcli is None:
            raise RuntimeError(
                "NetworkManager (nmcli) is required to connect to Wi-Fi. "
                "Connect using the desktop network menu, then retry."
            )
        profile_uuid = str(uuid4())

        def escape_keyfile_value(value):
            return (
                value.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace(" ", "\\s")
            )

        profile = (
            "[connection]\n"
            "id=StartupService temporary Wi-Fi\n"
            f"uuid={profile_uuid}\n"
            "type=wifi\n"
            "autoconnect=false\n\n"
            "[wifi]\n"
            "mode=infrastructure\n"
            f"ssid={escape_keyfile_value(ssid)}\n\n"
            "[wifi-security]\n"
            "key-mgmt=wpa-psk\n"
            f"psk={escape_keyfile_value(password)}\n\n"
            "[ipv4]\n"
            "method=auto\n\n"
            "[ipv6]\n"
            "method=auto\n"
        )
        descriptor, profile_path = tempfile.mkstemp(
            prefix="startupservice-wifi-", suffix=".nmconnection", dir="/run"
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as profile_file:
                profile_file.write(profile)
            result = subprocess.run(
                [nmcli, "connection", "load", profile_path],
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
            if result.returncode:
                raise RuntimeError(
                    (result.stderr or result.stdout or "Could not load Wi-Fi profile.").strip()
                )
            result = subprocess.run(
                [nmcli, "--wait", "45", "connection", "up", "uuid", profile_uuid],
                text=True,
                capture_output=True,
                check=False,
                timeout=55,
            )
            if result.returncode:
                raise RuntimeError(
                    (result.stderr or result.stdout or "Could not connect to Wi-Fi.").strip()
                )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Timed out while connecting to Wi-Fi.") from error
        finally:
            if os.path.exists(profile_path):
                os.remove(profile_path)

    def _run(self, arguments, callback, input_text=None, environment=None):
        self._progress(callback, f"Running {arguments[0]}…")
        result = self.command_runner(
            arguments,
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
            env=environment,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "").strip()
            if len(detail) > 1200:
                detail = detail[-1200:]
            message = f"{' '.join(arguments)} failed (exit code {result.returncode})."
            if detail:
                message += f"\n\n{detail}"
            raise RuntimeError(message)

    def _step(self, callback, message):
        self._progress(callback, message)
        if self.simulate:
            self.simulated_steps.append(message)

    def configure_school_server(self, settings, callback):
        """Extension point for a future school or directory server connector."""
        if settings.get("school_server"):
            self._step(
                callback,
                "A school server was provided, but server integration is not configured yet.",
            )
            return
        self._step(callback, "School server setup is not configured; skipping it.")

    def apply(self, data, catalog, callback=None, progress_callback=None):
        validate_setup_data(data, catalog)
        if self.simulate:
            self._simulate(data, catalog, callback, progress_callback)
            return
        self._apply_linux(data, catalog, callback, progress_callback)

    def _simulate(self, data, catalog, callback, progress_callback):
        self.simulated_steps = []
        self.debug_commands = build_command_plan(data, catalog) if self.debug else []
        if self.debug:
            report_path = save_debug_report(data, catalog, self.debug_log_path)
            print(_format_debug_report(data, catalog), end="", flush=True)
            print(f"Debug report saved to: {report_path}", flush=True)
        stages = [
            (2, "Checking the internet connection."),
            (5, "Configuring official package sources."),
            (10, f"Applying language {data['locale']}."),
            (20, f"Applying keyboard layout {data['keyboard']}."),
            (30, f"Setting time zone {data['timezone']}."),
            (42, f"Creating the {data['username']} user account."),
            (55, "Refreshing package information."),
            (65, "Upgrading installed system packages."),
            (78, "Installing the selected desktop environment and apps."),
            (88, "Running custom-install.sh."),
            (95, f"Applying the {data['theme']} theme."),
        ]
        for value, stage in stages:
            self._report_progress(progress_callback, value)
            self._step(callback, f"[Preview] {stage}")
        self.configure_school_server(
            {"school_server": data.get("school_server", "")}, callback
        )
        self._report_progress(progress_callback, 100)
        self._step(callback, "[Preview] Setup finished; no system changes were made.")

    def _apply_linux(self, data, catalog, callback, progress_callback):
        if platform.system() != "Linux":
            raise RuntimeError("System installation is supported on Debian or Ubuntu Linux only.")
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            raise RuntimeError("Run startuper.sh with administrator access to install the system.")
        import pwd

        release_path = Path("/etc/os-release")
        release = release_path.read_text(encoding="utf-8").lower()
        if not any(identifier in release for identifier in ("id=debian", "id=ubuntu")):
            raise RuntimeError("This installer currently supports Debian and Ubuntu only.")

        self._report_progress(progress_callback, 0)
        self._step(callback, "Configuring official package sources.")
        self._run(
            ["/bin/sh", str(CONFIGURE_APT_SOURCES_SCRIPT_PATH)],
            callback,
        )
        self._report_progress(progress_callback, 5)
        self._step(callback, f"Applying language {data['locale']}.")
        self._run(["locale-gen", data["locale"]], callback)
        self._run(["localectl", "set-locale", f"LANG={data['locale']}"], callback)
        self._report_progress(progress_callback, 18)
        self._step(callback, f"Applying keyboard layout {data['keyboard']}.")
        self._run(["localectl", "set-keymap", data["keyboard"]], callback)
        self._report_progress(progress_callback, 27)
        self._step(callback, f"Setting time zone {data['timezone']}.")
        self._run(["timedatectl", "set-timezone", data["timezone"]], callback)
        self._report_progress(progress_callback, 34)

        self._step(callback, f"Creating the {data['username']} user account.")
        try:
            pwd.getpwnam(data["username"])
        except KeyError:
            pass
        else:
            raise RuntimeError(
                f"The account '{data['username']}' already exists. Choose a different username."
            )
        self._run(
            [
                "adduser",
                "--disabled-password",
                "--gecos",
                data["full_name"].strip(),
                data["username"],
            ],
            callback,
        )
        self._run(
            ["chpasswd"],
            callback,
            input_text=f"{data['username']}:{data['password']}\n",
        )
        self._report_progress(progress_callback, 46)

        packages = _selected_packages(data, catalog)
        environment = os.environ.copy()
        environment["DEBIAN_FRONTEND"] = "noninteractive"
        self._step(callback, "Refreshing package information.")
        self._run(["apt-get", "update"], callback)
        self._report_progress(progress_callback, 55)
        self._step(callback, "Upgrading installed system packages. This can take a while.")
        self._run(
            ["apt-get", "upgrade", "-y"],
            callback,
            environment=environment,
        )
        self._report_progress(progress_callback, 65)
        self._step(callback, f"Installing {len(packages)} selected packages.")
        self._run(
            ["apt-get", "install", "-y", "--", *packages],
            callback,
            environment=environment,
        )
        self._report_progress(progress_callback, 80)
        self._step(callback, "Running custom-install.sh.")
        custom_environment = os.environ.copy()
        custom_environment.update(
            {
                "STARTUPSERVICE_USERNAME": data["username"],
                "STARTUPSERVICE_FULL_NAME": data["full_name"].strip(),
                "STARTUPSERVICE_LOCALE": data["locale"],
                "STARTUPSERVICE_KEYBOARD": data["keyboard"],
                "STARTUPSERVICE_TIMEZONE": data["timezone"],
                "STARTUPSERVICE_DESKTOP": data["desktop"],
                "STARTUPSERVICE_THEME": data["theme"],
                "STARTUPSERVICE_SOFTWARE_IDS": " ".join(data["software"]),
                "STARTUPSERVICE_PACKAGES": " ".join(packages),
                "DEBIAN_FRONTEND": "noninteractive",
            }
        )
        self._run(
            ["/bin/sh", str(CUSTOM_INSTALL_SCRIPT_PATH)],
            callback,
            environment=custom_environment,
        )
        self._report_progress(progress_callback, 90)
        self._step(callback, "Enabling the selected desktop login service.")
        self._run(
            ["systemctl", "enable", DISPLAY_MANAGER_SERVICES[data["desktop"]]],
            callback,
        )
        self._report_progress(progress_callback, 95)
        self._step(callback, f"Applying the {data['theme']} desktop theme.")
        self._apply_theme(data)
        self.configure_school_server(
            {"school_server": data.get("school_server", "")}, callback
        )
        self._report_progress(progress_callback, 100)

    def _apply_theme(self, data):
        import pwd

        user = pwd.getpwnam(data["username"])
        home = Path(user.pw_dir)
        for relative_path, contents in build_theme_plan(data):
            self._write_user_file(
                home,
                user,
                relative_path,
                contents,
            )

    @staticmethod
    def _write_user_file(home, user, relative_path, contents):
        destination = home / relative_path
        created_directories = []
        directory = home
        for component in Path(relative_path).parts[:-1]:
            directory = directory / component
            if directory.is_symlink():
                raise RuntimeError(f"Refusing to write through a symbolic link: {directory}")
            if not directory.exists():
                directory.mkdir()
                created_directories.append(directory)
        if destination.is_symlink():
            raise RuntimeError(f"Refusing to replace a symbolic link: {destination}")
        destination.write_text(contents, encoding="utf-8")
        for directory in created_directories:
            os.chown(directory, user.pw_uid, user.pw_gid, follow_symlinks=False)
        os.chown(destination, user.pw_uid, user.pw_gid, follow_symlinks=False)
