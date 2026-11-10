# OPSLE Software Installer

The project has a PyQt6 software-selection app, a Debian APT updater, and
unit tests that can be run on Windows. The installer and pre-login update
workflow are intended for Debian with systemd and APT.

## Development and tests (Windows or Linux)

Install Python dependencies:

```text
python -m pip install -r requirements.txt
```

Run the unit tests without APT or a graphical session:

```text
python -m unittest discover -s tests -v
```

Windows is supported for running the unit tests, not for installing software.

## Run the application on Debian 13

```sh
sudo apt update
sudo apt install python3 python3-pyqt6 python3-yaml konsole
python3 main.py
```

Check software, select packages, and choose **Install selected** or **Upgrade
selected**. A confirmation appears before APT runs, then a result window reports
success or failure. A terminal opens for the `sudo` password prompt.
The app supports KDE Plasma's Konsole and also checks the system
`x-terminal-emulator` and XFCE Terminal.

The catalog is at `opsle_installer/data/installable_software.yaml`. Each entry
has a Debian package name, display name, and description; environment fields are
not used.

## Pre-login system updater (Debian only)

`config.yaml` controls the updater. At every startup, it refreshes configured
APT sources. Before the mandatory date, it does not install updates and allows
normal login. On or after the date, it installs required packages, upgrades all
eligible system packages, then reboots after success. `managed_packages` can
explicitly name additional installed packages to upgrade. Add a trusted HTTPS
`policy_url` to supply the mandatory date and required packages:

```json
{"version": 1, "mandatory_after": "2026-12-01", "required_packages": ["opsle-agent"]}
```

The date is interpreted in UTC. Only package names are accepted from this
endpoint; packages are still fetched from the machine's configured APT sources.
The endpoint is unset by default, so no mandatory date is active until you
configure it.
The updater records a successfully completed date so it does not reboot on every
subsequent startup; advance the policy date to schedule another mandatory cycle.

Review `config.yaml`, then run `sudo sh linux/install_system_updater.sh` from
the project directory on the target Debian machine. This installs the desktop
app and its Python dependencies, adds an applications-menu launcher, installs
the systemd updater service, and gates the detected display manager on that
service. Set `display_manager` to `lightdm`, `gdm`, or `sddm` if automatic
detection is not right. The service waits for network-online and runs APT
before the display manager. After the date, graphical login remains gated until
updates succeed when `block_login_on_failure` is true.

During updates, Plymouth displays a full-screen boot progress status and
percentage when its daemon is active; APT download and package progress feed
the percentage. If Plymouth is absent or inactive, updates continue without a
splash and progress is written to the updater log. The installer does not
install Plymouth, enable a boot splash, or modify GRUB. This runs before the
desktop login screen, so it is not a closable app window. Test it on a
non-critical machine first. If APT sources cannot be refreshed, or a mandatory
update fails, login can be blocked as configured. To
recover, use a text/recovery console and remove
`/etc/systemd/system/<display-manager>.service.d/opsle-update-gate.conf`, then
run `sudo systemctl daemon-reload`.
The update status includes a translated “Do not power off your computer”
warning. The language is selected from the system locale, with translations for
English, French, German, Spanish, Italian, Portuguese, Dutch, Polish, Russian,
Ukrainian, Simplified Chinese, Japanese, Finnish, and Swedish; unsupported
locales fall back to English. Each translation is maintained in its own JSON
file under `opsle_installer/locales/`.

The updater writes logs to `/var/log/opsle-updater.log`.

To preview the update progress screen on Windows or Linux, install the Python
dependencies and run this from the project directory:

```text
python -m opsle_installer.preview
```

This is a desktop simulation of the progress text and percentage; it does not
run APT or reboot, and it cannot verify the actual Plymouth theme shown during
boot. Press **F5** to replay the sequence or **Esc** to close the preview.
