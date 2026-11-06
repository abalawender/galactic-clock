#!/usr/bin/env python3
"""Host simulator for the Galactic Unicorn weather clock.

Runs the exact same rendering code as the board (src/render.py) against a
software framebuffer with a faithful re-implementation of the PicoGraphics
bitmap6 font (sim/font6_data.py, from pimoroni-pico), so layouts measured and
drawn here match the device pixel-for-pixel.

Usage:
    python3 sim/sim.py print  --screen weather --code 61 --temp 21 --frames 8
                                 # plain ASCII frames to stdout (for agents/diffs)
    python3 sim/sim.py play   --screen weather --code 61 --temp 21 --frames 12
                                 # animated in the terminal
    python3 sim/sim.py play   --screen clock --frames 8
    python3 sim/sim.py play   --screen hilo --hi 25 --lo 18
    python3 sim/sim.py play   --screen clock --frames 30 --gif /tmp/clock.gif
                                 # animated GIF (needs Pillow); generate for PRs,
                                 # never commit (gitignored)
    python3 sim/before_after.py --ref main --out /tmp/pr
                                 # before/after/compare GIFs per screen, from a git ref

Screens: weather (icon + temp), clock, hilo, message. --frames N renders N
animation ticks (frame 0..N-1); --delay sets playback seconds per frame.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render  # noqa: E402
import font6_data  # noqa: E402

W, H = 53, 11


class SimGraphics:
    """Drop-in replacement for the PicoGraphics subset used by render.py."""

    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.fb = [[(0, 0, 0)] * w for _ in range(h)]
        self.pen = (0, 0, 0)

    # -- PicoGraphics-compatible API -----------------------------------------
    def create_pen(self, r, g, b):
        return (r, g, b)

    def set_pen(self, p):
        self.pen = p

    def pixel(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.fb[y][x] = self.pen

    def rectangle(self, x, y, w, h):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy)

    def measure_text(self, s, scale=1, spacing=1, fixed_width=False):
        # mirrors bitmap::measure_text: sum(width*scale + spacing*scale),
        # minus the trailing spacing
        total = 0
        for ch in s:
            o = ord(ch)
            w = font6_data.WIDTHS[o - 32] if 32 <= o < 128 else 0
            if fixed_width:
                w = 6
            total += (w + spacing) * scale
        return total - spacing * scale if total > 0 else 0

    def text(self, s, x, y, wordwrap=0, scale=1, angle=0, spacing=1,
             fixed_width=False):
        cx = x
        for ch in s:
            o = ord(ch)
            if not 32 <= o < 128:
                cx += spacing * scale
                continue
            cols = font6_data.GLYPHS[ch]
            w = 6 if fixed_width else font6_data.WIDTHS[o - 32]
            for col in range(w):
                bits = cols[col]
                for row in range(font6_data.HEIGHT):
                    if bits >> row & 1:
                        for sy in range(scale):
                            for sx in range(scale):
                                self.pixel(cx + col * scale + sx,
                                           y + row * scale + sy)
            cx += (w + spacing) * scale


RAMP = " .:-=+*#%@"


def frame_to_text(fb):
    lines = []
    for row in fb:
        line = []
        for r, g, b in row:
            lum = (r * 299 + g * 587 + b * 114) // 1000
            line.append(RAMP[min(lum * (len(RAMP) - 1) // 255, len(RAMP) - 1)])
        lines.append("".join(line))
    return "\n".join(lines)


def make_screen_fn(args):
    if args.screen == "weather":
        return lambda d, f: render.draw_weather(d, W, H, args.code, "%dC" % args.temp, f)
    if args.screen == "clock":
        return lambda d, f: render.draw_clock(d, W, H, "21", "%02d" % (f % 60), f % 2 == 0)
    if args.screen == "hilo":
        return lambda d, f: render.draw_hilo(d, W, H, "%d" % args.hi, "%d" % args.lo)
    if args.screen == "co2":
        return lambda d, f: render.draw_co2(d, W, H, args.ppm)
    if args.screen == "message":
        return lambda d, f: render.draw_message(d, W, H, args.message)
    raise SystemExit("unknown screen: %s" % args.screen)


def render_frame(fn, frame):
    d = SimGraphics(W, H)
    render.clear(d, W, H)
    fn(d, frame)
    return d.fb


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=["play", "print"], default="play",
                    help="play: animate in terminal; print: plain ASCII frames "
                         "to stdout (no escape codes)")
    ap.add_argument("--screen", default="weather",
                    choices=["weather", "clock", "hilo", "co2", "message"])
    ap.add_argument("--code", type=int, default=61, help="WMO weather code (weather screen)")
    ap.add_argument("--temp", type=int, default=21, help="current temperature C")
    ap.add_argument("--hi", type=int, default=25)
    ap.add_argument("--lo", type=int, default=18)
    ap.add_argument("--ppm", type=int, default=812, help="CO2 ppm (co2 screen)")
    ap.add_argument("--message", default="no weather")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.15, help="seconds per frame in play mode")
    ap.add_argument("--gif", default=None,
                    help="also write an animated GIF here (needs Pillow); "
                         "generate on demand for PRs, never commit it")
    ap.add_argument("--scale", type=int, default=8, help="GIF pixel scale")
    args = ap.parse_args()

    fn = make_screen_fn(args)
    frames = [render_frame(fn, f) for f in range(args.frames)]

    if args.gif:
        from gif import write_gif
        write_gif(frames, args.gif, scale=args.scale,
                  delay_ms=int(args.delay * 1000))
        print("wrote gif: %s" % args.gif)
    if args.mode == "print":
        for i, fb in enumerate(frames):
            print("# frame %d" % i)
            print(frame_to_text(fb))
    else:
        for fb in frames:
            sys.stdout.write("\033[H\033[J" + frame_to_text(fb) + "\n")
            sys.stdout.flush()
            time.sleep(args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
