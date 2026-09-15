#!/usr/bin/env bash
# Attach the Galactic Unicorn (Pico W) USB serial device to WSL via usbipd.
# Prerequisite (once, as admin on the Windows host): usbipd bind --busid 2-2
# Usage: scripts/attach.sh [busid]   (default busid: 2-2)
set -euo pipefail

USBIPD="usbipd.exe"
BUSID="${1:-2-2}"

"$USBIPD" attach --wsl --busid "$BUSID"
sleep 2
ls -la /dev/ttyACM0
