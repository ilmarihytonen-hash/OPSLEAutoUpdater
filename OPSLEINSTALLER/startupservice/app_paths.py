"""Application resource and writable configuration paths."""

import os
import shutil
import sys


def resource_path(filename):
    """Return the absolute path to a file shipped beside the application."""
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


def writable_path(filename):
    """Return a per-user path for application configuration."""
    if os.name == "nt":
        base_path = os.environ.get("APPDATA")
        if not base_path:
            base_path = os.path.expanduser("~")
        return os.path.join(base_path, "StartupService", filename)

    home = os.path.expanduser("~")
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and hasattr(os, "geteuid") and os.geteuid() == 0:
        try:
            import pwd

            home = pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            pass

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if not config_home:
        config_home = os.path.join(home, ".config")
    return os.path.join(config_home, "startupservice", filename)


def migrate_legacy_file(filename):
    """Copy a shipped legacy config to its writable location once."""
    source = resource_path(filename)
    destination = writable_path(filename)
    if os.path.abspath(source) == os.path.abspath(destination):
        return
    if os.path.isfile(source) and not os.path.exists(destination):
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
