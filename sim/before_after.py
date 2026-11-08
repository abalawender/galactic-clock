#!/usr/bin/env python3
"""Record before/after GIFs of display screens: a git ref vs the current tree.

"before" loads src/render.py from --ref via `git show` and drives the same
SCREENS table as the current tree — src/render.py is the stable seam across
refactors. Screens the base ref cannot render are skipped with a note instead
of failing, so this keeps working when screens change significantly. For refs
without src/render.py, per-screen before is skipped, but the "rotation"
pseudo-screen still compares by running that ref's real main.py fully mocked
(sim/run_main.py).

The weather screen is special: its animation phase comes from main.py's frame
argument (on the board int(time.time()*3) with int seconds), not from
render.py alone — so both sides are captured by running each side's real
main.py mocked (run_main.run_screen_*) and recording every draw_weather call.
Driving render.py with synthetic 0..n frames would hide device-only bugs.

    python3 sim/before_after.py --ref main --out /tmp/pr
    # writes /tmp/pr_<screen>_{after,before,compare}.gif  (before/compare only
    # when the base ref can render that screen)

Screens live in SCREENS below; each entry maps a name to a draw_* call and a
frame count. The special "icons" screen is a contact sheet of every weather
icon (WMO code x day/night) in one animated GIF — the quickest way to eyeball
icon changes. Weather values are samples — the sim never reads secrets.py.

Screens whose "before" is pixel-identical to "after" (unchanged by the PR)
produce no GIFs at all, so the CI upload and the PR comment skip them
entirely — the review only shows what actually changed.
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


def _clock(d, R, f):
    R.draw_clock(d, W, H, "21", "07", (f * 200) % 1000 < 500)


def _hilo(d, R, f):
    R.draw_hilo(d, W, H, "25", "18")


def _co2(d, R, f):
    R.draw_co2(d, W, H, 812)


def _boot(d, R, f):
    # the whole loading sequence: boot/wifi/ntp/weather, 4 frames per stage
    R.draw_boot(d, W, H, simmod.BOOT_STAGES[min(f // 4, len(simmod.BOOT_STAGES) - 1)], f)


SCREENS = {"clock": (_clock, 30), "hilo": (_hilo, 1), "co2": (_co2, 1),
           "boot": (_boot, 16)}

# Weather goes through the real main loop on both sides (see module docstring).
WEATHER_FUNC = "draw_weather"
WEATHER_FRAMES = 16
WEATHER_SECONDS = 9.0  # loop shows 5s clock first, then weather at 0.15s/frame

# "icons" contact sheet: (WMO code, is_day) entries — all day kinds plus the
# two night variants. Drawn with each side's own render.py, so the compare GIF
# shows old vs new icons for every kind in one animation. The entries and the
# grid renderer live in sim.py, shared with `sim.py --screen icons`.
ICON_ENTRIES = simmod.ICON_ENTRIES
ICON_FRAMES = 8
render_icons = simmod.render_icons


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
    """Vertically stack two frame lists (dims inferred from the frames)."""
    h, w = len(a[0]), len(a[0][0])
    n = max(len(a), len(b))
    black = [[(0, 0, 0)] * w for _ in range(h)]
    sep = [[(30, 30, 30)] * w]
    frames = [(a[i] if i < len(a) else black) + sep +
              (b[i] if i < len(b) else black) for i in range(n)]
    return frames, w, h


def write_screen_gifs(out, screen, after, before, ref, scale, delay_ms):
    """Write the review GIFs for one screen; return a status line for the log.

    before=None     -> after-only (the base ref cannot render this screen)
    before==after   -> write nothing: an unchanged screen would only add
                       duplicate GIFs to the PR review, so no files are
                       produced and the CI upload/comment skips it entirely
    otherwise       -> after + before + compare (stacked, labelled)
    """
    if before is not None and len(before) == len(after) and before == after:
        return ("%s: %d frames, pixel-identical to %s — skipped, no GIFs"
                % (screen, len(after), ref))
    write_gif(after, "%s_%s_after.gif" % (out, screen),
              scale=scale, delay_ms=delay_ms)
    if before is None:
        return "%s: after-only (%d frames)" % (screen, len(after))
    write_gif(before, "%s_%s_before.gif" % (out, screen),
              scale=scale, delay_ms=delay_ms)
    stacked, cw, ch = stack(before, after)
    labels = [(4, 4, "before @ %s" % ref),
              (4, (ch + 1) * scale + 4, "after @ HEAD")]
    write_gif(stacked, "%s_%s_compare.gif" % (out, screen),
              scale=scale, delay_ms=delay_ms, texts=labels)
    return ("%s: compared %d vs %d frames, pixel-identical=False"
            % (screen, len(before), len(after)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="main", help="git ref for the 'before' side")
    ap.add_argument("--screens",
                    default="weather,icons," + ",".join(SCREENS) + ",rotation",
                    help="comma-separated subset of: weather,icons,%s,rotation"
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
            before = None
            try:
                before = run_main.run_at(args.ref, ROTATION_SECONDS)
            except Exception as e:
                print("rotation: before failed at %s (%s) — after-only"
                      % (args.ref, e))
            if before is not None:
                m = min(len(before), len(after))
                before, after = before[:m], after[:m]
            print(write_screen_gifs(args.out, "rotation", after, before,
                                    args.ref, args.scale, delay_ms))
            continue
        before = None
        if screen == "weather":
            after = (run_main.run_screen_current(WEATHER_FUNC, WEATHER_SECONDS)
                     or [])[:WEATHER_FRAMES]
            try:
                before = (run_main.run_screen_at(args.ref, WEATHER_FUNC,
                                                 WEATHER_SECONDS)
                          or [])[:WEATHER_FRAMES] or None
            except Exception as e:
                print("weather: before unavailable at %s (%s) — after-only"
                      % (args.ref, e))
        elif screen == "icons":
            after = render_icons(render, ICON_ENTRIES, ICON_FRAMES)
            before = None
            if R_base is not None:
                try:
                    before = render_icons(R_base, ICON_ENTRIES, ICON_FRAMES)
                except Exception as e:
                    print("icons: before unavailable at %s (%s) — after-only"
                          % (args.ref, e))
        elif screen in SCREENS:
            n = SCREENS[screen][1]
            after = render_frames(render, screen, n)
            if R_base is not None:
                try:
                    before = render_frames(R_base, screen, n)
                except Exception as e:
                    print("%s: before unavailable at %s (%s) — after-only"
                          % (screen, args.ref, e))
        else:
            raise SystemExit("unknown screen: %s (have: weather,icons,%s,rotation)"
                             % (screen, ",".join(SCREENS)))
        print(write_screen_gifs(args.out, screen, after, before,
                                args.ref, args.scale, delay_ms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
