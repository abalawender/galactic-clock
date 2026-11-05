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

## Layout

- `scripts/` — attach.sh
- `main.py` — board autostart (deploy: `mpremote cp main.py :main.py`)
