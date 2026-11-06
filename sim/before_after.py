#!/usr/bin/env python3
"""Record before/after GIFs of a screen: old code from a git ref vs current tree.

The "before" side executes the actual main.py from `--ref` with the board
modules (galactic, picographics, secrets, network, time, ...) stubbed out,
capturing every gu.update() frame on a SimGraphics. The "after" side renders
the current src/render.py. Writes <out>_before.gif, <out>_after.gif and a
stacked <out>_compare.gif (before on top, after below).

    python3 sim/before_after.py --ref 25a412a --screen clock --seconds 6 --out frames/clock
    python3 sim/before_after.py --ref 25a412a --screen weather --code 61 --temp 21 \
        --frames 16 --out frames/rain
"""
import argparse
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import render  # noqa: E402
import sim as simmod  # noqa: E402
from gif import write_gif  # noqa: E402

W, H = 53, 11


def load_old_main(ref):
    """Exec main.py from git ref `ref` with stubbed board modules."""
    src = subprocess.run(["git", "show", "%s:main.py" % ref], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    state = {"t": 1700000000.0, "ms": 0}

    fake_time = types.ModuleType("time")
    fake_time.time = lambda: state["t"]
    fake_time.ticks_ms = lambda: state["ms"]

    def _sleep(s):
        state["t"] += s
        state["ms"] += int(s * 1000)

    fake_time.sleep = _sleep
    fake_time.localtime = lambda: (2024, 11, 5, 21, 7, 0, 1, 309, 0)

    class FakeGu:
        WIDTH, HEIGHT = W, H

        def __init__(self):
            self.frames = []

        def update(self, d):
            self.frames.append([row[:] for row in d.fb])

        def clear(self):
            pass

    galactic = types.ModuleType("galactic")
    galactic.GalacticUnicorn = FakeGu
    picographics = types.ModuleType("picographics")
    picographics.DISPLAY_GALACTIC_UNICORN = 0
    picographics.PicoGraphics = lambda display=0: simmod.SimGraphics(W, H)
    secrets = types.ModuleType("secrets")
    for k in ("LOCATION_LAT", "LOCATION_LON", "TZ", "WIFI_PASSWORD", "WIFI_SSID"):
        setattr(secrets, k, "")
    stubs = {"time": fake_time, "galactic": galactic,
             "picographics": picographics, "secrets": secrets,
             "network": types.ModuleType("network"),
             "ntptime": types.ModuleType("ntptime"),
             "urequests": types.ModuleType("urequests"),
             "ujson": types.ModuleType("ujson")}
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        g = {"__name__": "old_main"}
        exec(compile(src, "main.py@%s" % ref, "exec"), g)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return g


def old_frames(g, screen, args):
    if screen == "clock":
        g["show_clock"](args.seconds)
    else:
        wx = {"current": {"temperature_2m": float(args.temp),
                          "weather_code": args.code}}
        g["show_weather"](wx, args.frames * 0.15)
    return g["gu"].frames


def new_frames(screen, args):
    if screen == "clock":
        n = int(args.seconds / 0.2)
        return [simmod.render_frame(
            lambda d, f: render.draw_clock(d, W, H, "21", "07",
                                           (f * 200) % 1000 < 500), f)
            for f in range(n)]
    return [simmod.render_frame(
        lambda d, f: render.draw_weather(d, W, H, args.code, "%dC" % args.temp, f), f)
        for f in range(args.frames)]


def stack(a, b):
    n = max(len(a), len(b))
    black = [[(0, 0, 0)] * W for _ in range(H)]
    sep = [[(30, 30, 30)] * W]
    return [(a[i] if i < len(a) else black) + sep +
            (b[i] if i < len(b) else black) for i in range(n)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="25a412a", help="git ref for the 'before' code")
    ap.add_argument("--screen", choices=["clock", "weather"], default="clock")
    ap.add_argument("--code", type=int, default=61, help="WMO code (weather screen)")
    ap.add_argument("--temp", type=int, default=21)
    ap.add_argument("--seconds", type=float, default=6.0, help="clock: simulated seconds")
    ap.add_argument("--frames", type=int, default=16, help="weather: frame count")
    ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.2)
    ap.add_argument("--out", required=True, help="output prefix, e.g. frames/clock")
    args = ap.parse_args()

    g = load_old_main(args.ref)
    before = old_frames(g, args.screen, args)
    after = new_frames(args.screen, args)

    outdir = os.path.dirname(args.out)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    delay_ms = int(args.delay * 1000)
    write_gif(before, args.out + "_before.gif", scale=args.scale, delay_ms=delay_ms)
    write_gif(after, args.out + "_after.gif", scale=args.scale, delay_ms=delay_ms)
    labels = [(4, 4, "before @ %s" % args.ref),
              (4, (H + 1) * args.scale + 4, "after @ HEAD")]
    write_gif(stack(before, after), args.out + "_compare.gif",
              scale=args.scale, delay_ms=delay_ms, texts=labels)
    print("before frames: %d, after frames: %d" % (len(before), len(after)))
    print("wrote %s_{before,after,compare}.gif" % args.out)
    if len(before) == len(after):
        print("before == after pixel-identical:", before == after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
