---
name: board
description: Make the Galactic Unicorn (Pico W) available in WSL2 via usbipd when /dev/ttyACM0 is missing or the REPL is unresponsive. Agent-side recovery procedure.
---

# Board attach / recovery

Use when `/dev/ttyACM0` is missing or `mpremote exec` gets no response.

Fast path first: `ls /dev/ttyACM0` — if missing, run `scripts/attach.sh`
(which is just `usbipd.exe attach --wsl --busid 2-2`; `scripts/deploy.sh`
auto-runs it too). Verify with `mpremote exec "print('ok')"`. Only if attach
fails or the REPL stays silent, work through the manual recovery below:

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
4. Verify: `mpremote exec "print('ok')"`
5. REPL still silent -> `mpremote exec "import machine; machine.reset()"`,
   wait ~5 s, re-attach if the port vanished, verify again
