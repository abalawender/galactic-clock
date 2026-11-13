#!/usr/bin/env bash
# Deploy the weather clock to the board. If the board is not usbipd-attached to
# WSL yet (/dev/ttyACM0 missing), scripts/attach.sh is run automatically first.
#   scripts/deploy.sh               upload main.py + render.py, then reset the board
#   scripts/deploy.sh --no-reset    upload only, keep the current REPL session
#   scripts/deploy.sh --no-attach   never attach; fail if /dev/ttyACM0 is missing
set -euo pipefail
cd "$(dirname "$0")/.."

NO_RESET=0
NO_ATTACH=0
for a in "$@"; do
  case "$a" in
    --no-reset)  NO_RESET=1 ;;
    --no-attach) NO_ATTACH=1 ;;
  esac
done

if [[ ! -e /dev/ttyACM0 ]]; then
  if [[ "$NO_ATTACH" == 1 ]]; then
    echo "error: /dev/ttyACM0 not found and --no-attach given." >&2
    echo "  run: scripts/attach.sh [busid]   # busid auto-detected if omitted" >&2
    exit 1
  fi
  echo "board not attached (/dev/ttyACM0 missing) - running scripts/attach.sh" >&2
  "$(dirname "$0")/attach.sh" || true
fi
if [[ ! -e /dev/ttyACM0 ]]; then
  echo "error: /dev/ttyACM0 still missing after attach attempt." >&2
  echo "  if the port stays missing or the REPL is silent: skills/board/SKILL.md" >&2
  exit 1
fi

mpremote cp main.py :main.py
mpremote cp src/render.py :render.py
mpremote cp src/tz.py :tz.py
echo "deployed main.py + render.py + tz.py (breakout_scd41 is frozen in the firmware)"

if [[ "$NO_RESET" == 0 ]]; then
  mpremote reset   # reboots into /main.py
fi
