"""Pure rendering for the 53x11 Galactic Unicorn weather clock.

Every function draws into `d`, any object implementing the PicoGraphics subset
used here (create_pen, set_pen, pixel, rectangle, text, measure_text), so the
same code runs on the board (main.py, real PicoGraphics) and on the host
(sim/sim.py, SimGraphics). No board imports in this module.

`frame` is a monotonically increasing animation tick (board: int(time*3)).
"""

# --- palette ---------------------------------------------------------------

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
CLOUD = (160, 160, 170)         # back puff
CLOUD_MID = (135, 135, 148)     # texture flecks
CLOUD_SHADE = (105, 105, 120)   # bottom edge
STORM_CLOUD = (125, 125, 140)
STORM_HI = (155, 155, 170)
STORM_MID = (110, 110, 125)
STORM_SHADE = (85, 85, 100)
SUN = (255, 200, 0)
SUN_DIM = (140, 90, 0)          # twinkling ray frame
MOON = (235, 235, 205)
RAIN = (60, 120, 255)
SNOW = (255, 255, 255)
BOLT = (255, 230, 0)
FOG = (150, 150, 165)
HI = (255, 90, 60)
LO = (90, 140, 255)
CLOCK = (120, 200, 255)
MSG = (255, 160, 40)
CO2_WARN_PPM = 800   # at/above this the CO2 font goes amber
CO2_RED_PPM = 1200   # at/above this it goes red — and the audible alarm fires
CO2_OK = (80, 220, 80)
CO2_WARN = (255, 200, 0)
CO2_BAD = (255, 60, 60)

TEXT_Y = 2


def clear(d, w, h):
    d.set_pen(d.create_pen(*BLACK))
    d.rectangle(0, 0, w, h)


def kind_of(code):
    if code in (0, 1):
        return "clear"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code >= 95:
        return "storm"
    if code in (85, 86):
        return "snow"
    if code >= 80:
        return "showers"
    if code == 75:
        return "heavysnow"
    if code >= 71:
        return "snow"
    if code == 65:
        return "heavyrain"
    if code in (51, 53, 55):
        return "drizzle"
    return "rain"


# --- animated weather icon, 10x11 in the left part of the matrix -----------
# Hand-drawn 10x11 pixel icons (tuned visually in the sim), animated per kind:
# twinkling sun rays and stars, shaded cloud underside, drifting fog bands,
# falling rain/snow streaks, flashing bolt.

# Cloud occupies rows 1..6, leaving rows 7..10 for precipitation: FALL_ROWS
# rows of falling drops, staggered per column so they never move in lockstep.
# y = CLOUD_BOTTOM + (frame//speed + phase) % FALL_ROWS increases every tick
# and wraps at the bottom -> drops always fall down and respawn at the top.
CLOUD_BOTTOM = 7
FALL_ROWS = 4  # rows 7..10

# 10-wide cloud as (y, x_from, x_to, color): a darker back puff (CLOUD,
# shifted left, rows 1-3 plus one pixel below at (4,1) to round its bottom —
# a solid contiguous blob, so nothing protrudes) with the pure-white body on
# the right whose left side rises to row 2, plus a white pixel at 1-indexed
# (4,4) that rounds the top-left of the front puff, so the back cloud's left
# side stays visible; interior CLOUD_MID flecks; flat bottom, corners cut.
CLOUD_ROWS = (
    (1, 1, 3, CLOUD),
    (2, 0, 4, CLOUD),
    (3, 0, 2, CLOUD),
    (4, 1, 1, CLOUD),       # rounds the back puff's bottom
    (1, 6, 7, WHITE),
    (2, 4, 8, WHITE),
    (3, 3, 9, WHITE),       # includes the rounding pixel at 1-indexed (4,4)
    (4, 2, 9, WHITE),
    (5, 2, 9, WHITE),
    (6, 3, 8, WHITE),
    (4, 5, 5, CLOUD_MID),   # texture flecks
    (5, 6, 6, CLOUD_MID),
)

# Same two-fluff cloud pushed right/down for partly cloudy (and night
# precipitation), so the sun/moon is tucked *behind* it — drawn first, the
# cloud covers its lower right, which reads as "peeking out".
PARTLY_CLOUD_ROWS = (
    (2, 6, 7, WHITE),
    (3, 4, 9, WHITE),
    (4, 3, 9, WHITE),
    (5, 3, 9, WHITE),
    (6, 4, 8, WHITE),
    (4, 6, 6, CLOUD_MID),
    (5, 5, 5, CLOUD_MID),
)

# 5-wide sun disc (corners cut), symmetric about x=5, rows 3..7; single rays.
SUN_CORE_ROWS = ((3, 4, 6), (4, 3, 7), (5, 3, 7), (6, 3, 7), (7, 4, 6))
SUN_RAYS = ((5, 1), (5, 9), (1, 5), (9, 5), (2, 2), (8, 2), (2, 8), (8, 8))

