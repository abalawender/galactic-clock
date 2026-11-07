"""Unit tests for the display: property checks on rendered bitmaps plus golden
ASCII dumps, and a mocked full run of the real main.py.

Run: python3 -m unittest discover -s tests -v
Host-only (uses sim/, not the board). Weather values are canned samples.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "sim"))

import render  # noqa: E402
import run_main  # noqa: E402
import sim as simmod  # noqa: E402

W, H = 53, 11


def frame(draw, f=0):
    d = simmod.SimGraphics(W, H)
    render.clear(d, W, H)
    draw(d, f)
    return d.fb


def ascii_of(fb):
    return simmod.frame_to_text(fb)


def lit_span(fb):
    xs = [x for x in range(W) for y in range(H) if fb[y][x] != (0, 0, 0)]
    return min(xs), max(xs)


def margins(fb):
    lo, hi = lit_span(fb)
    return lo, W - 1 - hi


def precip_cols(code, match, frames=8):
    """Per-column sequence of the topmost precipitation row below the cloud,
    one entry per frame (streaks are 2 px tall; only the leading edge moves)."""
    cols = {}
    for f in range(frames):
        fb = frame(lambda d, f: render.draw_icon(d, code, f), f)
        for x in range(W):
            ys = [y for y in range(7, H) if match(fb[y][x])]
            if ys:
                cols.setdefault(x, []).append(min(ys))
    return cols


def assert_falling(testcase, cols, rows=4, allowed=(1,)):
    """Every per-frame step must be in `allowed` (mod rows) — never negative,
    i.e. never upwards — and the column must advance overall."""
    testcase.assertTrue(cols, "no precipitation pixels found")
    for x, seq in cols.items():
        testcase.assertGreaterEqual(len(seq), rows)
        steps = [(seq[(i + 1) % len(seq)] - seq[i]) % rows
                 for i in range(len(seq))]
        for step in steps:
            testcase.assertIn(step, allowed,
                              "col %d moved up: %s" % (x, seq))
        testcase.assertTrue(any(s > 0 for s in steps),
                            "col %d never advances: %s" % (x, seq))


class TestFontContract(unittest.TestCase):
    """SimGraphics.measure_text must match the board's bitmap6 metrics."""

    def test_widths(self):
        d = simmod.SimGraphics(W, H)
        self.assertEqual(d.measure_text("25C", 1), 14)   # 4+1+5+1+4... font6 widths
        self.assertEqual(d.measure_text("00", 1), 11)    # 5+1+5
        self.assertEqual(d.measure_text("1", 1), 2)
        self.assertEqual(d.measure_text("", 1), 0)


class TestPrecipitation(unittest.TestCase):
    def test_rain_falls_down(self):
        cols = precip_cols(61, lambda p: p[2] > 150 and p[0] < 150)
        assert_falling(self, cols)

    def test_snow_falls_down(self):
        # snow falls at half speed (frame//2): steps of 0 or +1, never up
        cols = precip_cols(71, lambda p: p[0] > 200 and p[1] > 200 and p[2] > 200)
        assert_falling(self, cols, allowed=(0, 1))

    def test_rain_columns_staggered(self):
        # columns must not share one phase (the old lockstep bug)
        cols = precip_cols(61, lambda p: p[2] > 150 and p[0] < 150)
        firsts = {seq[0] for seq in cols.values()}
        self.assertGreater(len(firsts), 1)


class TestLayout(unittest.TestCase):
    def test_weather_group_centered(self):
        fb = frame(lambda d, f: render.draw_weather(d, W, H, 0, "21C", f))
        lo, hi = margins(fb)
        self.assertLessEqual(abs(lo - hi), 1, "weather group off-center: %s" % ((lo, hi),))

    def test_hilo_centered_and_snug(self):
        fb = frame(lambda d, f: render.draw_hilo(d, W, H, "25", "18"))
        lo, hi = margins(fb)
        self.assertEqual(lo, hi, "hi/lo pair off-center: %s" % ((lo, hi),))
        # recompute the hi group start the way draw_hilo does; the column
        # between arrow and digits must be empty (1 px gap)
        d = simmod.SimGraphics(W, H)
        gw_hi = 3 + 1 + d.measure_text("25", 1)
        gw_lo = 3 + 1 + d.measure_text("18", 1)
        x = (W - (gw_hi + 6 + gw_lo)) // 2
        self.assertTrue(all(fb[y][x + 3] == (0, 0, 0) for y in range(H)),
                        "gap between arrow and digits is not 1px")

    def test_clock_centered_and_blink(self):
        on = frame(lambda d, f: render.draw_clock(d, W, H, "21", "07", True))
        off = frame(lambda d, f: render.draw_clock(d, W, H, "21", "07", False))
        self.assertNotEqual(ascii_of(on), ascii_of(off), "colon blink has no effect")
        lo, hi = margins(on)
        self.assertEqual(lo, hi, "clock off-center: %s" % ((lo, hi),))


