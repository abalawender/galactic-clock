---
name: board-files
description: Manage files on the Galactic Unicorn's MicroPython filesystem (list/get/put/run) via scripts/mp.py over USB serial.
---

# Board files (agent)

Prerequisite: board attached to WSL2 (see `skills/board`). Use `scripts/mp.py`:

- list:      `python3 scripts/mp.py ls /`
- run code:  `python3 scripts/mp.py exec "print(1+1)"`
- run file:  `python3 scripts/mp.py run local.py`
- upload:    `python3 scripts/mp.py put local.py /main.py`
- download:  `python3 scripts/mp.py get /main.py [local]`

Files currently on the flash: none (empty). The rest of the "default" Python
is frozen into the firmware image (visible via `help('modules')` on the
board), not files.

## Boot semantics

- `/boot.py` runs at every power-on/reset before anything else (we don't use
  it — the RP2040 WDT feeder needs core 1, which is unavailable on Pico W).
- `/main.py` runs at boot right after boot.py — the autostart entry point.
  No main.py present -> plain REPL at boot.
