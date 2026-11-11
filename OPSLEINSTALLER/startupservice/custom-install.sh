#!/bin/sh
set -eu

# Add optional system-wide install commands here. This script runs as root
# after the selected APT packages are installed.
#
# Available environment variables:
#   STARTUPSERVICE_USERNAME
#   STARTUPSERVICE_FULL_NAME
#   STARTUPSERVICE_LOCALE
#   STARTUPSERVICE_KEYBOARD
#   STARTUPSERVICE_TIMEZONE
#   STARTUPSERVICE_DESKTOP
#   STARTUPSERVICE_THEME
#   STARTUPSERVICE_SOFTWARE_IDS
#   STARTUPSERVICE_PACKAGES
#   DEBIAN_FRONTEND
#
# Do not put passwords or other secrets in this script.
apt update
apt install -y dolphin snapd git ssh flatpak kdeconnect syncthing bitwarden ufw fail2ban openssh-server logwatch sysstat
