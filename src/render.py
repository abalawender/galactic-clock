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
SPOTIFY = (30, 215, 96)      # brand green: note icon + progress fill
SPOTIFY_DIM = (16, 84, 38)   # progress-bar track
PAUSED = (110, 110, 110)     # marquee text while paused

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


# --- screens ---------------------------------------------------------------

def draw_weather(d, w, h, code, temp_text, frame, is_day=1):
    """Icon + temperature as one group, centered so no space is wasted right."""
    icon_w = 10
    gap = 3
    text_w = d.measure_text(temp_text, 1)
    x0 = (w - (icon_w + gap + text_w)) // 2
    draw_icon(d, code, frame, ox=x0, oy=0, is_day=is_day)
    d.set_pen(d.create_pen(*WHITE))
    d.text(temp_text, x0 + icon_w + gap, TEXT_Y, scale=1)


def draw_clock(d, w, h, hh, mm, blink):
    colon_adv = 3  # reserved px for the colon, keeps layout stable
    tw = d.measure_text(hh, 1) + colon_adv + d.measure_text(mm, 1)
    x = (w - tw) // 2
    d.set_pen(d.create_pen(*CLOCK))
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


# --- spotify now-playing screen ---------------------------------------------
# Green eighth note on the left, scrolling "artist - title" marquee right of
# it, and a 1 px track progress bar along the bottom edge.

# Eighth note, 7x9 (x 0..6, y 0..8), drawn at (0, 1): flag top-right, stem at
# x=4, head at the bottom-left of the stem.
NOTE_PX = ((5, 0), (6, 0), (6, 1), (5, 2),
           (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5), (4, 6), (4, 7),
           (4, 8),
           (2, 6), (3, 6), (1, 7), (2, 7), (3, 7), (1, 8), (2, 8), (3, 8))
NOTE_TEXT_X = 9  # marquee area starts right of the 7 px icon (+ 2 px gap)


