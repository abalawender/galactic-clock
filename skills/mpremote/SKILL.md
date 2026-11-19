---
name: mpremote
description: Working with the board over mpremote/REPL — attach/recovery (usbipd), flash file management, and the rule that mpremote exec interrupts the running main.py. Read before any mpremote exec.
---

# mpremote / REPL on the Galactic Unicorn (Pico W)

## `mpremote exec` stops the main program

Running `mpremote exec ...` takes over the REPL and **stops the running
`main.py` loop** — the clock halts (blank/frozen matrix). Rules:

- Never use `mpremote exec "print(...)"` as a liveness check of the clock.
  A deploy is verified by `scripts/deploy.sh` output alone (it ends with
  `mpremote reset`, which reboots into `main.py`).
- Use `exec` only for deliberate probes/demos. Afterwards `mpremote reset`
  (or `scripts/deploy.sh`) to return the board to the clock.
- Ctrl-C in the REPL also kills the main loop — avoid it.

## Board attach / recovery

Use when `/dev/ttyACM0` is missing or the REPL is unresponsive.

Fast path first: `ls /dev/ttyACM0` — if missing, run `scripts/attach.sh`
(auto-detects the busid by USB vendor 2e8a; `scripts/deploy.sh` auto-runs it
too). **Every `mpremote reset` re-enumerates the USB device and drops the
wsL attach** — after any reset, re-run `scripts/attach.sh` before the next
command that touches `/dev/ttyACM0`. Verify the REPL answers with
`mpremote exec "print('ok')"`
— remember this halts `main.py` (fine in recovery; reset afterwards). Only
if attach fails or the REPL stays silent, work through the manual recovery
below:

1. List host USB devices: `usbipd.exe list`
2. Find the board by VID:PID:
   - `2e8a:0005` — MicroPython running (normal state)
   - `2e8a:0003` — RP2 Boot: board is in bootloader, RPI-RP2 mass-storage drive
     is on Windows (usable for flashing via `/mnt/<letter>`)
   - `0000:0002` / "Device Descriptor Request Failed" — board crashed; ask the
     operator to unplug/replug
3. Attach to WSL: `usbipd.exe attach --wsl --busid <busid>` -> `/dev/ttyACM0`
   - "Device is not shared" -> operator runs `usbipd bind --busid <busid>`
     as admin on Windows first
4. Verify: `mpremote exec "print('ok')"` (halts main.py — see above)
5. REPL still silent -> `mpremote exec "import machine; machine.reset()"`,
   wait ~5 s, re-attach if the port vanished, verify again

## Files on the flash

Prerequisite: board attached to WSL2 (see above). Use `mpremote`:

- list:      `mpremote ls :/`
- run code:  `mpremote exec "print(1+1)"` (halts main.py — see above)
- run file:  `mpremote run local.py`
- upload:    `mpremote cp local.py :main.py`
- download:  `mpremote cp :main.py local.py`
- reboot:    `mpremote reset`  (reboots into `/main.py` — this drops the
  WSL usbipd attach; re-run `scripts/attach.sh` before the next command)

Files on the flash: `/main.py` (autostart), `/render.py`, `/tz.py` — exactly
what `scripts/deploy.sh` uploads. `/secrets.py` holds WiFi credentials and
location: gitignored, and it must stay on the board only — never read, print,
or `mpremote cp :secrets.py ...` it (see AGENTS.md golden rules). To *create*
it, copy the committed template `secrets.example.py`, fill in real values, and
upload host -> board only (`mpremote cp secrets.py :secrets.py`), then delete
the local file; the variable contract is documented in README "Board
configuration".
The rest of the "default" Python (`galactic`, `picographics`,
`breakout_scd41`, ...) is frozen into the firmware image (visible via
`help('modules')` on the board), not files. Board firmware APIs: see
`skills/unicorn`.

## Boot semantics

- `/boot.py` runs at every power-on/reset before anything else (not used).
- `/main.py` runs at boot right after boot.py — the autostart entry point.
  No main.py present -> plain REPL at boot.

## RAM persistence across resets — there is none (REPL-verified)

App-state history must be rebuilt in RAM after any reset (soft reset,
`machine.reset()`, power cycle): nothing on the RP2040 retains RAM. Modules
are no escape hatch either, on this firmware:

- `sys.<attr> = x` **raises** `AttributeError: 'module' object has no
  attribute '<attr>'`.
- `builtins.<attr> = x` is worse: it **silently no-ops** — no exception, but
  a `getattr(builtins, attr, default)` in the very same script returns the
  default (the value is never stored). A bare `try` around the assignment is
  a false positive; always re-read the attribute to check it stuck.

Verified 2026-11-18 via `scripts/attach.sh` + a probe through REPL. To
re-verify (REPL summary: `type(time.time())`, storing into an `array('i')`):

```python
import time, array, sys, builtins
print(type(time.time()))            # int on this build — NOT float
a = array.array("i", (0,) * 4)
try:
    a[0] = 1.5                       # measure()-like float
except Exception as e:
    print(e)                         # TypeError: can't convert float to int
try:
    sys.x = 1
except Exception as e:
    print(e)                         # AttributeError: no attribute 'x'
builtins.x = 1
print(getattr(builtins, "x", None))  # None — silently dropped
```

Related board facts (same probe, same day): `breakout_scd41.measure()`
returns floats (co2 among them), so any value destined for a `array('i')` /
`array('H')` ring must pass `int()` first; `array` supports no repetition
(`a * 2` raises `TypeError: unsupported types for __mul__`) — prefill via a
tuple, `array("i", (0,) * N)`.
