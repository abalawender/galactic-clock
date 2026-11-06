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

def draw_icon(d, code, frame):
    kind = kind_of(code)
    if kind == "sun":
        d.set_pen(d.create_pen(255, 200, 0))
        d.rectangle(3, 4, 4, 4)  # core
        rays = ((5, 1), (5, 9), (1, 6), (9, 6), (2, 3), (8, 3), (2, 9), (8, 9))
        for i, (x, y) in enumerate(rays):
            # twinkle: alternate rays dim/bright
            d.set_pen(d.create_pen(255, 200 if (i + frame) % 2 == 0 else 60, 0))
            d.pixel(x, y)
        return
    d.set_pen(d.create_pen(*CLOUD))
    d.rectangle(1, 4, 8, 4)   # cloud body
    d.rectangle(3, 2, 4, 2)   # puff
    if kind == "rain":
        d.set_pen(d.create_pen(*RAIN))
        for x in (2, 5, 8):
            d.pixel(x, 8 + (frame + x) % 3)  # drops fall
    elif kind == "snow":
        d.set_pen(d.create_pen(*SNOW))
        for x in (2, 4, 6, 8):
            d.pixel(x, 8 + (frame + x) % 3)
    elif kind == "storm":
        if frame % 2 == 0:
            d.set_pen(d.create_pen(*BOLT))
            for x, y in ((5, 8), (4, 9), (5, 10)):
                d.pixel(x, y)


# --- screens ---------------------------------------------------------------

def draw_weather(d, w, h, code, temp_text, frame):
    draw_icon(d, code, frame % 4)
    d.set_pen(d.create_pen(*WHITE))
    d.text(temp_text, 13, TEXT_Y, scale=1)


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
    d.set_pen(d.create_pen(*HI))
    _arrow(d, 6, 3, True)
    d.text(hi_text, 12, TEXT_Y, scale=1)
    d.set_pen(d.create_pen(*LO))
    _arrow(d, 30, 3, False)
    d.text(lo_text, 36, TEXT_Y, scale=1)


def draw_message(d, w, h, msg):
    d.set_pen(d.create_pen(*MSG))
    d.text(msg, 4, TEXT_Y, scale=1)
