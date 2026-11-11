#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/opsle-installer
UNIT_NAME=opsle-system-update.service
LAUNCHER=/usr/local/bin/opsle-installer
DESKTOP_ENTRY=/usr/share/applications/opsle-installer.desktop
INSTALL_DEPENDENCIES=1
DEFER_UNTIL_FIRST_SETUP=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-dependencies)
            INSTALL_DEPENDENCIES=0
            ;;
        --defer-until-first-setup)
            DEFER_UNTIL_FIRST_SETUP=1
            ;;
        *)
            echo "Usage: sudo $0 [--skip-dependencies] [--defer-until-first-setup]" >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root (for example: sudo $0)." >&2
    exit 1
fi
if [ ! -f /etc/os-release ]; then
    echo "Cannot identify the operating system; install on Debian." >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ]; then
    echo "This installer supports Debian. Detected: ${PRETTY_NAME:-unknown}." >&2
    exit 1
fi
if [ ! -x /usr/bin/apt-get ] || [ ! -x /usr/bin/python3 ]; then
    echo "This installer requires apt-get and Python 3." >&2
    exit 1
fi
if [ ! -f "$PROJECT_ROOT/opsle_installer/app.py" ]; then
    echo "Run this installer from a complete OPSLE project directory." >&2
    exit 1
fi
if [ ! -f "$PROJECT_ROOT/linux/$UNIT_NAME" ]; then
    echo "Run this installer from a complete OPSLE project directory." >&2
    exit 1
fi

if [ "$INSTALL_DEPENDENCIES" -eq 1 ]; then
    apt-get update
    apt-get install -y python3-yaml python3-pyqt6
fi

DISPLAY_MANAGER=$(PYTHONPATH="$PROJECT_ROOT" /usr/bin/python3 -c '
from opsle_installer.config import configured_display_manager
print(configured_display_manager())
')
if ! systemctl cat "$DISPLAY_MANAGER" >/dev/null 2>&1; then
    echo "Could not find $DISPLAY_MANAGER; configure a supported display manager in config.yaml." >&2
    exit 1
fi

install -d "$INSTALL_ROOT/opsle_installer" /etc/systemd/system
cp -a "$PROJECT_ROOT/opsle_installer/." "$INSTALL_ROOT/opsle_installer/"
install -m 0644 "$PROJECT_ROOT/main.py" "$INSTALL_ROOT/main.py"
if [ ! -e "$INSTALL_ROOT/config.yaml" ]; then
    install -m 0644 "$PROJECT_ROOT/config.yaml" "$INSTALL_ROOT/config.yaml"
fi
install -m 0644 "$PROJECT_ROOT/linux/$UNIT_NAME" "/etc/systemd/system/$UNIT_NAME"

cat > "$LAUNCHER" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /opt/opsle-installer/main.py "$@"
EOF
chmod 0755 "$LAUNCHER"

install -d "$(dirname -- "$DESKTOP_ENTRY")"
cat > "$DESKTOP_ENTRY" <<'EOF'
[Desktop Entry]
Type=Application
Name=OPSLE Software Installer
Comment=Install and upgrade selected software
Exec=/usr/local/bin/opsle-installer
Icon=system-software-install
Terminal=false
Categories=System;Utility;
EOF
chmod 0644 "$DESKTOP_ENTRY"

DROP_IN_DIR="/etc/systemd/system/$DISPLAY_MANAGER.d"
install -d "$DROP_IN_DIR"
cat > "$DROP_IN_DIR/opsle-update-gate.conf" <<'EOF'
[Unit]
Requires=opsle-system-update.service
After=opsle-system-update.service
EOF

UPDATER_DROP_IN_DIR="/etc/systemd/system/$UNIT_NAME.d"
FIRST_SETUP_DROP_IN="$UPDATER_DROP_IN_DIR/startupservice-first-setup.conf"
if [ "$DEFER_UNTIL_FIRST_SETUP" -eq 1 ]; then
    install -d "$UPDATER_DROP_IN_DIR"
    cat > "$FIRST_SETUP_DROP_IN" <<'EOF'
[Unit]
ConditionPathExists=/var/lib/startupservice/setup-complete
EOF
else
    rm -f "$FIRST_SETUP_DROP_IN"
fi

systemctl daemon-reload
if command -v plymouth >/dev/null 2>&1 && plymouth --ping >/dev/null 2>&1; then
    echo "Plymouth is active now; the updater will display translated progress when active."
else
    echo "Plymouth is inactive now; the updater will check again at boot and continue without a splash if unavailable."
fi
echo "Installed OPSLE Software Installer. Launch it from the applications menu or run: opsle-installer"
if [ "$DEFER_UNTIL_FIRST_SETUP" -eq 1 ]; then
    echo "Installed the pre-login update gate for $DISPLAY_MANAGER."
    echo "The updater is deferred until /var/lib/startupservice/setup-complete exists."
else
    echo "Installed the pre-login update gate for $DISPLAY_MANAGER. It will run on the next boot."
fi
echo "Plymouth is optional; this installer does not enable it or modify GRUB."
echo "On updater failure, use a recovery console to disable $DROP_IN_DIR/opsle-update-gate.conf."
