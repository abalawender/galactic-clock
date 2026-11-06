# galactic-unicorn

Pimoroni Galactic Unicorn (53x11 LED matrix) on Raspberry Pi Pico W, running MicroPython.

## Environment

- Windows 11 host + WSL2 (Ubuntu-24.04); repo: `/home/adam/dev/galactic-unicorn`
- Board on host USB bus 2-2; usbipd: `usbipd.exe`; `mpremote` (apt install micropython-mpremote)
- Firmware: MicroPython v1.29.0 board build `pico_w_galactic-v1.29.0-micropython.uf2`
  from https://github.com/pimoroni/unicorn/releases/tag/v1.29.0

## Connect

```
# once, as admin on Windows:
usbipd bind --busid 2-2
# from WSL:
usbipd.exe attach --wsl --busid 2-2   # -> /dev/ttyACM0
mpremote exec "import os; print(os.uname().version)"
```

## Board API

```python
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
gu = GalacticUnicorn()                       # 53x11
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
d.set_pen(d.create_pen(255, 60, 0))
d.pixel(26, 5)
gu.update(d)
```

## Simulate on the host

See exactly what the 53x11 matrix will show — without touching the board.
`sim/sim.py` runs the same `src/render.py` as the board, with a faithful
re-implementation of the PicoGraphics bitmap6 font (`sim/font6_data.py`), so
layouts match the device pixel-for-pixel. The sim never reads `secrets.py`;
weather values are CLI args (`--code/--temp/--hi/--lo`).

```
python3 sim/sim.py print  --screen weather --code 61 --temp 21 --frames 8
                              # plain ASCII frames on stdout (for agent analysis)
python3 sim/sim.py play   --screen weather --code 61 --temp 21   # animate in terminal
python3 sim/sim.py play   --screen hilo --hi 25 --lo 18
```

Recordings are generated on demand and never committed (gitignored):

```
python3 sim/sim.py play --screen weather --code 61 --frames 16 --gif /tmp/rain.gif
python3 sim/before_after.py --ref main --screen weather --code 61 --out /tmp/pr_rain
                              # writes /tmp/pr_rain_{before,after,compare}.gif — attach to the PR
```

## Layout

- `AGENTS.md` — ramp-up essentials: golden rules, workflow, layout
- `main.py` — board entry point: WiFi/NTP/open-meteo + screen loop (thin)
- `src/render.py` — all drawing; pure functions, no board imports
- `sim/` — host simulator (`sim.py`, `font6_data.py`)
- `scripts/` — attach.sh, deploy.sh (uploads `main.py` + `src/render.py`, resets board)
- `skills/`, `docs/`, `firmware/` — board procedures and local uf2 (gitignored)

Deploy: `scripts/deploy.sh` (board attached first, see Connect above).
