#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run the APT sources setup as root." >&2
    exit 1
fi

if [ ! -r /etc/os-release ]; then
    echo "Cannot detect the Linux distribution (/etc/os-release is missing)." >&2
    exit 1
fi

. /etc/os-release
CODENAME=${VERSION_CODENAME:-}
if [ -z "$CODENAME" ]; then
    echo "Cannot detect the distribution release codename." >&2
    exit 1
fi

SOURCE_DIR=/etc/apt/sources.list.d
STARTUPSERVICE_SOURCES="$SOURCE_DIR/startupservice.list"
CUSTOM_SOURCES=/opt/startupservice/custom-apt-sources.list
TEMP_SOURCES=$(mktemp "$SOURCE_DIR/.startupservice.XXXXXX")
trap 'rm -f "$TEMP_SOURCES"' EXIT HUP INT TERM

case "${ID:-}" in
    debian)
        DEBIAN_MAJOR=${VERSION_ID%%.*}
        if [ "$DEBIAN_MAJOR" -ge 12 ]; then
            COMPONENTS="main contrib non-free non-free-firmware"
        else
            COMPONENTS="main contrib non-free"
        fi
        cat > "$TEMP_SOURCES" <<EOF
deb https://deb.debian.org/debian $CODENAME $COMPONENTS
deb https://deb.debian.org/debian $CODENAME-updates $COMPONENTS
deb https://security.debian.org/debian-security $CODENAME-security $COMPONENTS
EOF
        ;;
    ubuntu)
        COMPONENTS="main restricted universe multiverse"
        ARCHITECTURE=$(dpkg --print-architecture)
        case "$ARCHITECTURE" in
            amd64|i386)
                ARCHIVE=https://archive.ubuntu.com/ubuntu
                SECURITY=https://security.ubuntu.com/ubuntu
                ;;
            *)
                ARCHIVE=https://ports.ubuntu.com/ubuntu-ports
                SECURITY=https://ports.ubuntu.com/ubuntu-ports
                ;;
        esac
        cat > "$TEMP_SOURCES" <<EOF
deb $ARCHIVE $CODENAME $COMPONENTS
deb $ARCHIVE $CODENAME-updates $COMPONENTS
deb $ARCHIVE $CODENAME-backports $COMPONENTS
deb $SECURITY $CODENAME-security $COMPONENTS
EOF
        ;;
    *)
        echo "Unsupported APT sources setup for distribution: ${ID:-unknown}" >&2
        exit 1
        ;;
esac

if [ -f "$CUSTOM_SOURCES" ]; then
    cat "$CUSTOM_SOURCES" >> "$TEMP_SOURCES"
fi

chmod 0644 "$TEMP_SOURCES"
mv -f "$TEMP_SOURCES" "$STARTUPSERVICE_SOURCES"
trap - EXIT HUP INT TERM
echo "Configured official ${ID} sources for ${CODENAME} in ${STARTUPSERVICE_SOURCES}."
