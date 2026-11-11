# Startup Service

Startup Service is a PyQt6 first-start wizard for Debian and Ubuntu images. It
collects locale, keyboard, time zone, a user account, optional school-server
details, application selections, desktop, and theme. Application choices are
configured in `software.yaml`; wizard translations live in `locales/`.
The wizard offers Danish, English, German, Spanish, Finnish, French, Italian,
Japanese, Dutch, Polish, Portuguese, Russian, Swedish, Ukrainian, and
Simplified Chinese. Text not yet translated in a catalog falls back to English.

## Preview and tests (Windows or Linux)

Install the Python dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python setup.py --preview
```

On Linux, use `.venv/bin/python` in place of the Windows executable path.
Preview mode runs the complete wizard and simulates all setup operations; it
does not call system tools, change system settings, create users, install
packages, or reboot. Headless UI and backend tests can be run with:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest -v
```

For development, set `"debug_mode": true` in the active `config.json` to
simulate setup even when launching without `--preview`. Debug mode never runs
system commands. It prints the planned command argument lists and theme-file
changes to the console, and writes them to `setup-debug.log`; password input
to `chpasswd` is redacted. In debug mode, press `Ctrl+Shift+Q` to close the
wizard from any step.
The wizard also saves the submitted setup choices to `setup-info.json` before
starting setup and updates its status when setup finishes. That file
intentionally excludes the password and is written with owner-only permissions
on Linux. Debug mode finishes with a close-only screen and never prompts for or
attempts a reboot.

The wizard opens fullscreen, frameless, and always on top. In normal
(non-debug, non-preview) mode, application close requests are ignored; the
debug-only shortcut is not installed.

On Linux, these files are stored under
`$XDG_CONFIG_HOME/startupservice/` (or `~/.config/startupservice/` by default).
On Windows, they are stored under `%APPDATA%\\StartupService\\`. Edit the
writable `config.json` there to enable debug mode; the bundled `config.json`
is the default for a fresh installation.

The wizard creates `setup-info.json` as soon as it opens and updates it while
you make selections and while installation runs. It records the current step,
install progress, setup choices, and an `already_done` flag, but never
passwords. The flag becomes `true` only after a real installation succeeds;
debug and preview runs leave it `false`. A later launch refuses to start if the
flag is already true. To intentionally repeat setup, remove or reset the
summary file first. The installation
progress bar tracks completed setup phases; a long-running APT operation or
custom script stays at its current phase until it finishes.

Before a real install starts, the wizard checks access to the detected
distribution's official package mirror. If the check fails, enter Wi-Fi
credentials and connect through NetworkManager. The temporary root-only
NetworkManager profile is removed after connection.

Add optional install commands to `custom-install.sh`. The installer copies it
to `/opt/startupservice/`, then runs it with `/bin/sh` as root after APT
installs the selected packages. It receives the selected username, locale,
keyboard, time zone, desktop, theme, software IDs, and package list through
`STARTUPSERVICE_*` environment variables. Keep secrets out of the script.
Debug mode prints this planned invocation but does not execute the script.

`configure-apt-sources.sh` adds official Debian or Ubuntu entries to its own
managed file under `/etc/apt/sources.list.d/`; it does not replace existing
repository files. Add development-team repository lines to
`custom-apt-sources.list`, which the image installer copies to
`/opt/startupservice/` and the sources script appends to the managed file.

## Debian/Ubuntu image integration

The wizard displays the contents of `eula.txt` without translating or changing
the file. Real installation is blocked until a non-empty `eula.txt` is present
and the user accepts it. The school-server field is intentionally only an
extension point; it does not configure accounts or passwords yet.

Keep the sibling `software installer` project beside this folder. From the
Debian VM, run `sudo sh install.sh`. It installs the setup wizard and software
installer, installs their separate systemd units from
`../software installer/linux/`, and enables the first-start wizard. The wizard
runs after the display manager on first boot, so its network window can connect
before APT is needed. The pre-login updater is deferred until the wizard writes
its one-time completion marker; on later boots it runs before the display
manager. The wizard service is skipped after first setup.

The service defaults to `DISPLAY=:0`; desktop images may need XAUTHORITY or
Wayland environment values in `/etc/default/startupservice`. Verify the
display manager's graphical-session environment in the target VM before
rebooting. The OPSLE updater is configured to run before login; if APT update
fails, its default policy can block the display manager. Keep a recovery
console available and review `../software installer/config.yaml` before
installation. The pre-login updater may also perform its configured mandatory
updates and reboot after they succeed.

For preparing an image without enabling the wizard yet, run
`sudo sh install-iso.sh`; enable it later with
`sudo systemctl enable startupservice.service`. Alternatively, run
`sudo ./startuper.sh` from a configured target graphical session.

The real backend currently supports Debian and Ubuntu, requires root, and
installs packages using APT. Do not run it on a machine that should not be
reconfigured.
