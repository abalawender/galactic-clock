#!/usr/bin/env python3
"""Record before/after GIFs of display screens: a git ref vs the current tree.

"before" loads src/render.py from --ref via `git show` and drives the same
SCREENS table as the current tree — src/render.py is the stable seam across
refactors. Screens the base ref cannot render are skipped with a note instead
of failing, so this keeps working when screens change significantly. For refs
without src/render.py, per-screen before is skipped, but the "rotation"
pseudo-screen still compares by running that ref's real main.py fully mocked
(sim/run_main.py).

    python3 sim/before_after.py --ref main --out /tmp/pr
    # writes /tmp/pr_<screen>_{after,before,compare}.gif  (before/compare only
    # when the base ref can render that screen)

Screens live in SCREENS below; each entry maps a name to a draw_* call and a
frame count. Weather values are samples — the sim never reads secrets.py.
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

import render  # noqa: E402  (current tree)
import run_main  # noqa: E402
import sim as simmod  # noqa: E402
from gif import write_gif  # noqa: E402

W, H = 53, 11

ROTATION_SECONDS = 18.0  # virtual seconds of the real main loop for "rotation"


def _weather(d, R, f):
    R.draw_weather(d, W, H, 61, "21C", f)


def _clock(d, R, f):
    R.draw_clock(d, W, H, "21", "07", (f * 200) % 1000 < 500)


def _hilo(d, R, f):
    R.draw_hilo(d, W, H, "25", "18")


SCREENS = {"weather": (_weather, 16), "clock": (_clock, 30), "hilo": (_hilo, 1)}


def render_frames(R, screen, n):
    fn = SCREENS[screen][0]
    out = []
    for f in range(n):
        d = simmod.SimGraphics(W, H)
        R.clear(d, W, H)
        fn(d, R, f)
        out.append(d.fb)
    return out


def load_render_at(ref):
    """The src/render.py module as of git ref, or None if it did not exist."""
    r = subprocess.run(["git", "show", "%s:src/render.py" % ref], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    mod = types.ModuleType("render_at_%s" % ref[:7])
    exec(compile(r.stdout, "render.py@%s" % ref, "exec"), mod.__dict__)
    return mod


def stack(a, b):
    n = max(len(a), len(b))
    black = [[(0, 0, 0)] * W for _ in range(H)]
    sep = [[(30, 30, 30)] * W]
    return [(a[i] if i < len(a) else black) + sep +
            (b[i] if i < len(b) else black) for i in range(n)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="main", help="git ref for the 'before' side")
    ap.add_argument("--screens", default=",".join(SCREENS) + ",rotation",
                    help="comma-separated subset of: %s,rotation"
                         % ",".join(SCREENS))
    ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.2)
    ap.add_argument("--out", required=True, help="output prefix, e.g. /tmp/pr")
    args = ap.parse_args()

    outdir = os.path.dirname(args.out)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    delay_ms = int(args.delay * 1000)

    R_base = load_render_at(args.ref)
    if R_base is None:
        print("note: no src/render.py at %s — per-screen before skipped; "
              "rotation (mocked main.py) still compares" % args.ref)

    for screen in args.screens.split(","):
        if screen == "rotation":
            # whole main-loop run with hardware/internet/time mocked — robust
            # to any screen changes, since nothing app-level is hard-coded
            after = run_main.run_current(ROTATION_SECONDS)
            write_gif(after, "%s_rotation_after.gif" % args.out,
                      scale=args.scale, delay_ms=delay_ms)
            before = None
            try:
                before = run_main.run_at(args.ref, ROTATION_SECONDS)
            except Exception as e:
                print("rotation: before failed at %s (%s) — after-only"
                      % (args.ref, e))
            if before is not None:
                m = min(len(before), len(after))
                before = before[:m]
                write_gif(before, "%s_rotation_before.gif" % args.out,
                          scale=args.scale, delay_ms=delay_ms)
                labels = [(4, 4, "before @ %s" % args.ref),
                          (4, (H + 1) * args.scale + 4, "after @ HEAD")]
                write_gif(stack(before, after[:m]),
                          "%s_rotation_compare.gif" % args.out,
                          scale=args.scale, delay_ms=delay_ms, texts=labels)
                print("rotation: compared %d vs %d frames, pixel-identical=%s"
                      % (m, len(after), before == after[:m]))
            else:
                print("rotation: after-only (%d frames)" % len(after))
            continue
        if screen not in SCREENS:
            raise SystemExit("unknown screen: %s (have: %s,rotation)"
                             % (screen, ",".join(SCREENS)))
        n = SCREENS[screen][1]
        after = render_frames(render, screen, n)
        write_gif(after, "%s_%s_after.gif" % (args.out, screen),
                  scale=args.scale, delay_ms=delay_ms)
        before = None
        if R_base is not None:
            try:
                before = render_frames(R_base, screen, n)
            except Exception as e:
                print("%s: before unavailable at %s (%s) — after-only"
                      % (screen, args.ref, e))
        if before is not None:
            write_gif(before, "%s_%s_before.gif" % (args.out, screen),
                      scale=args.scale, delay_ms=delay_ms)
            labels = [(4, 4, "before @ %s" % args.ref),
                      (4, (H + 1) * args.scale + 4, "after @ HEAD")]
            write_gif(stack(before, after),
                      "%s_%s_compare.gif" % (args.out, screen),
                      scale=args.scale, delay_ms=delay_ms, texts=labels)
            same = (len(before) == len(after) and before == after)
            print("%s: compared %d vs %d frames, pixel-identical=%s"
                  % (screen, len(before), len(after), same))
        else:
            print("%s: after-only (%d frames)" % (screen, len(after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
