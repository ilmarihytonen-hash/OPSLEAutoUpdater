#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OPSLE_SERVICE_DIR="$SCRIPT_DIR/../software installer/linux"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root (for example: sudo sh $0)." >&2
    exit 1
fi
if [ ! -f /etc/os-release ]; then
    echo "Cannot identify the operating system." >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ]; then
    echo "The combined VM installer supports Debian. Detected: ${PRETTY_NAME:-unknown}." >&2
    exit 1
fi
if [ ! -x /usr/bin/systemctl ] || [ ! -x /usr/bin/apt-get ]; then
    echo "This installer requires systemd and APT." >&2
    exit 1
fi
if [ ! -f "$OPSLE_SERVICE_DIR/install_system_updater.sh" ]; then
    echo "The separate service project was not found at: $OPSLE_SERVICE_DIR" >&2
    echo "Keep 'software installer' beside 'startupservice'." >&2
    exit 1
fi

export OPSLE_SERVICE_DIR
exec sh "$SCRIPT_DIR/install-iso.sh" --enable-service