# Golden ASCII dumps — exact rendered output. Update deliberately when the
# layout intentionally changes.
GOLDEN_WEATHER_RAIN_F0 = (
    '                                                     \n'
    '               +++  @@                               \n'
    '              ++++@@@@@                              \n'
    '              +++@@@@@@@   @@@  @@  @@@              \n'
    '               +@@@=@@@@      @  @ @                 \n'
    '                @@@@=@@@    @@   @ @                 \n'
    '                 @@@@@@    @     @ @                 \n'
    '                =          @@@@  @  @@@              \n'
    '                = =                                  \n'
    '                  = =                                \n'
    '                    = =                              '
)
GOLDEN_HILO = (
    '                                                     \n'
    '                                                     \n'
    '                                                     \n'
    '            =  ===  ====          ==  ====           \n'
    '           ===    = =         ===  = =   =           \n'
    '                ==  ===        =   =  ===            \n'
    '               =       =           = =   =           \n'
    '               ==== ===            =  ===            \n'
    '                                                     \n'
    '                                                     \n'
    '                                                     '
)
GOLDEN_CO2 = (
    '                                                     \n'
    '                                                     \n'
    '                                                     \n'
    '           ***  **** ***       **** ** ***           \n'
    '          *    *   *    *     *   *  *    *          \n'
    '          *    *   *  **       ***   *  **           \n'
    '          *    *   * *        *   *  * *             \n'
    '           ***  ***  ****      ***   * ****          \n'
    '                                                     \n'
    '                                                     \n'
    '                                                     '
)
GOLDEN_CLOCK = (
    '                                                     \n'
    '                                                     \n'
    '                                                     \n'
    '                ***  **    **** *****                \n'
    '                   *  * * *   * *   *                \n'
    '                 **   *   *   *     *                \n'
    '                *     *   *   *    *                 \n'
    '                ****  * *  ***    *                  \n'
    '                                                     \n'
    '                                                     \n'
    '                                                     '
)


class TestGolden(unittest.TestCase):
    def test_weather_rain_frame0(self):
        fb = frame(lambda d, f: render.draw_weather(d, W, H, 61, "21C", f), 0)
        self.assertEqual(ascii_of(fb), GOLDEN_WEATHER_RAIN_F0)

    def test_hilo(self):
        fb = frame(lambda d, f: render.draw_hilo(d, W, H, "25", "18"))
        self.assertEqual(ascii_of(fb), GOLDEN_HILO)

    def test_clock_blink_on(self):
        fb = frame(lambda d, f: render.draw_clock(d, W, H, "21", "07", True))
        self.assertEqual(ascii_of(fb), GOLDEN_CLOCK)

    def test_co2(self):
        fb = frame(lambda d, f: render.draw_co2(d, W, H, 812))
        self.assertEqual(ascii_of(fb), GOLDEN_CO2)


class TestCO2(unittest.TestCase):
    """SCD41 CO2 screen: centered, color encodes indoor air quality."""

    def test_co2_centered(self):
        fb = frame(lambda d, f: render.draw_co2(d, W, H, 812))
        lo, hi = margins(fb)
        self.assertEqual(lo, hi, "co2 off-center: %s" % ((lo, hi),))

    def test_co2_color_buckets(self):
        for ppm, want in ((700, render.CO2_OK), (900, render.CO2_WARN),
                          (1300, render.CO2_BAD)):
            fb = frame(lambda d, f: render.draw_co2(d, W, H, ppm))
            lit = {p for row in fb for p in row if p != (0, 0, 0)}
            self.assertEqual(lit, {want}, "ppm %d -> %s, want %s"
                             % (ppm, lit, want))


class TestTZ(unittest.TestCase):
    """src/tz.py: EU DST rule for Europe/* zones; UTC otherwise. Expected
    boundary epochs come from CPython's calendar (independent of tz.py)."""

    def test_eu_dst_2026(self):
        import calendar
        import tz
        start = calendar.timegm((2026, 3, 29, 1, 0, 0))   # last Sun of Mar 01:00 UTC
        end = calendar.timegm((2026, 10, 25, 1, 0, 0))     # last Sun of Oct 01:00 UTC
        self.assertEqual(tz.utc_offset("Europe/Warsaw", start - 1), 3600)
        self.assertEqual(tz.utc_offset("Europe/Warsaw", start), 7200)
        self.assertEqual(tz.utc_offset("Europe/Warsaw", end - 1), 7200)
        self.assertEqual(tz.utc_offset("Europe/Warsaw", end), 3600)

    def test_eu_dst_2027(self):
        import calendar
        import tz
        start = calendar.timegm((2027, 3, 28, 1, 0, 0))
        end = calendar.timegm((2027, 10, 31, 1, 0, 0))
        self.assertEqual(tz.utc_offset("Europe/Warsaw", start), 7200)
        self.assertEqual(tz.utc_offset("Europe/Warsaw", end), 3600)

    def test_midwinter_midsummer(self):
        import calendar
        import tz
        self.assertEqual(tz.utc_offset("Europe/Warsaw",
                                       calendar.timegm((2026, 1, 15, 12, 0, 0))), 3600)
        self.assertEqual(tz.utc_offset("Europe/Warsaw",
                                       calendar.timegm((2026, 7, 15, 12, 0, 0))), 7200)

    def test_non_europe_is_utc(self):
        import tz
        self.assertEqual(tz.utc_offset("America/New_York", 1793972928), 0)
        self.assertEqual(tz.utc_offset("mock", 1793972928), 0)


