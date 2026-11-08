# AGENTS.md — galactic-clock

Pimoroni Galactic Unicorn (53x11 LED matrix) on a Raspberry Pi Pico W running
MicroPython. Weather clock: open-meteo forecast rotated with a clock and a
hi/lo screen.

## Golden rules

- **Never read, print, or commit `secrets.py`** (WiFi credentials, location,
  `SCD41_ALTITUDE_M`). It is gitignored; the board holds the only copy.
  Variable contract + how to create it: `secrets.example.py` and README
  "Board configuration" — fill the template, upload host -> board, delete local.
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
  `python3 sim/sim.py play ...` animates in the terminal. Render the whole
  rotation loop (real `main.py`, fully mocked) to a GIF for reviews:
  `python3 sim/run_main.py --seconds 18 --gif /tmp/rotation.gif` (needs Pillow).
  In agent sandboxes the ambient `LD_LIBRARY_PATH` can point at an incompatible
  libstdc++ (e.g. the editor's), which breaks Pillow's libLerc with
  `GLIBCXX_3.4.29 not found`; run with a clean env instead:
  `env -i HOME=$HOME PATH=/usr/bin:/bin:/usr/local/bin python3 ...` — same for
  `python3 -m unittest discover -s tests` so the Pillow-dependent GIF test
  actually runs instead of skipping.
- **Run the tests with any display change**:
  `python3 -m unittest discover -s tests -v` — bitmap property checks, golden
  ASCII dumps, tz DST rules, and a mocked full run of `main.py`.
- **Recordings are never committed** (`frames/`, `*.gif` gitignored — the one
  exception is the tracked README demo `docs/demo-rotation.gif`). For a
  pull request, generate a GIF on demand and attach it, e.g.
  `python3 sim/before_after.py --ref main --out /tmp/pr`
  → attach e.g. `/tmp/pr_weather_compare.gif` to the PR.

## Pull requests

Most contributions here come from agents — this file is the contract:

1. Branch off `micropython`: `git checkout -b feat/my-change micropython`
   (`fix/...` for fixes). Never push to `main`/`micropython` directly.
2. Clean commit queue: small, atomic commits, one logical change each,
   `<type>: <what>` messages (`feat:`, `fix:`, `docs:`, `refactor:`, `tests:`,
   `ci:`, `scripts:`) — see `git log` for examples.
3. Before pushing, run `python3 -m unittest discover -s tests -v` and preview
   any display change in `sim/` (above).
4. Push the branch and open the PR against `micropython`. CI
   (`.github/workflows/pr-sim.yml`, triggered by changes to `main.py`/`src/`/
   `sim/`/`tests/`) runs the tests and posts before/after GIFs of every changed
   screen inline on the PR (artifact `sim-before-after`; screens pixel-identical
   to the base produce no GIFs). For icon changes, also do a HITL pass on the
   physical board: `python3 skills/display/display.py --icons` after
   `scripts/deploy.sh --no-reset` (so the board runs *your* render.py), then
   `mpremote reset` to return to the clock.
   `micropython` is protected by a ruleset: one approving review and all threads
   resolved are required; merges are **rebase-only with required linear
   history** (no squash — the atomic commits from step 2 are what lands);
   deletion and non-fast-forward pushes are blocked; the `micropython-check`
   status (workflow of the same name) must be green **and up to date** (strict
   policy). So before asking for review / merging, rebase:
   `git fetch origin && git rebase origin/micropython` and re-push.
5. If the change affects rendering, regenerate the README demo GIF in the same
   branch: `python3 sim/run_main.py --seconds 18 --delay 0.12 --gif
   docs/demo-rotation.gif`. The `micropython-check` workflow runs on the PR and
   on push to `micropython` (`.github/workflows/micropython-check.yml` →
   `sim/check_demo_gif.py`) and fails if code and GIF disagree — it must be a
   required check in branch protection to actually block the merge. `tests/`
   runs the same comparison locally (skipped without Pillow).

## Layout

- `main.py` — board entry point (WiFi/NTP/open-meteo/SCD41 + screen loop), thin
- `src/render.py` — all drawing; pure functions taking a PicoGraphics-like `d`
- `src/tz.py` — EU DST offset, pure integer math (no tzdata on the board)
- `sim/` — host simulator: `sim.py`, `font6_data.py` (Pimoroni font6),
  `run_main.py` (mocked full run of main.py), `before_after.py` (PR GIFs)
- `tests/` — unittest suite, host-only (`python3 -m unittest discover -s tests -v`)
- `scripts/` — attach.sh, deploy.sh
- `skills/`, `docs/` — board attach/recovery, flash file management, on-device
  display snippets, flashing notes
- `firmware/` — local .uf2 copy (gitignored)

## Branches

`main`, `micropython` (PR target — active work happens on short-lived
`feat/*` / `fix/*` branches merged into it).
Check `git branch` before committing; do not push without asking.
PR flow: see "Pull requests" above.
