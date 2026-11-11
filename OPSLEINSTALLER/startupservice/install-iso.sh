#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVICE_DIR=${OPSLE_SERVICE_DIR:-"$SCRIPT_DIR/../software installer/linux"}
ENABLE_SERVICE=0
if [ "${1:-}" = "--enable-service" ]; then
    ENABLE_SERVICE=1
elif [ "$#" -gt 0 ]; then
    echo "Usage: sudo $0 [--enable-service]" >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this image preparation script as root." >&2
    exit 1
fi
if [ ! -f /etc/os-release ]; then
    echo "Cannot identify the operating system." >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ]; then
    echo "The combined image installer supports Debian. Detected: ${PRETTY_NAME:-unknown}." >&2
    exit 1
fi
if [ ! -f "$SERVICE_DIR/install_system_updater.sh" ] || \
    [ ! -f "$SERVICE_DIR/startupservice.service" ] || \
    [ ! -f "$SERVICE_DIR/opsle-system-update.service" ]; then
    echo "The separate service files were not found in: $SERVICE_DIR" >&2
    echo "Keep the 'software installer' folder beside 'startupservice'." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pyqt6 python3-yaml network-manager
sh "$SERVICE_DIR/install_system_updater.sh" \
    --skip-dependencies --defer-until-first-setup
install -d -m 0755 /opt/startupservice /etc/default
install -d -m 0755 /var/lib/startupservice/config
install -m 0644 "$SCRIPT_DIR/setup.py" "$SCRIPT_DIR/setup_ui.py" \
    "$SCRIPT_DIR/setup_core.py" "$SCRIPT_DIR/app_paths.py" \
    "$SCRIPT_DIR/configreader.py" "$SCRIPT_DIR/software.yaml" \
    "$SCRIPT_DIR/config.json" \
    /opt/startupservice/
install -m 0644 "$SCRIPT_DIR/custom-install.sh" /opt/startupservice/
install -m 0644 "$SCRIPT_DIR/configure-apt-sources.sh" \
    "$SCRIPT_DIR/custom-apt-sources.list" /opt/startupservice/
install -d -m 0755 /opt/startupservice/locales
install -m 0644 "$SCRIPT_DIR"/locales/*.json /opt/startupservice/locales/
if [ -f "$SCRIPT_DIR/eula.txt" ]; then
    install -m 0644 "$SCRIPT_DIR/eula.txt" /opt/startupservice/eula.txt
else
    echo "Note: Add eula.txt before producing the final image; installation stays disabled until it exists."
fi
install -m 0644 "$SERVICE_DIR/startupservice.service" \
    /etc/systemd/system/startupservice.service
if [ ! -f /etc/default/startupservice ]; then
    printf '%s\n' '# Add display-manager-specific environment variables here if needed.' \
        > /etc/default/startupservice
fi
systemctl daemon-reload
if [ "$ENABLE_SERVICE" -eq 1 ]; then
    systemctl enable startupservice.service
fi
echo "Startup Service installed under /opt/startupservice."
echo "OPSLE updater and its separate systemd units are installed."
if [ "$ENABLE_SERVICE" -eq 1 ]; then
    echo "The first-boot service starts after the display manager."
    echo "The pre-login updater gate activates after first setup completes."
    echo "Verify DISPLAY/XAUTHORITY in /etc/default/startupservice for your VM."
else
    echo "Enable it in your image with: systemctl enable startupservice.service"
fi
