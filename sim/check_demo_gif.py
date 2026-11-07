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

import run_main  # noqa: E402
from gif import fb_to_image  # noqa: E402

# keep in sync with the README regenerate command (scale is run_main's default)
DEMO_GIF = os.path.join(REPO, "docs", "demo-rotation.gif")
DEMO_SECONDS = 18.0
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
    """Render the demo with the current code and compare against the GIF."""
    return compare(run_main.run_current(seconds), gif_path, scale, delay_ms)


def main():
    problems = check()
    if problems:
        print("FAIL: docs/demo-rotation.gif does not match the current code:")
        for p in problems[:10]:
            print("  - %s" % p)
        print("regenerate with: python3 sim/run_main.py --seconds %g"
              " --delay %g --gif docs/demo-rotation.gif"
              % (DEMO_SECONDS, DEMO_DELAY_MS / 1000.0))
        return 1
    print("OK: docs/demo-rotation.gif matches the current code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