# Small 3x3 sun peeking out top-left for partly cloudy day.
SMALL_SUN_CORE_ROWS = ((1, 1, 3), (2, 1, 3), (3, 1, 3))
SMALL_SUN_RAYS = ((2, 0), (0, 2), (4, 2))

# Round full moon (clear night) — a clean disc (no bite/knob, not C-shaped)
# plus its stars, which twinkle dim/bright (slow), not on/off.
MOON_PX = ((4, 2), (5, 2), (6, 2),
           (3, 3), (4, 3), (5, 3), (6, 3), (7, 3),
           (3, 4), (4, 4), (5, 4), (6, 4), (7, 4),
           (3, 5), (4, 5), (5, 5), (6, 5), (7, 5),
           (4, 6), (5, 6), (6, 6))
MOON_STARS = ((8, 1), (1, 9))
STAR_DIM = (110, 110, 100)

# Small quarter moon for partly cloudy night / night precipitation, top-left:
# the full disc stays visible (dark half in MOON_DARK, high contrast) with
# the left half plus the other top pixel lit — reads as a quarter moon,
# not a "C".
SMALL_MOON_PX = ((2, 0), (3, 0),
                 (1, 1), (2, 1), (3, 1), (4, 1),
                 (1, 2), (2, 2), (3, 2), (4, 2),
                 (1, 3), (2, 3), (3, 3), (4, 3),
                 (2, 4), (3, 4))
SMALL_MOON_LIT = tuple((x, y) for (x, y) in SMALL_MOON_PX if x <= 2) + ((3, 0),)
MOON_DARK = (55, 55, 52)

# Lightning bolt, rows 7..10, 2-px zigzag (flashes on alternate frames).
BOLT_PX = ((6, 7), (5, 8), (6, 8), (4, 9), (5, 9), (4, 10), (5, 10))


def _rows(d, ox, oy, rows, dx=0, dy=0):
    for (y, xa, xb, col) in rows:
        d.set_pen(d.create_pen(*col))
        d.rectangle(ox + xa + dx, oy + y + dy, xb - xa + 1, 1)


def _cloud(d, ox, oy, dark=False, dy=0):
    # storm cloud: same shape, dark body, darker left bump, light flecks
    tone = {WHITE: STORM_CLOUD, CLOUD: STORM_SHADE, CLOUD_MID: STORM_HI,
            CLOUD_SHADE: STORM_SHADE}
    rows = []
    for (y, xa, xb, col) in CLOUD_ROWS:
        if dark:
            col = tone[col]
        rows.append((y, xa, xb, col))
    _rows(d, ox, oy, rows, dy=dy)


def _sun(d, ox, oy, frame):
    _rows(d, ox, oy, [(y, xa, xb, SUN) for (y, xa, xb) in SUN_CORE_ROWS])
    for i, (x, y) in enumerate(SUN_RAYS):
        # twinkle: alternate rays dim/bright
        d.set_pen(d.create_pen(*(SUN if (i + frame) % 2 == 0 else SUN_DIM)))
        d.pixel(ox + x, oy + y)


def _small_sun(d, ox, oy, frame):
    _rows(d, ox, oy, [(y, xa, xb, SUN) for (y, xa, xb) in SMALL_SUN_CORE_ROWS])
    for i, (x, y) in enumerate(SMALL_SUN_RAYS):
        d.set_pen(d.create_pen(*(SUN if (i + frame) % 2 == 0 else SUN_DIM)))
        d.pixel(ox + x, oy + y)


