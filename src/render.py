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
CLOUD = (160, 160, 170)
RAIN = (60, 120, 255)
SNOW = (255, 255, 255)
BOLT = (255, 230, 0)
HI = (255, 90, 60)
LO = (90, 140, 255)
CLOCK = (120, 200, 255)
MSG = (255, 160, 40)
CO2_OK = (80, 220, 80)    # < 800 ppm
CO2_WARN = (255, 200, 0)  # < 1200 ppm
CO2_BAD = (255, 60, 60)   # >= 1200 ppm

TEXT_Y = 2


def clear(d, w, h):
    d.set_pen(d.create_pen(*BLACK))
    d.rectangle(0, 0, w, h)


def kind_of(code):
    if code in (0, 1):
        return "sun"
    if code in (2, 3, 45, 48):
        return "cloud"
    if code >= 95:
        return "storm"
    if code >= 71:
        return "snow"
    return "rain"


# --- animated weather icon, 10x11 in the left part of the matrix -----------

# Cloud occupies rows 1..6, leaving rows 7..10 for precipitation: FALL_ROWS
# rows of falling drops, staggered per column so they never move in lockstep.
# y = CLOUD_BOTTOM + (frame + phase) % FALL_ROWS increases every tick and
# wraps at the bottom -> drops always fall down and respawn at the top.
# (Previously the tick was taken mod 4 but the row mod 3, so drops jumped up on
# wrap, and x=2,5,8 are all 2 mod 3, so every column shared one phase.)
CLOUD_BOTTOM = 7
FALL_ROWS = 4  # rows 7..10


def draw_icon(d, code, frame, ox=0, oy=0):
    kind = kind_of(code)
    if kind == "sun":
        d.set_pen(d.create_pen(255, 200, 0))
        d.rectangle(ox + 3, oy + 4, 4, 4)  # core
        rays = ((5, 1), (5, 9), (1, 6), (9, 6), (2, 3), (8, 3), (2, 9), (8, 9))
        for i, (x, y) in enumerate(rays):
            # twinkle: alternate rays dim/bright
            d.set_pen(d.create_pen(255, 200 if (i + frame) % 2 == 0 else 60, 0))
            d.pixel(ox + x, oy + y)
        return
    d.set_pen(d.create_pen(*CLOUD))
    d.rectangle(ox + 1, oy + 3, 8, 4)   # cloud body, rows 3..6
    d.rectangle(ox + 3, oy + 1, 4, 2)   # puff, rows 1..2
    if kind == "rain":
        d.set_pen(d.create_pen(*RAIN))
        for i, x in enumerate((2, 5, 8)):
            d.pixel(ox + x, oy + CLOUD_BOTTOM + (frame + i) % FALL_ROWS)
    elif kind == "snow":
        d.set_pen(d.create_pen(*SNOW))
        for i, x in enumerate((2, 4, 6, 8)):
            d.pixel(ox + x, oy + CLOUD_BOTTOM + (frame // 2 + i) % FALL_ROWS)
    elif kind == "storm":
        if frame % 2 == 0:
            d.set_pen(d.create_pen(*BOLT))
            for x, y in ((5, 7), (4, 8), (6, 9), (5, 10)):
                d.pixel(ox + x, oy + y)


# --- screens ---------------------------------------------------------------

def draw_weather(d, w, h, code, temp_text, frame):
    """Icon + temperature as one group, centered so no space is wasted right."""
    icon_w = 10
    gap = 3
    text_w = d.measure_text(temp_text, 1)
    x0 = (w - (icon_w + gap + text_w)) // 2
    draw_icon(d, code, frame, ox=x0, oy=0)
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


def co2_color(ppm):
    """Indoor air quality: green < 800 ppm, amber < 1200, red above."""
    if ppm < 800:
        return CO2_OK
    if ppm < 1200:
        return CO2_WARN
    return CO2_BAD


def draw_message(d, w, h, msg):
    d.set_pen(d.create_pen(*MSG))
    d.text(msg, 4, TEXT_Y, scale=1)