def draw_marquee(d, w, h, text, frame, x0, color=WHITE, hold=8, gap=6):
    """Scrolling text in the area right of x0. Held at x0 for `hold` frames,
    then moves left 1 px per frame; once the tail has passed x0, a `gap`-px
    blank wraps around and the text re-enters from the right. Text that fits
    the area is centered instead of scrolling."""
    tw = d.measure_text(text, 1)
    d.set_pen(d.create_pen(*color))
    if tw <= w - x0:
        d.text(text, x0 + (w - x0 - tw) // 2, TEXT_Y, scale=1)
        return
    off = (frame - hold) % (tw + gap) if frame >= hold else 0
    d.text(text, x0 - off, TEXT_Y, scale=1)


def draw_spotify(d, w, h, line, frame, progress=0.0, playing=True):
    """Now-playing screen: note icon + marquee + progress bar. `line` is
    "artist - title", `progress` in 0..1; paused playback dims the text."""
    draw_marquee(d, w, h, line, frame, NOTE_TEXT_X,
                 color=(WHITE if playing else PAUSED))
    # the marquee scrolls left past NOTE_TEXT_X — mask the icon gutter so
    # the text never bleeds into it, then draw the note on top
    d.set_pen(d.create_pen(*BLACK))
    d.rectangle(0, 0, NOTE_TEXT_X, h - 1)
    d.set_pen(d.create_pen(*SPOTIFY))
    for (x, y) in NOTE_PX:
        d.pixel(x, 1 + y)
    d.set_pen(d.create_pen(*SPOTIFY_DIM))
    d.rectangle(0, h - 1, w, 1)
    d.set_pen(d.create_pen(*SPOTIFY))
    d.rectangle(0, h - 1, int(progress * w), 1)


# --- 5px monospace font for two-line screens --------------------------------
# Hand-authored 5x5 (Tiny5-style); same column-byte format as the sim's
# font6_data: bit y of byte x = pixel (x, y), row 0 = top. Rendered with
# d.pixel() so it also works on the board's PicoGraphics (no custom font).
FONT5 = {
    ' ': (0, 0, 0, 0, 0),
    '!': (0, 0, 15, 0, 0),
    '"': (0, 3, 0, 3, 0),
    '#': (10, 31, 10, 31, 10),
    '$': (4, 10, 31, 10, 18),
    '%': (19, 8, 4, 2, 25),
    '&': (14, 17, 21, 10, 16),
    "'": (0, 0, 3, 0, 0),
    '(': (0, 0, 14, 17, 0),
    ')': (0, 17, 14, 0, 0),
    '*': (0, 10, 4, 10, 0),
    '+': (0, 4, 14, 4, 0),
    ',': (0, 16, 8, 0, 0),
    '-': (0, 4, 4, 4, 0),
    '.': (0, 0, 16, 0, 0),
    '/': (16, 8, 4, 2, 1),
    '0': (14, 17, 25, 21, 14),
    '1': (0, 18, 31, 16, 0),
    '2': (18, 17, 25, 21, 18),
    '3': (2, 17, 21, 29, 2),
    '4': (8, 12, 10, 31, 8),
    '5': (23, 21, 21, 21, 9),
    '6': (14, 21, 21, 21, 8),
    '7': (1, 1, 25, 5, 3),
    '8': (10, 21, 21, 21, 10),
    '9': (2, 21, 21, 21, 14),
    ':': (0, 0, 10, 0, 0),
    ';': (0, 16, 10, 0, 0),
    '<': (0, 4, 10, 17, 0),
    '=': (0, 10, 10, 10, 0),
    '>': (0, 17, 10, 4, 0),
    '?': (2, 1, 25, 5, 2),
    '@': (14, 17, 21, 21, 6),
    'A': (30, 5, 5, 5, 30),
    'B': (31, 21, 21, 21, 10),
    'C': (14, 17, 17, 17, 0),
    'D': (31, 17, 17, 10, 4),
    'E': (31, 21, 21, 21, 17),
    'F': (31, 5, 5, 5, 1),
    'G': (14, 17, 17, 21, 12),
    'H': (31, 4, 4, 4, 31),
    'I': (0, 17, 31, 17, 0),
    'J': (8, 16, 17, 15, 1),
    'K': (31, 4, 4, 10, 17),
    'L': (31, 16, 16, 16, 16),
    'M': (31, 2, 4, 2, 31),
    'N': (31, 2, 4, 8, 31),
    'O': (14, 17, 17, 17, 14),
    'P': (31, 5, 5, 5, 2),
    'Q': (14, 17, 17, 9, 22),
    'R': (31, 5, 5, 13, 18),
    'S': (18, 21, 21, 21, 9),
    'T': (1, 1, 31, 1, 1),
    'U': (15, 16, 16, 16, 15),
    'V': (15, 0, 16, 0, 15),
    'W': (31, 8, 4, 8, 31),
    'X': (27, 0, 4, 0, 27),
    'Y': (3, 0, 28, 0, 3),
    'Z': (17, 25, 21, 19, 17),
    '[': (0, 31, 17, 17, 0),
    '\\': (1, 2, 4, 8, 16),
    ']': (0, 17, 17, 31, 0),
    '^': (0, 2, 1, 2, 0),
    '_': (16, 16, 16, 16, 16),
    '`': (0, 1, 2, 0, 0),
    'a': (0, 20, 20, 20, 24),
    'b': (31, 20, 20, 20, 8),
    'c': (8, 20, 20, 20, 0),
    'd': (8, 20, 20, 20, 31),
    'e': (8, 28, 28, 28, 8),
    'f': (0, 30, 5, 5, 0),
    'g': (20, 10, 10, 10, 30),
    'h': (31, 4, 4, 4, 24),
    'i': (0, 20, 29, 16, 0),
    'j': (0, 16, 20, 13, 0),
    'k': (31, 8, 8, 20, 0),
    'l': (0, 1, 31, 0, 0),
    'm': (28, 4, 24, 4, 24),
    'n': (28, 4, 4, 4, 24),
    'o': (8, 20, 20, 20, 8),
    'p': (30, 10, 10, 10, 4),
    'q': (4, 10, 10, 10, 30),
    'r': (28, 8, 4, 4, 0),
    's': (24, 20, 20, 20, 4),
    't': (0, 15, 20, 20, 0),
    'u': (12, 16, 16, 16, 28),
    'v': (12, 0, 16, 0, 12),
    'w': (12, 16, 8, 16, 12),
    'x': (20, 0, 8, 0, 20),
    'y': (4, 8, 16, 8, 4),
    'z': (20, 20, 28, 20, 20),
    '{': (0, 4, 10, 17, 0),
    '|': (0, 0, 31, 0, 0),
    '}': (0, 17, 10, 4, 0),
    '~': (8, 4, 12, 8, 4),
}


def measure_text5(s, spacing=1):
    """Width of `s` in the 5px monospace font (every glyph 5 px + spacing)."""
    if not s:
        return 0
    return len(s) * (5 + spacing) - spacing


def text5(d, s, x, y, spacing=1):
    cx = x
    for ch in s:
        cols = FONT5.get(ch)
        if cols is not None:
            for col in range(5):
                bits = cols[col]
                for row in range(5):
                    if bits >> row & 1:
                        d.pixel(cx + col, y + row)
        cx += 5 + spacing


def draw_marquee5(d, w, text, frame, x0, y, color=WHITE, hold=8, gap=6):
    """draw_marquee with the 5px font at an arbitrary y (two-line screens)."""
    tw = measure_text5(text)
    d.set_pen(d.create_pen(*color))
    if tw <= w - x0:
        text5(d, text, x0 + (w - x0 - tw) // 2, y)
        return
    off = (frame - hold) % (tw + gap) if frame >= hold else 0
    text5(d, text, x0 - off, y)


F5_TEXT_X = 9        # same icon gutter as NOTE_TEXT_X
F5_LINE_Y = (0, 5)   # two 5px lines fill rows 0..9; row 10 = progress bar


def draw_spotify5(d, w, h, artist, title, frame, progress=0.0, playing=True):
    """Two-line now-playing screen: artist (top) / title (bottom) marquee in
    the 5px font, note icon left, 1 px progress bar on the bottom row. Lines
    sit at rows 0-4 and 5-9, so a descender can touch the line below."""
    color = WHITE if playing else PAUSED
    draw_marquee5(d, w, artist, frame, F5_TEXT_X, F5_LINE_Y[0], color)
    draw_marquee5(d, w, title, frame, F5_TEXT_X, F5_LINE_Y[1], color)
    # mask the icon gutter so the marquee never bleeds into it, then the note
    d.set_pen(d.create_pen(*BLACK))
    d.rectangle(0, 0, F5_TEXT_X, h - 1)
    d.set_pen(d.create_pen(*SPOTIFY))
    for (x, y) in NOTE_PX:
        d.pixel(x, 1 + y)
    d.set_pen(d.create_pen(*SPOTIFY_DIM))
    d.rectangle(0, h - 1, w, 1)
    d.set_pen(d.create_pen(*SPOTIFY))
    d.rectangle(0, h - 1, int(progress * w), 1)


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