class TestBeforeAfter(unittest.TestCase):
    """sim/before_after.py: icon contact sheet + vertical stacking."""

    def test_icons_entries_shared_with_sim(self):
        import sim as simmod
        import before_after
        self.assertIs(before_after.ICON_ENTRIES, simmod.ICON_ENTRIES)
        self.assertIs(before_after.render_icons, simmod.render_icons)
        self.assertEqual(len(before_after.ICON_ENTRIES), 12)  # 10 day + 2 night

    def test_icons_grid_shape_and_animation(self):
        import before_after
        frames = before_after.render_icons(render, before_after.ICON_ENTRIES, 4)
        self.assertEqual(len(frames), 4)
        self.assertEqual(len(frames[0]), 3 * 11)     # 3 rows of 11 px cells
        self.assertEqual(len(frames[0][0]), 4 * 11)  # 4 cols of 11 px cells
        self.assertNotEqual(frames[0], frames[1])    # icons animate

    def test_stack_infers_dims(self):
        import before_after
        a = before_after.render_icons(render, before_after.ICON_ENTRIES[:4], 2)
        stacked, w, h = before_after.stack(a, a)
        self.assertEqual((w, h), (4 * 11, 11))
        self.assertEqual(len(stacked[0]), 2 * 11 + 1)  # + 1 px separator row

    def test_identical_screen_writes_no_gifs(self):
        # pixel-identical before/after must produce no GIFs at all, so the
        # CI upload / PR comment skips the unchanged screen entirely
        import os
        import tempfile
        import before_after
        frames = before_after.render_icons(render, before_after.ICON_ENTRIES[:4], 2)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "pr")
            msg = before_after.write_screen_gifs(out, "icons", frames, frames,
                                                 "base", 4, 100)
            self.assertIn("pixel-identical", msg)
            self.assertEqual(os.listdir(td), [])  # nothing written at all


class TestDemoGif(unittest.TestCase):
    """docs/demo-rotation.gif must match what the current code renders — CI on
    push to micropython enforces this via sim/check_demo_gif.py; this test runs
    the same comparison locally (needs Pillow, skipped without it)."""

    def setUp(self):
        try:
            from PIL import Image  # noqa: F401 — also catches a broken native install
        except ImportError:
            self.skipTest("Pillow not available")

    def test_demo_gif_matches_code(self):
        import check_demo_gif
        self.assertEqual(check_demo_gif.check(), [])


class TestRunMainMocked(unittest.TestCase):
    """The real main.py under full mocks (hardware/internet/time stubbed)."""

    def test_current_rotation_runs(self):
        frames = run_main.run_current(16.0)
        self.assertGreater(len(frames), 60)  # ~5s clock + 5s weather + 5s hilo
        self.assertTrue(any(p != (0, 0, 0) for row in frames[0] for p in row),
                        "first frame is blank")

    def test_rotation_shows_all_screens(self):
        frames = run_main.run_current(16.0)
        has_rain = any(p[2] > 150 and p[0] < 150
                       for fb in frames for row in fb for p in row)
        has_hi_arrow = any(p[0] > 200 and p[1] < 150 and p[2] < 120
                           for fb in frames for row in fb for p in row)
        self.assertTrue(has_rain, "weather screen never appeared")
        self.assertTrue(has_hi_arrow, "hi/lo screen never appeared")

    def test_ref_version_runs_self_consistent(self):
        # HEAD has its own src/render.py; run_at must load it, not the working tree's
        frames = run_main.run_at("HEAD", 6.0)
        self.assertIsNotNone(frames)
        self.assertGreater(len(frames), 20)

    def test_rotation_includes_co2(self):
        # the mocked SCD41 must make the co2 screen appear in the rotation
        frames = run_main.run_screen_current("draw_co2", 25.0)
        self.assertTrue(frames, "co2 screen never appeared in the rotation")

    def test_scd41_altitude_configured(self):
        run_main.run_current(2.0)
        self.assertEqual(run_main.FakeSCD41.last.altitude_m, 470)


if __name__ == "__main__":
    unittest.main()
