---
name: mpremote
description: Working with the board over mpremote/REPL — attach/recovery (usbipd) plus the rule that mpremote exec interrupts the running main.py. Read before any mpremote exec.
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
(which is just `usbipd.exe attach --wsl --busid 2-2`; `scripts/deploy.sh`
auto-runs it too). Verify the REPL answers with `mpremote exec "print('ok')"`
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
