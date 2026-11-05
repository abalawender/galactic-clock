# Flashing notes (reference)

Firmware: see README (pimoroni/unicorn v1.29.0, `pico_w_galactic-v1.29.0-micropython.uf2`).
Keep a local copy in `firmware/` (gitignored).

## Steps

1. `mpremote exec "import machine; machine.bootloader()"` — board
   re-enumerates as RP2 Boot (`2e8a:0003`); Windows mounts `RPI-RP2` at `E:`.
2. `cp firmware/*.uf2 /mnt/e/` — bootloader flashes and reboots by itself.
3. `scripts/attach.sh` — re-attach serial; verify:
   `mpremote exec "import os; print(os.uname().version)"`.

## Gotchas (observed)

- Writes via `/mnt/e` (DrvFs) can lag up to ~2 min before the device sees them;
  copying from Windows itself (PowerShell `Copy-Item ... E:\`) lands immediately.
- Ejecting `E:` on Windows unmounts the volume but does NOT reboot the board out
  of bootloader mode.
- `usbipd bind --busid 2-2` once as admin on Windows is required before attach.
- dd-to-partition via usbipd (`of=/dev/sdd1`) needs disk group/sudo — not used;
  `picotool` on the Windows host is an alternative.
