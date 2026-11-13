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
class TestAnimations(unittest.TestCase):
    """Full-matrix digital-rain fun slot: the matrix code rain."""

    # -- matrix rain -------------------------------------------------------

    def _heads(self, frames):
        """(col -> list of head y per frame) for draw_matrix; None = in gap.
        The head is the brightest pixel of the column (alpha fades upward
        behind it, so the argmax is the head row)."""
        out = {}
        for f in frames:
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            for x in range(W):
                ls = [fb[y][x][1] for y in range(H)]  # g channel dominates
                ys = [y for y in range(H) if ls[y]]
                out.setdefault(x, []).append(
                    max(ys, key=lambda y: ls[y]) if ys else None)
        return out

    def test_matrix_is_green_rain(self):
        fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), 7)
        lit = {p for row in fb for p in row if p != (0, 0, 0)}
        self.assertTrue(lit, "matrix rain drew nothing")
        for (r, g, b) in lit:
            # pale bright heads, green trails: green always dominates
            self.assertLess(r, g, "rain pixel not green: %s" % ((r, g, b),))
            self.assertLess(b, g, "rain pixel not green: %s" % ((r, g, b),))

    def test_matrix_is_subpixel_smooth(self):
        # anti-aliasing: a head must not be a full-brightness dot teleporting
        # row to row — the drop's fractional position must show up as partial
        # brightness on two adjacent rows (the transition), and tier phases
        # must advance a non-integer number of rows per tick
        mid = 26  # a column with tier (2, 3, ...)
        prof = []
        for f in range(3):
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            prof.append([fb[y][mid][1] for y in range(H)])
        # the head pixel must sometimes sit between two rows: some frame has
        # its max pixel less than the per-tier max alpha (partial head)
        heads = [max(p) for p in prof if max(p)]
        self.assertTrue(any(h < 250 for h in heads),
                        "heads never anti-aliased: %s" % (heads,))
        self.assertEqual(render.MATRIX_TIERS[0][0:2], (1, 3))  # slow < 1 row/tick

    def test_matrix_tiers_differ_in_speed_and_brightness(self):
        # every tier must actually be configured, with visibly different
        # speeds (1, 2, 4 rows per 3 ticks) and strictly increasing brightness
        self.assertEqual(len(render.MATRIX_TIERS), 3)
        for (rows, per, bright) in render.MATRIX_TIERS:
            self.assertEqual(per, 3)  # denominator 3 -> phases don't step
        self.assertEqual([t[0] for t in render.MATRIX_TIERS], [1, 2, 4])
        lums = [(255 * t[2]) // 100 for t in render.MATRIX_TIERS]
        self.assertEqual(lums, sorted(lums), "tiers not dark -> bright")

    def _runs(self, col_heads):
        """col -> list of runs, each a list of (frame, head y) with the head
        continuously visible; a top respawn (upward jump > 2) starts a new
        run so wrap deltas never mask downward motion."""
        out = {}
        for x, seq in col_heads.items():
            out_runs, cur = [], []
            for i, y in enumerate(seq):
                if y is None or (cur and y < cur[-1][1] - 2):
                    if cur:
                        out_runs.append(cur)
                    cur = [] if y is None else [(i, y)]
                else:
                    cur.append((i, y))
            if cur:
                out_runs.append(cur)
            out[x] = out_runs
        return out

    def test_matrix_falls_down_at_constant_column_speed(self):
        runs = self._runs(self._heads(range(30)))
        self.assertTrue(runs, "no heads found at all")
        for x, col_runs in runs.items():
            for run in col_runs:
                for (i0, y0), (i1, y1) in zip(run, run[1:]):
                    dy = y1 - y0
                    self.assertGreaterEqual(dy, 0, "col %d moved up" % x)
                    self.assertLessEqual(dy, 2, "col %d jumped %d rows" % (x, dy))

    def test_matrix_speeds_vary_between_columns(self):
        # exact speeds from the exposed subpixel state: the three tiers move
        # 1, 2, 4 rows per 3 ticks (mod the wrap), all of them present
        speeds = set()
        for x in range(W):
            rows = render.MATRIX_TIERS[render._tier_of(x)][0]
            c0, _, _ = render.matrix_col(x, H, 100)
            c3, _, _ = render.matrix_col(x, H, 103)
            adv = (c3 - c0) % ((H + 4 + (x * 3) % 6) * render.SUB)
            self.assertEqual(adv, (rows * 3 * render.SUB)
                             // render.MATRIX_TIERS[render._tier_of(x)][1]
                             % ((H + 4 + (x * 3) % 6) * render.SUB),
                             "col %d advances %s per 3 ticks" % (x, adv))
            speeds.add(rows)
        self.assertEqual(speeds, {1, 2, 4},
                         "columns do not cover all three tier speeds")

    def test_matrix_motion_is_subpixel_continuous(self):
        # every tier's per-tick phase increment is NOT a whole row (no exact
        # row-multiples), so anti-aliased heads glide instead of teleporting
        for x in range(W):
            for f in range(6):
                c0, _, _ = render.matrix_col(x, H, f)
                c1, _, _ = render.matrix_col(x, H, f + 1)
                step = (c1 - c0) % ((H + 4 + (x * 3) % 6) * render.SUB)
                self.assertNotEqual(step % render.SUB, 0,
                                    "col %d steps a whole row at f=%d" % (x, f))

    def test_matrix_columns_are_staggered(self):
        seqs = self._heads(range(3))
        first_y = {seq[0] for seq in seqs.values() if seq[0] is not None}
        self.assertGreater(len(first_y), 1, "all heads share one phase")

    def test_matrix_covers_the_board(self):
        cols = set()
        for f in range(24):
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            for x in range(W):
                if any(fb[y][x] != (0, 0, 0) for y in range(H)):
                    cols.add(x)
        self.assertEqual(cols, set(range(W)), "matrix rain misses columns")

    # -- rotation integration ----------------------------------------------
    # The rain is user-toggled by button A's IRQ handler (main.py); presses
    # are injected at virtual epochs relative to the mocked NTP sync.

    def _with_presses(self, offsets, draw_func, seconds):
        press_at = tuple(run_main.SYNCED_EPOCH + off for off in offsets)
        run_main.FakePin.press_at = press_at
        try:
            return run_main.run_screen_current(draw_func, seconds)
        finally:
            run_main.FakePin.press_at = ()

    def test_matrix_hidden_until_button_pressed(self):
        shots = self._with_presses((), "draw_matrix", 26.0)
        self.assertFalse(shots, "matrix rain played with no button press")

    def test_matrix_plays_when_button_pressed(self):
        # a press mid-rotation takes over at the next slot boundary
        shots = self._with_presses((21.0,), "draw_matrix", 50.0)
        self.assertTrue(shots, "button press never started the rain")

    def test_second_press_stops_rain_and_rotation_resumes(self):
        # press at 21 s (rain on), press again at 27 s (rain off): only a
        # short burst of rain, then the clock returns for full slots
        rain = self._with_presses((21.0, 27.0), "draw_matrix", 60.0)
        clocks = self._with_presses((21.0, 27.0), "draw_clock", 60.0)
        self.assertTrue(rain, "the first press never started the rain")
        self.assertGreater(len(clocks), 26,
                           "rotation never resumed after the second press")

    def test_rain_timebox_returns_to_rotation(self):
        # one press at 21 s: rain until 141 s, then the rotation rotates on
        # (two or more clock fills become visible over the run)
        rain = self._with_presses((21.0,), "draw_matrix", 180.0)
        clocks = self._with_presses((21.0,), "draw_clock", 180.0)
        self.assertTrue(rain, "the press never started the rain")
        self.assertGreater(len(clocks), 26,
                           "rotation never resumed after the rain timebox")


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


GOLDEN_BOOT_WIFI_F0 = (
    '                                                     \n'
    '                                                     \n'
    '                                                     \n'
    '          * * * ***  *** ***                         \n'
    '   ***    * * *  *  *     *                          \n'
    '   **@    * * *  *  *     *                          \n'
    '   ***    * * *  *  ****  *                          \n'
    '          ** *  *** *    ***                         \n'
    '                                                     \n'
    '                                                     \n'
    '                                                     '
)


class TestBoot(unittest.TestCase):
    """Boot/loading screen: spinner + stage label, animated per frame."""

    def test_boot_golden(self):
        fb = frame(lambda d, f: render.draw_boot(d, W, H, "wifi", 0), 0)
        self.assertEqual(ascii_of(fb), GOLDEN_BOOT_WIFI_F0)

    def test_boot_spinner_animates(self):
        a = frame(lambda d, f: render.draw_boot(d, W, H, "wifi", f), 0)
        b = frame(lambda d, f: render.draw_boot(d, W, H, "wifi", f), 1)
        self.assertNotEqual(ascii_of(a), ascii_of(b))

    def test_boot_stages_cycle(self):
        # the PR boot GIF walks the real stages: boot/wifi/ntp/weather
        import sim as simmod
        self.assertEqual(simmod.BOOT_STAGES, ("boot", "wifi", "ntp", "weather"))
        a = frame(lambda d, f: render.draw_boot(d, W, H, simmod.BOOT_STAGES[0], 0), 0)
        b = frame(lambda d, f: render.draw_boot(d, W, H, simmod.BOOT_STAGES[3], 0), 0)
        self.assertNotEqual(ascii_of(a), ascii_of(b), "stage label has no effect")


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

    def test_co2_alarm_beeps_when_high_and_lit(self):
        run_main.CANNED_CO2 = 1500
        run_main.CANNED_LIGHT = 100.0
        run_main.FakeChannel.beeps = 0
        try:
            run_main.run_current(22.0)
        finally:
            run_main.CANNED_CO2 = 812
            run_main.CANNED_LIGHT = 2048.0
        self.assertGreater(run_main.FakeChannel.beeps, 0, "no alarm beep")

    def test_co2_alarm_silent_in_the_dark(self):
        # dark room established at ALS < 20 -> no alarm at 0 or 19
        for light in (0.0, 19.0):
            run_main.CANNED_CO2 = 1500
            run_main.CANNED_LIGHT = light
            run_main.FakeChannel.beeps = 0
            try:
                run_main.run_current(22.0)
            finally:
                run_main.CANNED_CO2 = 812
                run_main.CANNED_LIGHT = 2048.0
            self.assertEqual(run_main.FakeChannel.beeps, 0,
                             "alarm beeped at ALS=%s (dark)" % light)

    def test_co2_alarm_threshold_boundary(self):
        # ALS = 20 (ALS_ALARM_MIN) must beep, 19 must not
        for light, want_beeps in ((20.0, True), (19.0, False)):
            run_main.CANNED_CO2 = 1500
            run_main.CANNED_LIGHT = light
            run_main.FakeChannel.beeps = 0
            try:
                run_main.run_current(22.0)
            finally:
                run_main.CANNED_CO2 = 812
                run_main.CANNED_LIGHT = 2048.0
            self.assertEqual(run_main.FakeChannel.beeps > 0, want_beeps,
                             "ALS=%s beeps=%s want %s"
                             % (light, run_main.FakeChannel.beeps, want_beeps))

    def test_co2_alarm_silent_when_low(self):
        run_main.CANNED_CO2 = 800
        run_main.CANNED_LIGHT = 100.0
        run_main.FakeChannel.beeps = 0
        try:
            run_main.run_current(22.0)
        finally:
            run_main.CANNED_CO2 = 812
            run_main.CANNED_LIGHT = 2048.0
        self.assertEqual(run_main.FakeChannel.beeps, 0)

    def test_co2_alarm_threshold_is_red_level(self):
        # the audible alarm must fire exactly at the ppm level that turns
        # the CO2 font red (render.CO2_RED_PPM)
        for ppm, want_beeps in ((render.CO2_RED_PPM, True),
                                (render.CO2_RED_PPM - 1, False)):
            run_main.CANNED_CO2 = ppm
            run_main.CANNED_LIGHT = 100.0
            run_main.FakeChannel.beeps = 0
            try:
                run_main.run_current(22.0)
            finally:
                run_main.CANNED_CO2 = 812
                run_main.CANNED_LIGHT = 2048.0
            self.assertEqual(run_main.FakeChannel.beeps > 0, want_beeps,
                             "ppm=%s beeps=%s want %s"
                             % (ppm, run_main.FakeChannel.beeps, want_beeps))

    def test_run_main_wrappers_preserve_signatures(self):
        # before_after.render_icons detects day/night via inspect.signature;
        # run_main's wrappers must not hide is_day (regression: after-side
        # icons lost the moon when weather/rotation ran before icons)
        import inspect
        run_main.run_current(1.0)
        self.assertIn("is_day", inspect.signature(render.draw_icon).parameters)
        self.assertIn("is_day", inspect.signature(render.draw_weather).parameters)

    def test_boot_animation_drawn_at_startup(self):
        # with wifi+weather mocked OK, draw_boot is only used for the
        # boot/loading stages — it must fire within the first seconds
        frames = run_main.run_screen_current("draw_boot", 3.0)
        self.assertTrue(frames, "no boot animation drawn at startup")
        self.assertGreater(len(frames), 1, "boot animation is not animated")

    def test_sys_values_logged_over_uart(self):
        # read_sys() values must appear as a UART log line once per rotation
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_main.run_current(22.0)  # one full rotation is 20s
        out = buf.getvalue()
        self.assertIn("sys: light=2048/4095", out)  # canned gu.light()
        self.assertIn("temp=24.18C", out)            # canned ADC(4) = 14117
        # VSYS is measured once at boot with the radio off (ADC(29) canned)
        self.assertIn("sys: vsys=4.99V (radio off)", out)

    def test_clock_shown_when_ntp_synced(self):
        # default mock: wifi ok -> NTP syncs the RTC to 2026 -> clock appears
        clocks = run_main.run_screen_current("draw_clock", 10.0)
        self.assertTrue(clocks, "clock screen never appeared after NTP sync")

    def test_clock_hidden_when_rtc_unsynced_and_before_2026(self):
        # wifi down (no NTP) and the RTC still at its 2023 boot epoch: the
        # clock must not be shown — its slot shows a message instead
        run_main.WIFI_OK = False
        try:
            clocks = run_main.run_screen_current("draw_clock", 26.0)
            msgs = run_main.run_screen_current("draw_message", 26.0)
        finally:
            run_main.WIFI_OK = True
        self.assertFalse(clocks,
                         "clock shown although RTC is 2023 and never NTP-synced")
        self.assertTrue(msgs, "no message shown in the clock slot")

    def test_clock_shown_when_rtc_already_2026_without_ntp(self):
        # a soft reset keeps the RTC running: no NTP this boot, but the RTC
        # already reads >= 2026 -> the clock may be shown
        run_main.WIFI_OK = False
        run_main.BOOT_EPOCH = run_main.SYNCED_EPOCH  # RTC kept at 2026
        try:
            clocks = run_main.run_screen_current("draw_clock", 26.0)
        finally:
            run_main.WIFI_OK = True
            run_main.BOOT_EPOCH = 1700000000.0
        self.assertTrue(clocks, "clock hidden although RTC reads >= 2026")

    def test_wifi_retried_after_boot_failure(self):
        # wifi failed at boot: connect_wifi must be retried from the loop
        # (WIFI_RETRY_S apart), and the loop must stay alive meanwhile
        run_main.WIFI_OK = False
        run_main.FakeWLAN.connect_calls = 0
        try:
            # 130s: 20s boot timeout + two 20s rotations + one 20s retry
            frames = run_main.run_current(130.0)
        finally:
            run_main.WIFI_OK = True
        self.assertGreaterEqual(run_main.FakeWLAN.connect_calls, 2,
                                "wifi was not retried after the boot failure")
        self.assertGreater(len(frames), 30, "loop died while retrying wifi")

    def test_wifi_failure_does_not_kill_loop(self):
        # wifi down: the loop must survive (show "no wifi"/"no weather")
        # instead of raising out of main()
        run_main.WIFI_OK = False
        try:
            # 26s: the 20s wifi timeout plus a few seconds of the main loop
            frames = run_main.run_current(26.0)
            msgs = run_main.run_screen_current("draw_message", 26.0)
        finally:
            run_main.WIFI_OK = True
        self.assertGreater(len(frames), 30, "loop died after wifi failure")
        self.assertTrue(msgs, "no status message shown after wifi failure")

    def test_scd41_altitude_configured(self):
        run_main.run_current(2.0)
        self.assertEqual(run_main.FakeSCD41.last.altitude_m, 470)


if __name__ == "__main__":
    unittest.main()
