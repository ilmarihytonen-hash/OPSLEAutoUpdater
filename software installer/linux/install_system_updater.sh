#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/opsle-installer
UNIT_NAME=opsle-system-update.service

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root (for example: sudo $0)." >&2
    exit 1
fi
if [ ! -f /etc/default/grub ]; then
    echo "Missing /etc/default/grub; configure the Plymouth splash manually." >&2
    exit 1
fi

install -d "$INSTALL_ROOT" /etc/systemd/system
cp -a "$PROJECT_ROOT/opsle_installer" "$INSTALL_ROOT/"
if [ ! -e "$INSTALL_ROOT/config.yaml" ]; then
    install -m 0644 "$PROJECT_ROOT/config.yaml" "$INSTALL_ROOT/config.yaml"
fi
install -m 0644 "$PROJECT_ROOT/linux/$UNIT_NAME" "/etc/systemd/system/$UNIT_NAME"

apt-get update
apt-get install -y python3-yaml plymouth plymouth-themes

cp -n /etc/default/grub /etc/default/grub.opsle-backup
python3 - <<'PY'
from pathlib import Path
import re

path = Path("/etc/default/grub")
content = path.read_text(encoding="utf-8")
pattern = re.compile(r'^(GRUB_CMDLINE_LINUX_DEFAULT=")([^"]*)(")$', re.MULTILINE)
match = pattern.search(content)
if match is None:
    raise SystemExit("Could not safely find GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub")
options = match.group(2).split()
for option in ("quiet", "splash"):
    if option not in options:
        options.append(option)
updated = pattern.sub(match.group(1) + " ".join(options) + match.group(3), content, count=1)
path.write_text(updated, encoding="utf-8")
PY
plymouth-set-default-theme spinner
update-grub
update-initramfs -u -k all

DISPLAY_MANAGER=$(PYTHONPATH="$INSTALL_ROOT" /usr/bin/python3 -c '
from opsle_installer.config import configured_display_manager
print(configured_display_manager())
')
systemctl cat "$DISPLAY_MANAGER" >/dev/null

DROP_IN_DIR="/etc/systemd/system/$DISPLAY_MANAGER.d"
install -d "$DROP_IN_DIR"
cat > "$DROP_IN_DIR/opsle-update-gate.conf" <<'EOF'
[Unit]
Requires=opsle-system-update.service
After=opsle-system-update.service
EOF

systemctl daemon-reload
echo "Installed pre-login update gate for $DISPLAY_MANAGER."
echo "Plymouth spinner splash configured; verify it on the next boot."
echo "Reboot to activate. On failure, use a recovery console to disable the display-manager drop-in."
