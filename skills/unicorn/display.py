#!/usr/bin/env python3
"""Display on the Galactic Unicorn via MicroPython (through mpremote).

Usage:
    python3 skills/display/display.py                  # orange dots flying around
    python3 skills/display/display.py --text "Hi"      # static text (clips at 53 px)
    python3 skills/display/display.py --logo           # static Mistral logo (brand gradient)
    python3 skills/display/display.py --icons          # HITL review: cycle every weather
                                                       # icon on the board, 3 s each, WMO code
                                                       # labelled ("n" = night); loops until
                                                       # interrupted, then `mpremote reset`
                                                       # returns to the weather clock
    python3 skills/display/display.py --spotify5       # HITL review: ~15 s of the two-line
                                                       # 5px now-playing screen (deployed
                                                       # render.py); then `mpremote reset`
    python3 skills/display/display.py --stop           # interrupt animation and clear

The animation loop runs in the board's main REPL thread, so any later mpremote
call interrupts it with Ctrl-C (that is also what --stop does).
"""
import argparse
import subprocess
import tempfile

ANIM = """from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
import time, random
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W, H = gu.WIDTH, gu.HEIGHT
N = 12
dots = [[random.randint(0, W - 1), random.randint(0, H - 1),
         random.choice([-1, 1]), random.choice([-1, 1])] for _ in range(N)]
state = {"run": True}
while state["run"]:
    d.set_pen(d.create_pen(0, 0, 0))
    d.rectangle(0, 0, W, H)
    for dot in dots:
        x, y, dx, dy = dot
        d.set_pen(d.create_pen(255, 100 + random.randint(0, 80), 0))
        d.pixel(x, y)
        x += dx
        if x < 0:
            x, dx = 0, -dx
        if x >= W:
            x, dx = W - 1, -dx
        y += dy
        if y < 0:
            y, dy = 0, -dy
        if y >= H:
            y, dy = H - 1, -dy
        dot[0], dot[1], dot[2], dot[3] = x, y, dx, dy
    gu.update(d)
    time.sleep(0.05)
"""

TEXT = """from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
d.set_pen(d.create_pen(255, 255, 255))
d.text(%r, 1, 2, scale=1)
gu.update(d)
"""

# Mistral "M" logo: vertical bars with a valley in the middle, brand gradient
# yellow (#FFD800) -> orange -> red (#E10500) from left to right.
LOGO = """from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W, H = gu.WIDTH, gu.HEIGHT
heights = [H, H, 6, 2, 6, H, H]
x0 = (W - len(heights)) // 2
for i, h in enumerate(heights):
    t = i / (len(heights) - 1)
    d.set_pen(d.create_pen(255, int(216 - 206 * t), 0))
    d.rectangle(x0 + i, 0, 1, h)  # bars hang from the top -> "M"
gu.update(d)
"""

# HITL icon review: cycle every weather icon variant on the matrix, 3 s each,
# with the WMO code drawn next to it ("n" suffix = night variant). Uses the
# deployed render.py, so this shows exactly what the board firmware will draw.
ICONS = """from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
import render
import time
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W, H = gu.WIDTH, gu.HEIGHT
CODES = [(0, 1), (2, 1), (3, 1), (45, 1), (51, 1), (61, 1), (65, 1),
         (71, 1), (75, 1), (80, 1), (85, 1), (95, 1), (0, 0), (2, 0)]
i = 0
frame = 0
while True:
    code, day = CODES[i % len(CODES)]
    label = "%d" % code if day else "%dn" % code
    end = time.time() + 3
    while time.time() < end:
        d.set_pen(d.create_pen(0, 0, 0))
        d.rectangle(0, 0, W, H)
        render.draw_icon(d, code, frame, 0, 0, day)
        d.set_pen(d.create_pen(255, 255, 255))
        d.text(label, 14, 2, scale=1)
        gu.update(d)
        frame += 1
        time.sleep(0.15)
    i += 1
"""

# HITL two-line now-playing review: uses the deployed render.py, so this shows
# exactly what the board draws. ~15 s of the 5px artist/title marquee with the
# progress bar, then the snippet exits (mpremote reset returns to the clock).
SPOTIFY5 = """from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
import render
import time
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W, H = gu.WIDTH, gu.HEIGHT
frame = 0
for _ in range(150):  # ~15 s at 0.1 s per frame
    render.clear(d, W, H)
    render.draw_spotify5(d, W, H, "Daft Punk", "Around the World (Radio Edit)",
                         frame, 0.37)
    gu.update(d)
    frame += 1
    time.sleep(0.1)
"""

CLEAR = """from galactic import GalacticUnicorn
GalacticUnicorn().clear()
"""


def run(code, timeout=10):
    # NamedTemporaryFile is deleted on close; on Linux the subprocess can
    # read the path while the file is still open.
    with tempfile.NamedTemporaryFile("w", suffix=".py") as f:
        f.write(code)
        f.flush()
        try:
            subprocess.run(["mpremote", "run", f.name], timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # the animation loops forever on the board; that is expected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", help="static text to show instead of the animation")
    ap.add_argument("--logo", action="store_true", help="show the Mistral logo")
    ap.add_argument("--icons", action="store_true",
                    help="HITL review: cycle all weather icons on the board, "
                         "3 s each with the WMO code labelled; loops until "
                         "interrupted (then --stop / mpremote reset)")
    ap.add_argument("--spotify5", action="store_true",
                    help="HITL review: ~15 s of the two-line 5px now-playing screen "
                         "(deployed render.py), then exits; mpremote reset returns "
                         "to the weather clock")
    ap.add_argument("--stop", action="store_true", help="interrupt animation and clear")
    args = ap.parse_args()

    if args.stop:
        run(CLEAR)
    elif args.spotify5:
        run(SPOTIFY5, timeout=30)
    elif args.icons:
        # review loops forever on the board; the timeout only bounds the local
        # subprocess — interrupt with Ctrl-C / --stop when done reviewing
        run(ICONS, timeout=600)
    elif args.logo:
        run(LOGO)
    elif args.text is not None:
        run(TEXT % args.text)
    else:
        # animation never returns to the prompt; a short timeout hands it over
        run(ANIM, timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
