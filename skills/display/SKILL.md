---
name: display
description: Display static content (text, Mistral logo) on the Pimoroni Galactic Unicorn 53x11 LED matrix through MicroPython over USB serial (WSL + usbipd).
---

# Display on Galactic Unicorn

## Prerequisites

- Board attached to WSL (`scripts/attach.sh`, see README "Connect")
- `mpremote` installed (`apt install micropython-mpremote`)

## Usage

```bash
python3 skills/display/display.py                  # orange dots flying around, plays until interrupted
python3 skills/display/display.py --text "Hi"      # static text (clips at 53 px)
python3 skills/display/display.py --logo           # static Mistral logo
python3 skills/display/display.py --stop           # interrupt animation and clear
```

## How it works

`display.py` in this folder builds a MicroPython snippet and runs it on the
board via `mpremote run`. The dots animation loops in the board's main thread;
any later `mpremote` call interrupts it with Ctrl-C (that is how `--stop` works):

```python
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
# ... draw ...
gu.update(d)
```