def _moon(d, ox, oy, frame):
    d.set_pen(d.create_pen(*MOON))
    for (x, y) in MOON_PX:
        d.pixel(ox + x, oy + y)
    for i, (x, y) in enumerate(MOON_STARS):
        # stars twinkle dim/bright at half rate — no hard on/off blink
        d.set_pen(d.create_pen(*(SNOW if (i + frame // 2) % 2 == 0 else STAR_DIM)))
        d.pixel(ox + x, oy + y)


def _small_moon(d, ox, oy):
    for (x, y) in SMALL_MOON_PX:
        col = MOON if (x, y) in SMALL_MOON_LIT else MOON_DARK
        d.set_pen(d.create_pen(*col))
        d.pixel(ox + x, oy + y)


def _fog(d, ox, oy, frame):
    # fog = drifting bands only (no cloud, so it cannot be mistaken for rain);
    # each band is two 4-px segments at staggered heights -> a wavy staircase
    d.set_pen(d.create_pen(*FOG))
    for r, y in enumerate((2, 4, 6, 8)):
        xa = (frame // 2 + r) % 3
        d.rectangle(ox + xa, oy + y, 4, 1)
        d.rectangle(ox + xa + 4, oy + y + 1, 4, 1)


def _fall(d, ox, oy, frame, cols, color, speed=1, streak=1):
    d.set_pen(d.create_pen(*color))
    for i, x in enumerate(cols):
        top = (frame // speed + i) % FALL_ROWS
        for s in range(streak):
            if top + s < FALL_ROWS:  # streak exits at the bottom, then respawns
                d.pixel(ox + x, oy + CLOUD_BOTTOM + top + s)


def draw_icon(d, code, frame, ox=0, oy=0, is_day=1):
    kind = kind_of(code)
    if kind == "clear":
        if is_day:
            _sun(d, ox, oy, frame)
        else:
            _moon(d, ox, oy, frame)
        return
    if kind == "partly":
        # no precipitation rows needed: shift the whole group down so the
        # icon is vertically centered in the 11-row area
        if is_day:
            _small_sun(d, ox, oy + 2, frame)
        else:
            _small_moon(d, ox, oy + 2)
        _rows(d, ox, oy, PARTLY_CLOUD_ROWS, dy=2)
        return
    if kind == "cloud":
        _cloud(d, ox, oy, dy=2)  # no rain: center vertically
        return
    if kind == "fog":
        _fog(d, ox, oy, frame)
        return
    # precipitating kinds: cloud (dark for storm) + animated drops; at night a
    # small moon is tucked behind the cloud and the drops fall under the cloud
    if kind == "storm":
        _cloud(d, ox, oy, dark=True)
        if frame % 2 == 0:
            d.set_pen(d.create_pen(*BOLT))
            for (x, y) in BOLT_PX:
                d.pixel(ox + x, oy + y)
        _fall(d, ox, oy, frame, (2, 8), RAIN, speed=2)
        return
    night = not is_day
    if night:
        _small_moon(d, ox, oy)
        _rows(d, ox, oy, PARTLY_CLOUD_ROWS)
    else:
        _cloud(d, ox, oy)
    if kind == "drizzle":
        _fall(d, ox, oy, frame, (5, 8) if night else (3, 6), RAIN, speed=2)
    elif kind == "heavyrain":
        _fall(d, ox, oy, frame, (2, 4, 6, 8) if night else (1, 3, 5, 7, 9),
              RAIN, streak=2)
    elif kind == "showers":
        if frame % 6 < 4:  # intermittent
            _fall(d, ox, oy, frame, (4, 6, 8) if night else (2, 5, 8),
                  RAIN, streak=2)
    elif kind == "heavysnow":
        _fall(d, ox, oy, frame, (3, 5, 7, 9) if night else (1, 3, 5, 7, 9),
              SNOW, speed=2)
    elif kind == "snow":
        _fall(d, ox, oy, frame, (4, 6, 8) if night else (2, 4, 6, 8), SNOW, speed=2)
    else:  # rain
        _fall(d, ox, oy, frame, (4, 6, 8) if night else (2, 4, 6, 8), RAIN,
              streak=2)


# --- animation mode: matrix rain --------------------------------------------
# Full-matrix digital-rain fun screen. Same contract as the weather icons: no
# time, no randomness — everything derives from the `frame` tick, so sim and
# board stay identical.

SUB = 16  # subpixel steps per row (fixed-point position)

# Head-hue palette the falling head pixel cycles through. Tint 0 is the
# classic rain green — kept saturated rather than whitish so the field reads
# unmistakably green (~4 passes in 5, shimmering between the base tint and a
# subtle neighbor and settling back). The other passes cycle the subtle
# accent tints (compressed teal-ish and chartreuse-ish drifts, green channel
# pinned at 255, red/blue pulled down toward green) and settle on their
# assigned one. Still reads as green rain at a glance, just greener.
MATRIX_TINTS = (
    (170, 255, 130),
    (150, 255, 150),
    (128, 255, 170),
    (198, 255, 100),
    (218, 255, 88),
)
N_ACCENT = 4                   # tints 1..N_ACCENT are the accent hues
MATRIX_CHURN_SUB = SUB // 4    # one hue step per quarter-row of travel:
                               # the head pixel cycles tints several times
                               # per row it drops (fast shimmer)
# tier = (rows, per, brightness %). Every tier's phase advances a
# non-integer number of rows per tick (per never divides rows*SUB), so
# anti-aliased heads glide instead of stepping. Brightness grows with
# speed: fast reads near, slow reads far. At the 1/30 s tick these are
# ~3.75 / 5 / 7.5 / 10 / 15 rows per second.
MATRIX_TIERS = (
    (1, 8, 50),   # crawl, dim — the "far background"
    (1, 6, 65),   # slow
    (1, 4, 80),   # mid
    (4, 12, 90),  # brisk
    (1, 2, 100),  # sprint, full brightness
)


def _hash16(x, salt):
    """16-bit multiplicative hash of (x, salt): adjacent inputs scatter and
    every product stays a MicroPython small int (< 2**30, no bignum cost)."""
    return ((x * 40503 & 0xFFFF) ^ (salt * 21649 & 0xFFFF)) & 0x3FFFFFFF


def _tier_of(x):
    # per-column tier from a 16-bit hash — a plain modulo cycles too
    # regularly; the hash scatters adjacent columns over all tiers
    return (_hash16(x, 1) >> 4) % len(MATRIX_TIERS)


def _gap_of(x):
    # blank stretch before respawn, per column, 4..11 rows: columns still
    # differ in how densely they rain (duty 0.7..1.0 of the loop) but the
    # board reads dense overall; the slower the tier, the longer the dark
    # stretch lasts, which reads as depth
    return 4 + (_hash16(x, 2) >> 6) % 8


def matrix_col(x, h, frame):
    """Subpixel drop state of column x at frame: (c16, L16, bright, seed) —
    head position in 1/SUB-row steps (mod the column loop), trail length in
    rows (0 = resting pass: the column drops nothing this pass, so local
    density breathes), tier brightness, and the per-pass LCG seed for the
    head-hue schedule. Exposed for tuning and exact tests; draw_matrix only
    rasterizes what this state implies. Trail length and the resting/active
    decision mix from a hash over (column index and the pass number — one
    pass = one full drop travel), so density, speed mix, hue and trail vary
    pass to pass while staying deterministic. Constants stay under 2**30 so
    every product is a MicroPython small int — no bignum allocation per
    column and frame (a 32-bit LCG constant measured ~16 ms/frame slower)."""
    tier = _tier_of(x)
    rows, per, bright = MATRIX_TIERS[tier]
    gap = _gap_of(x)
    loop16 = (h + gap) * SUB
    u = (rows * SUB * frame) // per + (x * 37) * SUB   # + per-column phase
    pass_idx = u // loop16            # one pass = one full drop travel
    mix = _hash16(x, pass_idx)
    L = 4 + (mix >> 8) % 3            # 4..6 rows of trail per pass
    if (mix >> 3) % 10 == 0:          # ~1 pass in 10 rests: density breathes
        L = 0
    # head hue: ~1 pass in 5 takes an accent tint (1..N_ACCENT), the rest
    # stay classic green (seed 0) — every pass shimmers its bottom pixel
    variant = (mix >> 5) % 5
    seed = 1 + (mix >> 11) % N_ACCENT if variant == 0 else 0
    return u % loop16, L * SUB, bright, seed


def tint_at(seed, pos16, settle_pos16):
    """Head-hue schedule (the bottom-pixel shimmer). The head drops one
    row and cycles several hues within that row (one churn step per
    quarter-row), then — halfway down the pass — settles on its pass tint
    for the rest of the fall. seed 0 = classic green pass, mostly the base
    tint with a dip into a subtle neighbor on every 4th step; accent
    passes (seed 1..N_ACCENT) cycle the accent tints. Trail pixels keep
    the hue the head had when it passed them."""
    if pos16 >= settle_pos16:
        return seed
    step = pos16 // MATRIX_CHURN_SUB
    if seed == 0:
        if step % 4 != 3:
            return 0
        return 1 if (step // 4) % 2 == 0 else 3
    return 1 + (step + seed - 1) % N_ACCENT


# Pen memo for draw_matrix: the pixel color depends on (tint, bright, L16,
# alpha bucket) — only ~89 alpha buckets exist per (L16, bright, tint) — so
# pens are cached in a dict keyed by one int
# (bucket | tint<<8 | bright<<12 | L16<<19) instead of re-creating a pen per
# pixel. The bucket quantization bounds the memo (~few thousand entries, a
# few KB); exact-alpha keys proved effectively unbounded (heap full in ~3 s
# on board with the sub-integer rows/tick tiers). Board benchmark of this
# loop: 41 ms/frame naive -> ~29 ms (scanout stays ~2 ms).
_PEN_MEMO = {}

# Log-shaped trail-fade table: alpha weight per subpixel distance behind the
# head, exponential decay with a 2-row half-life (×2^(-1/32) per subpixel
# step, integer fixed point, ×251/256). Fades a bit faster early than the
# linear ramp it replaces, then levels off into a long dim tail — visually a
# log curve (linear's tail end is ~1.6% of head brightness, this keeps ~11%).
# The half-life can't be much shorter: the pixel holding the head sits at
# clamped dc 0..8, so f^8 sets its dimmest subpixel step (0.85 here) — steeper
# curves dip the "live" head well below the strongly-green threshold. Built
# at import for the only three trail lengths matrix_col ever yields
# (L = 4..6 rows → L16 = 64/80/96); draw_matrix indexes the dict directly,
# since a per-column builder call measured ~2.7 ms/frame extra. Weights stay
# <= L16 <= 96, so a byte holds each. Index is the clamped center distance
# dc the loop already computes; f[0] = L16 is the reference full brightness.
def _build_fade(L16):
    f = bytearray(L16)
    w = L16 << 8
    for i in range(L16):
        f[i] = w >> 8
        w = w * 251 >> 8
    return f


# The rain-clock overlay: rain inside the clock's text box is dimmed toward
# MATRIX_DIM % of its alpha (draw_matrix's optional dim_mask, built by
# draw_rain_clock), so the bright digits read over the pouring field even
# where a drop head passes directly behind them. The level is a flag in the
# pen-memo key (bit 28, above L16's last bit 25) so the dimmed pens never
# collide with the full-brightness ones of the same alpha bucket.
MATRIX_DIM = 35          # % of full alpha at the overlay's full strength
_KEY_DIM = 1 << 28
MATRIX_FADE_STEPS = 4    # dither levels: 0 = bare rain; STEPS = fully dim
# entry ramp: the dim does not re-press every in-box pixel with a level
# (that multiplied the pen space per level and stuttered the fade-in —
# burst-created pens + heap dips at dict growth); instead the box is dimmed
# through an ordered 4x4 Bayer pattern: at level L every box pixel whose
# threshold < L draws dim, so the dim patch spreads over the text box in a
# regular sweep while *no* pen is created for the fade itself — a level
# step costs nothing per frame and the ramp stays at full fps.
_BAYER4 = ((0, 2, 0, 2), (3, 1, 3, 1), (0, 2, 0, 2), (3, 1, 3, 1))
# exit: no dedicated pour phase — the moment the mode ends, the dim box
# lifts, the full rain pours over the still-bright clock AND the clock's
# ink starts converting to droplets one pixel at a time (organic: each
# pixel's conversion step and fall speed come from a hash), falling off
# the bottom like the rest of the rain.
MATRIX_STAGGER_STEPS = 4   # the ink-to-drop conversion waves through:
                           # ~1/4 of the clock converts per step, so the
                           # crumble is obvious from the very first step
                           # (a finer 9-step spread read as a separate
                           # "pour" stage first, crumble later)
MATRIX_DISSOLVE_STEPS = (MATRIX_STAGGER_STEPS + 11)
                           # +11 = one drop falling clear of the matrix

# bitmap6 digits, embedded (same bytes as sim/font6_data.py, itself a copy
# of Pimoroni's frozen font): the exit ramp needs per-pixel access to the
# glyph shapes and the board's PicoGraphics can't read its own text back.
# Each glyph is column bytes; bit r of byte c = pixel (c, r), 6 rows tall.
# tests/test_display.py pins this copy against the real font via the sim.
_DIGIT_GLYPHS = {
    "0": (28, 34, 34, 34, 30, 0), "1": (2, 62, 0, 0, 0, 0),
    "2": (50, 42, 42, 36, 0, 0),  "3": (42, 42, 42, 22, 0, 0),
    "4": (14, 16, 16, 62, 16, 0), "5": (46, 42, 42, 18, 0, 0),
    "6": (60, 42, 42, 42, 18, 0), "7": (6, 2, 34, 18, 14, 0),
    "8": (20, 42, 42, 42, 22, 0), "9": (4, 42, 42, 42, 30, 0),
}
_DIGIT_WIDTHS = (5, 2, 4, 4, 5, 4, 5, 5, 5, 5)   # bitmap6 widths for 0..9


_FADE_TAB = {L * SUB: _build_fade(L * SUB) for L in (4, 5, 6)}


def draw_matrix(d, w, h, frame, dim_mask=None):
    """Green code-rain falling down the whole matrix: one anti-aliased drop
    per column, staggered speeds and phases (five speed/brightness tiers,
    see MATRIX_TIERS), head pixel cycling through MATRIX_TINTS and settling
    to its pass hue halfway down; trail pixels keep their emission-time hue.
    dim_mask (rain-clock overlay, draw_rain_clock) is a w*h bytearray
    laid out [x * h + j] holding the fade level (0..MATRIX_FADE_STEPS): an
    in-box pixel draws dim when its Bayer threshold is under that level
    (level STEPS dims every box pixel); a bare rain has no mask at all.
    Fixed-point math only — identical output on board and host sim.
    Rasterizer is board-tuned: no min/max calls, memoized pens, bound
    attribute lookups."""
    SUB2 = SUB // 2
    set_pen = d.set_pen
    pixel = d.pixel
    create_pen = d.create_pen
    memo = _PEN_MEMO
    mget = memo.get
    mask = dim_mask
    for x in range(w):
        c16, L16, bright, seed_v = matrix_col(x, h, frame)
        if L16 == 0:            # resting pass: the cov math below would
            continue            # draw nothing anyway; skip its overhead
        lo = c16 - L16              # streak top edge (may be < 0)
        j0 = lo // SUB
        if j0 < 0:
            j0 = 0
        j1 = (c16 - 1) // SUB       # row holding the head
        if j1 > h - 1:
            j1 = h - 1
        # the head settles at its pass hue halfway down the loop
        settle_pos = ((h + _gap_of(x)) * SUB) // 2
        fade = _FADE_TAB[L16]
        mo = x * h if mask else 0   # dim-mask column base
        for j in range(j0, j1 + 1):
            top = j * SUB
            # coverage = overlap of pixel [j, j+1) with streak [lo, c16],
            # inlined min/max
            cov = (c16 if c16 < top + SUB else top + SUB) \
                - (lo if lo > top else top)
            if cov <= 0:
                continue
            # hue: the head row uses the live position; rows the head has
            # already passed freeze at their emission position
            pos = c16 if c16 < top + SUB else top + SUB
            # head-hue schedule (tint_at inlined): the head cycles hues
            # several times per row of travel; base passes mostly stay on
            # the classic green, accent passes cycle the accents
            if pos >= settle_pos:
                ti = seed_v
            elif seed_v:
                ti = 1 + (pos // MATRIX_CHURN_SUB + seed_v - 1) % N_ACCENT
            elif (pos // MATRIX_CHURN_SUB) % 4 == 3:
                ti = 1 if ((pos // MATRIX_CHURN_SUB) // 4) % 2 == 0 else 3
            else:
                ti = 0
            # log-shaped fade with distance behind the head (center-based
            # weight, clamped) — see _FADE_TAB above the pen memo
            dc = c16 - top - SUB2
            if dc < 0:
                dc = 0
            elif dc >= L16:
                dc = L16 - 1
            a = cov * fade[dc]      # 0..SUB*L16 alpha numerator
            if mask:
                # fade-level dither (see _BAYER4): the mask byte carries the
                # ramp level; a pixel draws dim the moment the level sweeps
                # past its Bayer threshold — no per-level pens exist at all
                if mask[mo + j] > _BAYER4[x & 3][j & 3]:
                    a = a * MATRIX_DIM // 100
                    is_dim = True
                else:
                    is_dim = False
            else:
                is_dim = False
            # memo key: alpha is quantized to its top 4 bits' index (q, at
            # most ~89 levels) — without this the exact subpixel alpha set
            # grows with every frame's fractional head position and the memo
            # is effectively unbounded (filled the heap in ~3 s on board);
            # pens are built from the bucket MIDPOINT so colors are
            # order-independent and identical on sim and board. a < 2**11,
            # so q < 2**7; ti < 8; bright <= 100, L16 < 2**7; bit 28 marks a
            # dim-masked pixel (rain-clock overlay) so the darkened alpha
            # space never shares a pen with the full-brightness one.
            if is_dim:
                # in-box dimmed pixels sit behind the dim mask and the
                # digits: the 4-bit bucket count is invisible there, and a
                # full 120 s rain once measured 4831 pens (2.3x the bare
                # memo) and collapsed the heap at dict growth (the ERR-on-
                # press bug). The 2-bit bucket count keeps the overlay's
                # share of the memo small.
                sh = 6
            else:
                sh = 4
            q = a >> sh                     # bucket index (floor, as before)
            key = (q | (ti << 8) | (bright << 12) | (L16 << 19) |
                   (_KEY_DIM if is_dim else 0))
            pen = mget(key)
            if pen is None:
                am = (q << sh) + (1 << (sh - 1))  # bucket midpoint alpha
                den = SUB * L16 * 100
                tc = MATRIX_TINTS[ti]
                pen = create_pen(tc[0] * am * bright // den,
                                 tc[1] * am * bright // den,
                                 tc[2] * am * bright // den)
                memo[key] = pen
            set_pen(pen)
            pixel(x, j)


# --- screens --------------------------------------------------------------


def _clock_ink(d, w, h, hh, mm):
    """The clock's ink as [(x, y, convert_at, fall_speed)] over the same
    layout math draw_clock uses (no blink dots): x/y from the embedded
    digit glyphs, convert_at = the dissolve step this pixel turns into a
    drop (hashed: staggered, organic — never the whole clock at once, and
    never before the pour is over), fall_speed = 1 or 2 rows per step.
    Cached per (hh, mm, w): it only changes once a minute."""
    global _INK_CACHE
    key = (hh, mm, w)
    if _INK_CACHE is not None and _INK_CACHE[0] == key:
        return _INK_CACHE[1]
    ink = []
    mhh = d.measure_text(hh, 1)
    base_x = ((w - (mhh + 3 + d.measure_text(mm, 1))) // 2)
    for base, s in ((base_x, hh), (base_x + mhh + 3, mm)):
        cx = base
        for ch in s:
            o = ord(ch) - 48
            if 0 <= o <= 9:
                cols = _DIGIT_GLYPHS[ch]
                gw = _DIGIT_WIDTHS[o]
                for col in range(gw):
                    bits = cols[col]
                    for row in range(6):
                        if bits >> row & 1:
                            px = cx + col
                            py = TEXT_Y + row
                            if py < h:
                                hs = _hash16(px + py * w, 4)
                                ink.append((
                                    px, py,
                                    hs % MATRIX_STAGGER_STEPS,
                                    1 + (hs >> 7) % 2))
                cx += gw + 1   # one column of glyph + spacing, like font6
            else:
                cx += 2        # gaps advance like measure_text
    _INK_CACHE = (key, ink)
    return ink


def _dissolve_draw(d, w, h, hh, mm, frame, dissolve):
    """The exit ramp's frames: the unconverted ink stays white under the
    pouring field (draw_matrix overdraws it — drops cross the digits);
    converted pixels fall as bright drops with a dimming 2-row trail."""
    create_pen = d.create_pen
    white = create_pen(255, 255, 255)
    # the converted pixel: a full-brightness drop in the classic rain green
    hr, hg, hb = MATRIX_TINTS[0]
    head_pen = create_pen(hr, hg, hb)
    # trail pens: the drop's two previous positions, dimmer with distance
    dim1 = create_pen(hr * 55 // 100, hg * 55 // 100, hb * 55 // 100)
    dim2 = create_pen(hr * 25 // 100, hg * 25 // 100, hb * 25 // 100)
    for (x, y, s, stride) in _clock_ink(d, w, h, hh, mm):
        if dissolve <= s:          # still part of the text: white ink
            d.set_pen(white)
            d.pixel(x, y)
            continue
        head = y + (dissolve - s) * stride
        for back, pen in ((2, dim2), (1, dim1), (0, head_pen)):
            yy = head - back * stride
            if 0 <= yy < h:
                d.set_pen(pen)
                d.pixel(x, yy)


def draw_rain_clock(d, w, h, hh, mm, blink, frame, fade=MATRIX_FADE_STEPS,
                    dissolve=0):
    """Clock rendered through the matrix rain (the mode shown while button
    A's rain deadline is live): the field keeps falling everywhere, but its
    alpha is scaled down inside the clock's padded text box so the bright
    digits read clearly while drops visibly pour across them. fade phases
    the overlay in (matrix mode's entry): 0 = bare rain, no digits;
    MATRIX_FADE_STEPS = the full overlay. Digit brightness rides the same
    fade, so the clock materializes out of the field instead of popping in.
    dissolve phases it out (the exit, starting immediately): the dim box
    lifts, the full-strength rain pours across the still-bright clock and
    the ink converts to drops one pixel at a time (organic stagger) while
    it falls off the bottom like the rest of the rain — no dedicated pour
    step, the two happen together. Blink and the
    HH/MM layout reuse draw_clock's math (via the embedded ink map); same
    contract as the plain rain (frame tick only)."""
    clear(d, w, h)               # draw_matrix only paints the rain pixels
    if dissolve > 0:             # exit ramp: rain pours over, ink falls
        _dissolve_draw(d, w, h, hh, mm, frame, dissolve)
        draw_matrix(d, w, h, frame)   # the rain overdraws ink + exit drops
        return
    if fade <= 0:                # bare rain: no box, no digits
        draw_matrix(d, w, h, frame)
        return
    # the digits brighten on the same quantized ramp as the box dithers in —
    # one interpolated pen per frame (draw_clock converges blink pixels onto
    # it)
    dh = 255 * fade // MATRIX_FADE_STEPS
    # the mask buffer is reused across frames — a fresh bytearray every
    # frame poked the GC (which scans the big pen-memo dict) and showed up
    # as fps drops on board; zeroing the cached one is a C-speed slice copy
    global _RC_MASK, _RC_ZEROS
    mask = _RC_MASK
    if mask is None or len(mask) != w * h:
        _RC_MASK = bytearray(w * h)
        _RC_ZEROS = bytes(w * h)
        mask = _RC_MASK
    else:
        mask[:] = _RC_ZEROS
    # same layout math as draw_clock, padded a pixel on each side; each box
    # pixel carries the fade level so draw_matrix can compare it against the
    # pixel's Bayer threshold (see _BAYER4) — the dither dim is free of pens
    colon_adv = 3
    tw = d.measure_text(hh, 1) + colon_adv + d.measure_text(mm, 1)
    x0 = max(0, (w - tw) // 2 - 1)
    x1 = min(w, x0 + tw + 2)
    for x in range(x0, x1):
        for j in range(1, min(h, TEXT_Y + 7)):
            mask[x * h + j] = fade
    draw_matrix(d, w, h, frame, dim_mask=mask)
    draw_clock(d, w, h, hh, mm, blink, color=(dh, dh, dh))


# rain-clock dim mask, reused across frames (see draw_rain_clock)
_RC_MASK = None
_RC_ZEROS = None
# the exit ramp's ink map, cached per clock text (see _clock_ink)
_INK_CACHE = None


def draw_weather(d, w, h, code, temp_text, frame, is_day=1):
    """Icon + temperature as one group, centered so no space is wasted right."""
    icon_w = 10
    gap = 3
    text_w = d.measure_text(temp_text, 1)
    x0 = (w - (icon_w + gap + text_w)) // 2
    draw_icon(d, code, frame, ox=x0, oy=0, is_day=is_day)
    d.set_pen(d.create_pen(*WHITE))
    d.text(temp_text, x0 + icon_w + gap, TEXT_Y, scale=1)


def draw_clock(d, w, h, hh, mm, blink, color=None):
    # color=None keeps the rotation's clock-cyan; the rain overlay passes the
    # bright rain-white so the digits pop over the field
    colon_adv = 3  # reserved px for the colon, keeps layout stable
    tw = d.measure_text(hh, 1) + colon_adv + d.measure_text(mm, 1)
    x = (w - tw) // 2
    d.set_pen(d.create_pen(*(color or CLOCK)))
    d.text(hh, x, TEXT_Y, scale=1)
    if blink:  # two pixels, 1 Hz blink driven by time.ticks_ms() on the board
        cx = x + d.measure_text(hh, 1) + 1
        d.pixel(cx, 4)
        d.pixel(cx, 7)
    d.text(mm, x + d.measure_text(hh, 1) + colon_adv, TEXT_Y, scale=1)


def _arrow(d, x, y, up):
    if up:
        pts = ((x, y), (x - 1, y + 1), (x, y + 1), (x + 1, y + 1))
    else:
        pts = ((x, y + 2), (x - 1, y + 1), (x, y + 1), (x + 1, y + 1))
    for px, py in pts:
        d.pixel(px, py)


def draw_hilo(d, w, h, hi_text, lo_text):
    """High/low pair: arrow snug against its number, pair centered as a whole."""
    arrow_gap = 1   # arrow is 3 px wide
    group_gap = 6   # between the high and low groups
    gw_hi = 3 + arrow_gap + d.measure_text(hi_text, 1)
    gw_lo = 3 + arrow_gap + d.measure_text(lo_text, 1)
    x = (w - (gw_hi + group_gap + gw_lo)) // 2
    d.set_pen(d.create_pen(*HI))
    _arrow(d, x + 1, 3, True)
    d.text(hi_text, x + 3 + arrow_gap, TEXT_Y, scale=1)
    x2 = x + gw_hi + group_gap
    d.set_pen(d.create_pen(*LO))
    _arrow(d, x2 + 1, 3, False)
    d.text(lo_text, x2 + 3 + arrow_gap, TEXT_Y, scale=1)


def draw_co2(d, w, h, ppm):
    """CO2 reading in ppm as one centered text group, color-coded by level."""
    text = "CO2 %d" % ppm
    x = (w - d.measure_text(text, 1)) // 2
    d.set_pen(d.create_pen(*co2_color(ppm)))
    d.text(text, x, TEXT_Y, scale=1)


def draw_als(d, w, h, mn, mx, avg):
    """Debug screen: min/max/avg of the last ALS samples, one centered line."""
    text = "%d %d %d" % (mn, mx, avg)
    x = (w - d.measure_text(text, 1)) // 2
    d.set_pen(d.create_pen(*MSG))
    d.text(text, x, TEXT_Y, scale=1)


def co2_color(ppm):
    """Indoor air quality: green below CO2_WARN_PPM, amber below
    CO2_RED_PPM, red at/above CO2_RED_PPM."""
    if ppm < CO2_WARN_PPM:
        return CO2_OK
    if ppm < CO2_RED_PPM:
        return CO2_WARN
    return CO2_BAD


def draw_message(d, w, h, msg):
    d.set_pen(d.create_pen(*MSG))
    d.text(msg, 4, TEXT_Y, scale=1)


# 8 spinner positions around a center pixel
SPIN = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def draw_boot(d, w, h, label, frame):
    """Boot/loading screen: spinning dot + stage label (wifi/ntp/weather)."""
    cx, cy = 4, 5
    d.set_pen(d.create_pen(*MSG))
    d.pixel(cx, cy)
    for i, (dx, dy) in enumerate(SPIN):
        if i == frame % len(SPIN):
            d.set_pen(d.create_pen(*WHITE))
        else:
            d.set_pen(d.create_pen(*MSG))
        d.pixel(cx + dx, cy + dy)
    d.set_pen(d.create_pen(*MSG))
    d.text(label, 10, TEXT_Y, scale=1)
