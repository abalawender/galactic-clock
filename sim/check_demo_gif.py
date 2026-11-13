#!/usr/bin/env python3
"""Verify that docs/demo-rotation.gif matches what the current code renders.

Regenerates the demo frames from the working tree with the exact parameters of
the README regenerate command — keep DEMO_* below in sync with:

    python3 sim/run_main.py --seconds 18 --delay 0.12 --gif docs/demo-rotation.gif

— then compares them with the committed GIF: frame count, size, per-frame
duration, and decoded pixels. Pixels are compared after decoding (not raw
bytes) so the check is stable across Pillow versions. Exits 1 with a
regenerate hint on any mismatch.

Run in CI on push to micropython (.github/workflows/micropython-check.yml);
locally: python3 sim/check_demo_gif.py   (needs Pillow)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import render  # noqa: E402
import run_main  # noqa: E402
from gif import fb_to_image  # noqa: E402

# keep in sync with the README regenerate command (scale is run_main's default)
DEMO_GIF = os.path.join(REPO, "docs", "demo-rotation.gif")
DEMO_SECONDS = 24.0  # must span a full ~20 s rotation (no matrix slot in it)
DEMO_DELAY_MS = 120
DEMO_SCALE = 8
W, H = 53, 11


def gif_frames(path):
    """[(rgb_bytes, (w, h), duration_ms)] for every frame of a GIF."""
    from PIL import Image
    img = Image.open(path)
    out = []
    try:
        while True:
            out.append((img.convert("RGB").tobytes(), img.size,
                        img.info.get("duration")))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    return out


def compare(frames, gif_path, scale, delay_ms):
    """frames: list of framebuffers from run_main. Returns a list of mismatch
    descriptions — empty means the GIF is exactly what the code renders.

    The comparison is timeline-based, not frame-list-based: Pillow merges
    identical consecutive GIF frames into one longer frame, so each stored
    frame is expanded back onto the code's fixed `delay_ms` grid before
    comparing. That keeps the check stable across Pillow versions (whether or
    not they merge) while still catching stale pixels, count, size, or tempo.
    """
    expected = [(fb_to_image(fb, scale).tobytes(), (W * scale, H * scale))
                for fb in frames]
    if not os.path.exists(gif_path):
        return ["%s does not exist" % gif_path]
    got = gif_frames(gif_path)
    problems = []
    expanded = []
    for i, (px, size, dur) in enumerate(got):
        if not dur or dur % delay_ms:
            problems.append("frame %d duration %s ms is not a multiple of the"
                            " %d ms frame step" % (i, dur, delay_ms))
            n = 1
        else:
            n = dur // delay_ms
        expanded.extend([(px, size)] * n)
    if len(expanded) != len(expected):
        problems.append("frame count: gif shows %d, code renders %d"
                        % (len(expanded), len(expected)))
    for i, (g, e) in enumerate(zip(expanded, expected)):
        if g[1] != e[1]:
            problems.append("frame %d size: gif %s, code renders %s" % (i, g[1], e[1]))
        elif g[0] != e[0]:
            problems.append("frame %d pixels differ" % i)
    return problems


def check(gif_path=DEMO_GIF, seconds=DEMO_SECONDS, scale=DEMO_SCALE,
          delay_ms=DEMO_DELAY_MS):
    """Render the demos with the current code and compare against the GIFs."""
    problems = compare(run_main.run_current(seconds), gif_path, scale, delay_ms)
    problems += compare_matrix_gif()
    return problems


# Keep in sync with the README matrix regenerate command below.
MATRIX_GIF = os.path.join(REPO, "docs", "demo-matrix.gif")
MATRIX_FRAMES = 60
MATRIX_DELAY_MS = 30  # GIF preview grid for the 1/30 s board tick (GIF
                      # durations only store centiseconds, so 33.3 ms is not
                      # representable; the frame CONTENT is tick-independent)
MATRIX_SCALE = 8


def matrix_frames():
    """The exact frames the tracked docs/demo-matrix.gif must contain."""
    import sim as simmod  # noqa: E402  (run_main import above set up sys.path)
    out = []
    for f in range(MATRIX_FRAMES):
        d = simmod.SimGraphics(W, H)
        render.clear(d, W, H)
        render.draw_matrix(d, W, H, f)
        out.append(d.fb)
    return out


def compare_matrix_gif():
    """docs/demo-matrix.gif check: frame count, size, tempo, pixels. Matrix
    frames always differ from each other (the rain never stops), so a
    straightforward one-to-one comparison needs no delay expansion."""

    if not os.path.exists(MATRIX_GIF):
        return ["%s does not exist" % MATRIX_GIF]
    got = gif_frames(MATRIX_GIF)
    expected = [(fb_to_image(fb, MATRIX_SCALE).tobytes(),
                 (W * MATRIX_SCALE, H * MATRIX_SCALE))
                for fb in matrix_frames()]
    problems = []
    if len(got) != len(expected):
        problems.append("matrix gif: %d frames, code renders %d"
                        % (len(got), len(expected)))
    for i, ((px, size, dur), (epx, esize)) in enumerate(zip(got, expected)):
        if size != esize:
            problems.append("matrix gif frame %d size %s" % (i, (size, esize)))
        elif px != epx:
            problems.append("matrix gif frame %d pixels differ" % i)
    return problems


def main():
    problems = check()
    if problems:
        print("FAIL: tracked demo gifs do not match the current code:")
        for p in problems[:10]:
            print("  - %s" % p)
        print("regenerate with: python3 sim/run_main.py --seconds %g"
              " --delay %g --gif docs/demo-rotation.gif"
              % (DEMO_SECONDS, DEMO_DELAY_MS / 1000.0))
        print("            and: python3 sim/sim.py play --screen matrix"
              " --frames %d --delay %g --gif docs/demo-matrix.gif"
              % (MATRIX_FRAMES, MATRIX_DELAY_MS / 1000.0))
        return 1
    print("OK: docs/demo-rotation.gif + docs/demo-matrix.gif match the"
          " current code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
