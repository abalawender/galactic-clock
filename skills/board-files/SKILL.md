---
name: board-files
description: Manage files on the Galactic Unicorn's MicroPython filesystem (list/get/put/run) via mpremote over USB serial.
---

# Board files (agent)

Prerequisite: board attached to WSL2 (see `skills/board`). Use `mpremote`:

- list:      `mpremote ls :/`
- run code:  `mpremote exec "print(1+1)"`
- run file:  `mpremote run local.py`
- upload:    `mpremote cp local.py :main.py`
- download:  `mpremote cp :main.py local.py`
- reboot:    `mpremote reset`  (reboots into `/main.py`)

Files on the flash: `/main.py` (autostart), `/render.py`, `/tz.py` — exactly
what `scripts/deploy.sh` uploads. `/secrets.py` holds WiFi credentials and
location: gitignored, and it must stay on the board only — never read, print,
or `mpremote cp :secrets.py ...` it (see AGENTS.md golden rules).
The rest of the "default" Python (`galactic`, `picographics`,
`breakout_scd41`, ...) is frozen into the firmware image (visible via
`help('modules')` on the board), not files.

## Boot semantics

- `/boot.py` runs at every power-on/reset before anything else (not used).
- `/main.py` runs at boot right after boot.py — the autostart entry point.
  No main.py present -> plain REPL at boot.
