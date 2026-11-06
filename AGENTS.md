# AGENTS.md — galactic-unicorn

Pimoroni Galactic Unicorn (53x11 LED matrix) on a Raspberry Pi Pico W running
MicroPython. Weather clock: open-meteo forecast rotated with a clock and a
hi/lo screen.

## Golden rules

- **Never read, print, or commit `secrets.py`** (WiFi credentials, location,
  `SCD41_ALTITUDE_M`). It is gitignored; the board holds the only copy.
- Board code must stay MicroPython-compatible: no CPython-only stdlib, match
  the existing `%`-formatting style, keep `src/render.py` free of board imports
  (it also runs on the host in `sim/`).
- The SCD41 driver is frozen into Pimoroni's MicroPython firmware
  (`breakout_scd41`, `pimoroni_i2c`) — do not vendor a copy; the sim mocks
  those two modules (sim/run_main.py).
- Deploy only `main.py`, `src/render.py` and `src/tz.py` to the flash root.

## Workflow

- Board attach (Windows host + WSL2, usbipd): `scripts/attach.sh` (once per
  boot on Windows: `usbipd bind --busid 2-2` as admin). Board shows up as
  `/dev/ttyACM0`. If missing/unresponsive: `skills/board/SKILL.md`.
- Deploy: `scripts/deploy.sh` → `mpremote cp main.py :main.py`,
  `mpremote cp src/render.py :render.py`, `mpremote cp src/tz.py :tz.py`,
  `mpremote reset`. It fails fast with
  the attach hint if the board is not usbipd-attached (`/dev/ttyACM0` missing).
  File management: `skills/board-files/SKILL.md`. One-off display snippets:
  `skills/display/`.
- **Preview display changes in sim/ before deploying** — not as a fallback for
  a detached board, but because you can actually see what the matrix will
  show, using the exact `src/render.py` code and real bitmap6 font metrics:
  `python3 sim/sim.py print --screen weather --code 61 --temp 21 --frames 8`
  writes plain ASCII frames to stdout for agent analysis;
  `python3 sim/sim.py play ...` animates in the terminal.
- **Recordings are never committed** (`frames/`, `*.gif` gitignored). For a
  pull request, generate a GIF on demand and attach it, e.g.
  `python3 sim/before_after.py --ref main --out /tmp/pr`
  → attach e.g. `/tmp/pr_weather_compare.gif` to the PR.

## Layout

- `main.py` — board entry point (WiFi/NTP/open-meteo + screen loop), thin
- `src/render.py` — all drawing; pure functions taking a PicoGraphics-like `d`
- `sim/` — host simulator (`sim.py`) + `font6_data.py` (Pimoroni font6, for the sim)
- `skills/`, `docs/` — board attach/flashing/display procedures
- `firmware/` — local .uf2 copy (gitignored)

## Branches

`main` and `micropython` (active work happens on `micropython`), plus `tts`.
Check `git branch` before committing; do not push without asking.
