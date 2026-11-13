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
        lit = set()
        strong = 0
        for f in range(40):
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            for p, _x in ((p, x) for row in fb for x, p in enumerate(row)
                          if p != (0, 0, 0)):
                lit.add(p)
        self.assertTrue(lit, "matrix rain drew nothing")
        for (r, g, b) in lit:
            # every tint in MATRIX_TINTS is green-dominant once the fade
            # multiplies all channels by the same alpha; near-black dust
            # pixels round to equal channels, so threshold the dominance
            self.assertLessEqual(r, g, "rain pixel not green: %s" % ((r, g, b),))
            self.assertLessEqual(b, g, "rain pixel not green: %s" % ((r, g, b),))
            if g > 200 and g - max(r, b) > 30:
                strong += 1
        self.assertGreater(strong, 0, "no strongly green rain pixels")

    def test_matrix_head_churns_hue_then_settles(self):
        # the down-most pixel of a drop cycles through several tints while it
        # travels the first half of its pass, then keeps one tint (tint_at);
        # each pass settles on its own (LCG-mixed) hue
        x = 5
        gap = 4 + (x * 3) % 6
        settle = ((H + gap) * render.SUB) // 2
        pass_hues = []          # settled hue of each pass seen
        cur = set()
        for f in range(2100):
            c16, L16, bright, seed_v = render.matrix_col(x, H, f)
            if c16 < settle:
                continue
            cur.add(render.tint_at(seed_v, c16, settle))
            nxt, _, _, _ = render.matrix_col(x, H, f + 1)
            if nxt < settle:    # head wrapped to the next pass
                pass_hues.append(cur)
                cur = set()
        self.assertTrue(pass_hues, "no settled stretch observed")
        for settled in pass_hues:
            self.assertEqual(len(settled), 1,
                             "head never settles on one hue: %s" % settled)
        self.assertGreater(len({h for s in pass_hues for h in s}), 1,
                           "every pass settles on the same hue")

    def test_matrix_tints_are_all_green_dominant(self):
        for (r, g, b) in render.MATRIX_TINTS:
            self.assertLess(r, g, "tint not green: %s" % ((r, g, b),))
            self.assertLess(b, g, "tint not green: %s" % ((r, g, b),))

    def test_matrix_is_subpixel_smooth(self):
        # a head must not be a full-brightness dot teleporting row to row:
        # the drop's fractional position must show up as partial brightness,
        # i.e. the column's peak brightness varies over time (the exact
        # non-stepping guarantee is asserted on the model in
        # test_matrix_motion_is_subpixel_continuous / tiers)
        mid = next(x for x in range(W)
                   if render.MATRIX_TIERS[render._tier_of(x)][0] == 4)
        peaks = []
        for f in range(400):
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            p = [fb[y][mid][1] for y in range(H)]
            if max(p):
                peaks.append(max(p))
                if len(peaks) >= 8 and len(set(peaks)) > 1:
                    break
        self.assertGreaterEqual(len(peaks), 8, "col %d never lit" % mid)
        self.assertGreater(len(set(peaks)), 1,
                           "head brightness never varies (no subpixel"
                           " partials): %s" % (sorted(set(peaks)),))

    def test_matrix_tiers_differ_in_speed_and_brightness(self):
        # every tier must actually be configured, with visibly different
        # speeds (none a whole number of rows per tick) and strictly
        # increasing brightness
        self.assertEqual(len(render.MATRIX_TIERS), 5)
        for (rows, per, bright) in render.MATRIX_TIERS:
            self.assertIn(per, (2, 4, 6, 8, 12))
            # the per-tick subpixel step must not be a whole row (stepped)
            self.assertNotEqual((rows * render.SUB // per) % render.SUB, 0,
                                "tier %s steps whole rows" % ((rows, per),))
        self.assertEqual([t[0] for t in render.MATRIX_TIERS], [1, 1, 1, 4, 1])
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
        # exact speeds from the exposed subpixel state: the five tiers move
        # 1, 1, 1, 4, 1 rows per 12, 6, 4, 12, 2 ticks (mod the wrap), all present
        speeds = set()
        for x in range(W):
            tier = render._tier_of(x)
            rows, per, _ = render.MATRIX_TIERS[tier]
            loop = (H + render._gap_of(x)) * render.SUB
            f0 = 100
            c0, *_ = render.matrix_col(x, H, f0)
            c3, *_ = render.matrix_col(x, H, f0 + 3)
            adv = (c3 - c0) % loop
            self.assertEqual(adv,
                             ((rows * render.SUB * (f0 + 3)) // per
                              - (rows * render.SUB * f0) // per) % loop,
                             "col %d advances %s per 3 ticks" % (x, adv))
            speeds.add(rows)
        self.assertEqual(speeds, {1, 4},
                         "columns do not cover all tier speeds")

    def test_matrix_motion_is_subpixel_continuous(self):
        # every tier's per-tick phase increment is NOT a whole row (no exact
        # row-multiples), so anti-aliased heads glide instead of teleporting
        for x in range(W):
            for f in range(6):
                c0, *_ = render.matrix_col(x, H, f)
                c1, *_ = render.matrix_col(x, H, f + 1)
                step = (c1 - c0) % ((H + render._gap_of(x)) * render.SUB)
                self.assertNotEqual(step % render.SUB, 0,
                                    "col %d steps a whole row at f=%d" % (x, f))

    def test_matrix_columns_are_staggered(self):
        seqs = self._heads(range(3))
        first_y = {seq[0] for seq in seqs.values() if seq[0] is not None}
        self.assertGreater(len(first_y), 1, "all heads share one phase")

    def test_matrix_covers_the_board(self):
        # window spans several loops per tier: slow crawl columns sit dark in
        # their gap for over a hundred frames, and ~1 pass in 10 rests whole
        cols = set()
        for f in range(400):
            fb = frame(lambda d, f: render.draw_matrix(d, W, H, f), f)
            for x in set(range(W)) - cols:
                if any(fb[y][x] != (0, 0, 0) for y in range(H)):
                    cols.add(x)
            if len(cols) == W:
                break
        self.assertEqual(cols, set(range(W)), "matrix rain misses columns")

    def test_matrix_rest_passes_breathe_density(self):
        # ~1 pass in 10 rests: some column is dark (matrix_col L16 == 0) at
        # most times — but never the whole board, and rests eventually end
        frames_with_rests = 0
        for f in range(600):
            resting = sum(1 for x in range(W)
                          if render.matrix_col(x, H, f)[1] == 0)
            frames_with_rests += (resting > 0)
            self.assertLess(resting, W,
                            "every column rests at once at f=%d" % f)
            if len({render.matrix_col(x, H, f)[1] == 0
                    for x in range(W)}) > 1:
                break
        self.assertGreater(frames_with_rests, 0, "no resting pass ever seen")

    def test_matrix_most_drops_stay_classic_green(self):
        # ~4 passes in 5 keep the classic rain green (seed 0, which never
        # churns); only the rest cycle the accent tints and settle on their
        # own accent. Count at pass boundaries (head position wraps).
        base = accents = 0
        for x in range(0, W, 2):                # every other column
            prev_c16 = render.matrix_col(x, H, 0)[0]
            for f in range(1, 2200):
                c16, L16, _, seed = render.matrix_col(x, H, f)
                if c16 < prev_c16:              # wrapped -> new pass
                    base += (seed == 0)
                    accents += (0 < seed <= render.N_ACCENT)
                # update every frame: skipping resting passes (L16 == 0)
                # leaves a stale prev and misreads every frame after the
                # wrap as a new pass
                prev_c16 = c16
        self.assertGreater(base / max(1, accents), 2.0,
                           "accent passes are not a minority "
                           "(base %d, accents %d)" % (base, accents))
        for s in range(1, render.N_ACCENT + 1):
            self.assertEqual(render.tint_at(s, 10 ** 9, 1000), s,
                             "accent heads must settle on their own tint")
        self.assertEqual(render.tint_at(0, 12345, 100), 0,
                         "classic-green passes must never churn")

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

    def test_press_takes_over_the_rotation_immediately(self):
        # a press mid-clock-slot ends the screen within a frame and the
        # rain starts — the rest of that rotation (weather/hilo/co2) never
        # plays; per-frame deadline polls in the show loops (rain_pending)
        late = self._with_presses((21.0,), "draw_weather", 45.0)
        early = self._with_presses((), "draw_weather", 45.0)
        self.assertTrue(early, "control run: no weather screens at all")
        self.assertLess(len(late or []), len(early) - 10,
                        "the press did not cancel the rotation's remaining "
                        "screens immediately (%d vs %d)" % (len(late or []),
                                                            len(early)))

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

    def test_rain_runs_at_30_frames_per_virtual_second(self):
        # the rain loop paces to 30 fps (1/30 s frame deadline in
        # maybe_show_rain); the mocked sleeps advance virtual time 33.3 ms
        # per frame. Rain starts at the slot boundary after the press (≤5 s
        # later) and runs to the end of the ~39 s window: at 30 fps that is
        # 1020+ frames; the old 50 ms tick would have produced < 800.
        rain = self._with_presses((21.0,), "draw_matrix", 60.0)
        self.assertTrue(rain, "the press never started the rain")
        self.assertGreater(len(rain), 30 * 30,
                           "rain is not running at ~30 fps: %d frames in"
                           " ~35 virtual s of rain" % len(rain))

    # -- rain-clock overlay --------------------------------------------------
    # With a trusted RTC, rain mode pours the rain over the clock
    # (render.draw_rain_clock); with the RTC untrusted it runs alone.

    def test_rain_mode_shows_the_clock_over_the_rain(self):
        # default mock: NTP synced -> RTC trusted -> the clock overlays
        shots = self._with_presses((21.0,), "draw_rain_clock", 60.0)
        self.assertTrue(shots, "rain mode never showed the clock overlay")

    def test_rain_mode_without_rtc_runs_bare_rain(self):
        # wifi down (no NTP) and the RTC still at its 2023 boot epoch: the
        # rain runs alone rather than show a wrong time (same rule as the
        # rotation's clock-hiding). Presses must be keyed to the boot epoch —
        # without NTP the mock's clock never reaches SYNCED_EPOCH.
        run_main.WIFI_OK = False
        run_main.FakePin.press_at = (run_main.BOOT_EPOCH + 21.0,)
        try:
            overlay = run_main.run_screen_current("draw_rain_clock", 60.0)
            bare = run_main.run_screen_current("draw_matrix", 60.0)
        finally:
            run_main.WIFI_OK = True
            run_main.FakePin.press_at = ()
        self.assertFalse(overlay, "clock overlay shown although RTC is 2023")
        self.assertTrue(bare, "no rain at all without a trusted RTC")

    def test_rain_clock_dims_rain_behind_bright_digits(self):
        # inside the clock's padded text box the rain is dimmed to
        # MATRIX_DIM % alpha, so no rain pixel reads brighter than the
        # (255,255,255) digits; outside the box it stays full brightness
        sim = simmod.SimGraphics(W, H)
        colon_adv = 3
        tw = sim.measure_text("23", 1) + colon_adv + sim.measure_text("59", 1)
        x0 = max(0, (W - tw) // 2 - 1)
        x1 = min(W, x0 + tw + 2)
        y0, y1 = 1, min(H, render.TEXT_Y + 7)
        digits = brightest_outside = 0
        for f in range(0, 60, 3):
            fb = frame(lambda d, ff: render.draw_rain_clock(
                d, W, H, "23", "59", False, ff), f)
            for y in range(H):
                for x in range(W):
                    r, g, b = fb[y][x]
                    if (r, g, b) == render.WHITE:
                        if x0 <= x < x1 and y0 <= y < y1:
                            digits += 1
                    elif g > 120:  # a rain pixel brighter than the dim cap
                        if x0 <= x < x1 and y0 <= y < y1:
                            self.fail("undimmed rain pixel %s behind the "
                                      "clock box at (%d,%d)" % ((r, g, b), x, y))
                        brightest_outside += 1
        self.assertGreater(digits, 0, "no bright digits in the clock box")
        self.assertGreater(brightest_outside, 0,
                           "no full-brightness rain outside the clock box")

    def test_dim_mask_dims_the_whole_field(self):
        mask = bytearray(W * H)
        for x in range(W):
            for j in range(H):
                mask[x * H + j] = render.MATRIX_FADE_STEPS  # fully dimmed
        produced_rain = False
        for f in range(0, 90, 5):
            dim_fb = frame(lambda d, ff: render.draw_matrix(
                d, W, H, ff, dim_mask=mask), f)
            full_fb = frame(lambda d, ff: render.draw_matrix(d, W, H, ff), f)
            for row in dim_fb:
                for (r, g, b) in row:
                    self.assertLessEqual(max(r, g, b), 120,
                                         "masked rain pixel not dimmed")
            if any(p[1] > 200 for row in full_fb for p in row):
                produced_rain = True
        self.assertTrue(produced_rain, "control run: no bright rain at all")

    def test_fade_dither_sweeps_the_box(self):
        # the ramp is a Bayer-ordered dither: level 1 dims only the pixels
        # under the 0 threshold, level 4 dims every box pixel — and every
        # pixel dimmed at a level stays dimmed at all higher levels
        saw_leak = saw_partial = full = False
        for f in range(0, 90, 9):
            for level in range(1, render.MATRIX_FADE_STEPS + 1):
                mask = bytearray(W * H)
                for x in range(W):
                    for j in range(H):
                        mask[x * H + j] = level
                fb = frame(lambda d, ff: render.draw_matrix(
                    d, W, H, ff, dim_mask=mask), f)
                bright_in_box = sum(
                    1 for y in range(H) for x in range(W)
                    if fb[y][x][1] > 120)
                if level == render.MATRIX_FADE_STEPS:
                    self.assertEqual(
                        bright_in_box, 0,
                        "level %d left bright pixels: dither never "
                        "completes" % level)
                    full = True
                elif bright_in_box:
                    saw_partial = True
                else:
                    saw_leak = True   # a low level that fully dims too soon
        self.assertTrue(saw_partial,
                        "no intermediate level leaves rain visible — the "
                        "dither has no effect")
        self.assertFalse(saw_leak,
                         "an intermediate level fully dims the field")
        self.assertTrue(full, "the full-level never fully dimmed")

    def test_rain_clock_fades_in_and_out(self):
        # fade phases the overlay: 0 = bare rain (no digits, identical
        # in-box rain to plain draw_matrix), stepping up dims the in-box
        # rain monotonically until the full overlay
        sim = simmod.SimGraphics(W, H)
        colon_adv = 3
        tw = sim.measure_text("23", 1) + colon_adv + sim.measure_text("59", 1)
        x0 = max(0, (W - tw) // 2 - 1)
        x1 = min(W, x0 + tw + 2)
        y0, y1 = 1, min(H, render.TEXT_Y + 7)
        maxdim = {f: 0 for f in range(render.MATRIX_FADE_STEPS + 1)}
        for f in range(0, 120, 7):
            for fade in range(render.MATRIX_FADE_STEPS + 1):
                fb = frame(lambda d, ff: render.draw_rain_clock(
                    d, W, H, "23", "59", False, ff, fade=fade), f)
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        r, g, b = fb[y][x]
                        if r == g == b:
                            continue    # a digit pixel, not rain
                        maxdim[fade] = max(maxdim[fade], max(r, g, b))
        bare_max = 0
        for f in range(0, 120, 7):
            bare = frame(lambda d, ff: render.draw_matrix(d, W, H, ff), f)
            for y in range(y0, y1):
                bare_max = max(bare_max,
                               max(max(p) for p in bare[y][x0:x1]))
        self.assertEqual(maxdim[0], bare_max,
                         "fade 0 is not bare rain inside the clock box")
        self.assertGreater(maxdim[0], maxdim[render.MATRIX_FADE_STEPS] + 80,
                           "the overlay does not dim the rain behind the "
                           "clock at full strength")
        # monotonic dimming: the in-box rain never brightens as the overlay
        # strengthens
        for fade in range(render.MATRIX_FADE_STEPS):
            self.assertGreaterEqual(maxdim[fade], maxdim[fade + 1],
                                    "in-box rain brightens as the overlay "
                                    "strengthens (fade=%d)" % fade)

    def test_faded_rain_clock_draws_digits_on_the_ramp(self):
        # each fade level draws digit pixels in exactly its ramp shade
        # (255*fade//STEPS), until fade 0 removes them entirely
        for fade in (1, 3, 8):
            dh = 255 * fade // render.MATRIX_FADE_STEPS
            hits = 0
            fb = frame(lambda d, ff: render.draw_rain_clock(
                d, W, H, "23", "59", False, ff, fade=fade), 10)
            for row in fb:
                for px in row:
                    if px == (dh, dh, dh):
                        hits += 1
            self.assertGreater(hits, 0, "no digit pixels at shade %d "
                                        "(fade=%d)" % (dh, fade))
        gone = frame(lambda d, ff: render.draw_rain_clock(
            d, W, H, "23", "59", False, ff, fade=0), 10)
        self.assertNotIn(render.WHITE, (px for row in gone for px in row),
                         "digits visible at fade 0")

    def test_exit_ink_matches_the_real_font(self):
        # the embedded digit glyphs (render._DIGIT_GLYPHS) must be the same
        # shapes Pimoroni's bitmap6 draws — the exit ramps them into drops,
        # and a divergent copy would visibly snap the clock at the
        # conversion boundary. First the raw glyph data, then the ink map's
        # pixel positions against really drawn text.
        for ch in "0123456789":
            mine = {(col, row) for col in range(6) for row in range(6)
                    if render._DIGIT_GLYPHS[ch][col] >> row & 1}
            spec = simmod.font6_data.GLYPHS[ch]
            real = {(col, row) for col in range(6) for row in range(6)
                    if spec[col] >> row & 1}
            self.assertEqual(mine, real, "digit %r bytes diverge from "
                             "font6" % ch)
            self.assertEqual(render._DIGIT_WIDTHS[ord(ch) - 48],
                             simmod.font6_data.WIDTHS[ord(ch) - 32],
                             "digit %r width diverges" % ch)
        # the ink map must land exactly where d.text puts the digits
        d = simmod.SimGraphics(W, H)
        mapped = set(render._clock_ink(d, W, H, "23", "59"))
        mhh = d.measure_text("23", 1)
        base = (W - (mhh + 3 + d.measure_text("59", 1))) // 2
        d.set_pen(d.create_pen(255, 255, 255))
        d.text("23", base, render.TEXT_Y)
        d.text("59", base + mhh + 3, render.TEXT_Y)
        real = {(x, y) for y in range(H) for x in range(W)
                if d.fb[y][x] == render.WHITE}
        self.assertEqual({(x, y) for (x, y, _, _) in mapped}, real,
                         "the ink map does not match the drawn clock")

    def test_rain_clock_exit_pours_then_ink_falls_organically(self):
        # the exit ramp: no dedicated pour phase — from the first step the
        # field pours across the still-bright clock while the ink converts
        # to drops AT STAGGERED STEPS — never all at once — each falling
        # away at its own speed; the last step is
        # pure bare rain (no mid-air cutoff). Crossing drops transiently
        # cover ink pixels, so ink counts are sampled as the max over
        # several frames — the max is the least-obscured count.
        last = frame(lambda d, ff: render.draw_rain_clock(
            d, W, H, "23", "59", False, ff,
            dissolve=render.MATRIX_DISSOLVE_STEPS), 10)
        bare = frame(lambda d, ff: render.draw_matrix(d, W, H, ff), 10)
        self.assertEqual(last, bare,
                         "the dissolved clock did not reduce to bare rain")
        sim = simmod.SimGraphics(W, H)
        ink = render._clock_ink(sim, W, H, "23", "59")
        all_px = {(x, y) for (x, y, s, f) in ink}
        self.assertGreater(len(all_px), 20, "ink map implausibly small")
        max_white = {}
        for step in (1, 2, 3, 4):
            best = 0
            for f in range(0, 90, 7):   # max over sampled frames
                fb = frame(lambda d, ff: render.draw_rain_clock(
                    d, W, H, "23", "59", False, ff, dissolve=step), f)
                n = sum(1 for y in range(H) for x in range(W)
                        if fb[y][x] == render.WHITE)
                best = max(best, n)
            max_white[step] = best
        # immediate conversion, no dedicated pour phase: the very first
        # exit step already shows converted pixels falling (whites below
        # the full ink count), most of the clock still lit — with the
        # coarse 4-step stagger roughly a quarter of the ink converts
        # per step, each wave plainly visible
        self.assertGreater(max_white[1], len(all_px) - 25,
                           "too much ink lost at the start of the exit")
        self.assertLess(max_white[1], len(all_px),
                        "no pixel converted at the first exit step")
        # organic stagger: the conversion waves through steps 1..3, never
        # a single block drop
        self.assertGreater(max_white[1] - max_white[2], 3,
                           "the conversion is not spread over steps")
        self.assertGreater(max_white[2] - max_white[3], 3,
                           "the conversion is not spread over steps")
        # stagger spans convert steps 0..3: past step 4 no ink is left
        self.assertEqual(max_white[4], 0, "ink left after all conversions")
        # and drops fall beside it: bright rain-green outside the ink too?
        fb = frame(lambda d, ff: render.draw_rain_clock(
            d, W, H, "23", "59", False, ff, dissolve=6), 10)
        drops_anywhere = sum(1 for y in range(H) for x in range(W)
                             if fb[y][x][1] > 120 and fb[y][x][0] < fb[y][x][1])
        self.assertGreater(drops_anywhere, 0, "no rain at the exit at all")




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
