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

## Run the application on Debian 13/XFCE

```sh
sudo apt update
sudo apt install python3 python3-pyqt6 python3-yaml xfce4-terminal
python3 main.py
```

Check software, select packages, and choose **Install selected** or **Upgrade
selected**. A confirmation appears before APT runs, then a result window reports
success or failure. A terminal opens for the `sudo` password prompt.

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

Review `config.yaml`, then run `sudo sh linux/install_system_updater.sh` on the
target Debian machine. The setup installs a systemd dependency on the detected
display manager; set `display_manager` to `lightdm`, `gdm`, or `sddm` if
automatic detection is not right. It waits for network-online and runs APT
before the display manager. After the date, graphical login remains gated until
updates succeed when `block_login_on_failure` is true.

During updates, Plymouth displays a full-screen boot progress status and
percentage; APT download and package progress feed the percentage. This runs
before the desktop login screen, so it is not a closable app window. The setup
installs Plymouth and configures the boot splash. Test it on a non-critical
machine first. If APT sources cannot be refreshed, or a mandatory update fails,
login can be blocked as configured. To
recover, use a text/recovery console and remove
`/etc/systemd/system/<display-manager>.service.d/opsle-update-gate.conf`, then
run `sudo systemctl daemon-reload`.

The updater writes logs to `/var/log/opsle-updater.log`.
