#!/usr/bin/env bash
# Attach the Galactic Unicorn (Pico W) USB serial device to WSL via usbipd.
# Prerequisite (once, as admin on the Windows host):
#   usbipd bind --busid <busid>    (busid from `usbipd list`; it changes
#                                   with the USB port, so never hardcode it)
# Usage: scripts/attach.sh [busid]
# Without a busid argument the board is found by its USB vendor id
# (Raspberry Pi Foundation, 2e8a) in `usbipd list` — no per-host config.
set -euo pipefail

USBIPD="usbipd.exe"
BUSID="${1:-}"
if [ -z "$BUSID" ]; then
  BUSID=$("$USBIPD" list | awk '$0 ~ /2e8a/ { print $1; exit }')
  if [ -z "$BUSID" ]; then
    echo "no Pico W (USB vendor 2e8a) found — usbipd list:" >&2
    "$USBIPD" list >&2 || true
    echo "if it is listed as not shared: usbipd bind --busid <busid> (as admin)" >&2
    exit 1
  fi
fi
echo "attaching busid $BUSID"

"$USBIPD" attach --wsl --busid "$BUSID"
sleep 2
ls -la /dev/ttyACM0
