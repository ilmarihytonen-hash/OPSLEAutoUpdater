#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$(uname -s)" = "Linux" ] && [ -f /etc/debian_version ]; then
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run this installer as root (for example: sudo $0)." >&2
        exit 1
    fi
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y python3 python3-pyqt6 python3-yaml
elif [ "$(uname -s)" != "Linux" ]; then
    echo "This script installs dependencies only on Debian or Ubuntu Linux." >&2
    echo "For a no-install UI preview, run: python setup.py --preview" >&2
    exit 1
fi

exec python3 "$SCRIPT_DIR/setup.py" "$@"
