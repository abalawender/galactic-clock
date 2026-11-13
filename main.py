"""Weather clock for the Galactic Unicorn. Runs at boot as /main.py.

Connects to WiFi (credentials in /secrets.py, not committed), syncs the RTC
via NTP (clock on screen), fetches the forecast from open-meteo (no API key
needed), reads a local SCD41 CO2 sensor over I2C (breakout_scd41 is frozen
into Pimoroni's MicroPython), and rotates the screens on the 53x11 matrix:
clock, weather icon + temperature, high/low, CO2 ppm. Button A toggles the
matrix-rain animation mode (fragments of green code falling full-screen),
which then runs for two minutes (a second press stops it early) before the
regular rotation resumes. The rain keeps a persistent frame tick across
runs. Board telemetry
(ambient light, die temperature) is logged over UART each rotation, and
VSYS once at boot with the radio powered down (GP29 is the Pico W radio's
SPI CS, so it is only measurable with WLAN off). A boot/loading screen is
shown while WiFi connects so the matrix is never blank at startup. The clock
screen is only shown when the RTC is trustworthy — NTP-synced at least once
this boot, or already reading >= 2026 (a soft reset keeps the RTC running);
otherwise its slot shows "no ntp" instead of a wrong time. If WiFi could
not connect at boot (or drops later) it is retried periodically in the loop,
and a reconnect re-runs the NTP sync.

All drawing lives in render.py (pure, board-independent) so it can also run in
the host simulator: python3 sim/sim.py play --screen weather --code 61
Deploy with scripts/deploy.sh (mpremote cp main.py + render.py :).
"""
import gc
import time

import network
import ntptime
import urequests
import ujson
from machine import ADC, Pin
from breakout_scd41 import BreakoutSCD41  # frozen into Pimoroni's MicroPython
from pimoroni_i2c import PimoroniI2C

from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
from secrets import LOCATION_LAT, LOCATION_LON, TZ, WIFI_PASSWORD, WIFI_SSID

try:
    from secrets import SCD41_ALTITUDE_M  # optional; 0 = no pressure compensation
except ImportError:
    SCD41_ALTITUDE_M = 0

import render
import tz

WX_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_S = 600
RTC_TRUST_YEAR = 2026  # an unsynced RP2040 RTC boots at 2021-01-01; a synced one is >= 2026
WIFI_RETRY_S = 60      # retry a failed/dropped wifi connect at most this often

# Button A toggles the matrix rain. The pin comes from the frozen galactic
# class — the board's buttons are NOT GP6/7/8/9 (A=0, B=1, C=3, D=6; verified
# on this board via GalacticUnicorn.SWITCH_*). Buttons are active-low.
RAINFALL_BUTTON_PIN = GalacticUnicorn.SWITCH_A
MATRIX_MODE_S = 120    # one press plays the rain this long, unless re-pressed
RAIN_FPS = 30          # target rain-frame rate (render+scanout decide the real one)
RAIN_FRAME_US = 1000000 // RAIN_FPS
BUTTON_DEBOUNCE_MS = 50  # bounce is ~ms; rain-loop polls are ~35 ms apart

# SCD41 on the STEMMA QT / Qwiic connector
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
SCD41_ADDR = 0x62

gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W, H = gu.WIDTH, gu.HEIGHT

temp_adc = ADC(4)   # RP2040 internal temperature sensor channel
# NB: VSYS via ADC(29)/GP29 is only readable with the radio powered down —
# on the Pico W the CYW43439 uses GP29 as its SPI CS, so with WLAN active
# the VSYS/3 divider reads ~0 V (measured: 4.80 V radio off, 0.05 V on).
# read_vsys() handles the power-down; see main().

WMO = {
    0: "clear", 1: "clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "heavy snow", 77: "snow",
    80: "showers", 81: "showers", 82: "showers",
    85: "snow", 86: "snow", 95: "storm", 96: "storm", 99: "storm",
}


def show_now(msg):
    """Draw a status message immediately (boot/loading screens), no waiting."""
    render.clear(d, W, H)
    render.draw_message(d, W, H, msg)
    gu.update(d)


boot_frame = 0


def tick_boot(label):
    """One frame of the boot animation (spinner + stage label)."""
    global boot_frame
    render.clear(d, W, H)
    render.draw_boot(d, W, H, label, boot_frame)
    gu.update(d)
    boot_frame += 1


def read_vsys(wlan):
    """VSYS via ADC3/GP29 (1/3 divider), measured with the radio powered
    down: wlan.active(False) releases GP29 from the CYW43439's SPI, the ADC
    is created only then, and the result is the true supply voltage."""
    wlan.active(False)
    time.sleep(0.5)
    vsys = ADC(29).read_u16() * 3 * 3.3 / 65535
    return vsys


ntp_synced = False  # latched: the RTC was synced via NTP at least once this boot


def rtc_trusted():
    """True when the clock may be shown: NTP-synced at least once, or the
    RTC already reads >= RTC_TRUST_YEAR (a soft/watchdog reset keeps the RTC
    running, so it stays trustworthy until NTP re-syncs)."""
    return ntp_synced or time.localtime()[0] >= RTC_TRUST_YEAR


def connect_wifi():
    """Connect WiFi and sync the RTC via NTP; returns wlan (None on failure).
    A successful NTP sync latches the global ntp_synced (see rtc_trusted)."""
    global ntp_synced
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    t0 = time.time()
    while not wlan.isconnected() and time.time() - t0 < 20:
        tick_boot("wifi")
        time.sleep(0.5)
    if not wlan.isconnected():
        print("wifi connect failed")
        return None
    print("wifi connected, ip:", wlan.ifconfig()[0])
    for _ in range(3):
        tick_boot("ntp")
        try:
            ntptime.settime()
            ntp_synced = True
            break
        except OSError:
            time.sleep(1)
    print("rtc synced" if ntp_synced else "ntp sync failed", "epoch:", time.time())
    return wlan


def fetch_weather():
    url = ("%s?latitude=%s&longitude=%s"
           "&current=temperature_2m,weather_code,is_day"
           "&daily=temperature_2m_max,temperature_2m_min"
           "&timezone=%s&forecast_days=1"
           % (WX_URL, LOCATION_LAT, LOCATION_LON, TZ.replace("/", "%2F")))
    r = urequests.get(url)
    if r.status_code != 200:
        raise RuntimeError("weather http %d" % r.status_code)
    return ujson.loads(r.content)


def show_weather(wx, seconds):
    code = wx["current"]["weather_code"]
    temp = "%dC" % round(wx["current"]["temperature_2m"])
    is_day = wx["current"].get("is_day", 1)
    end = time.time() + seconds
    frame = 0
    # every show loop polls the button-A deadline (see rain_pending): a
    # press mid-rotation ends this screen within a frame and the rain
    # starts right away instead of at the next slot boundary
    while time.time() < end and not rain_pending():
        render.clear(d, W, H)
        # frame must advance by exactly 1 per shown frame: time.time() is int
        # seconds on this build, so int(time.time()*3) jumps 0,3,6,9... and
        # the drops appear to fall upwards
        render.draw_weather(d, W, H, code, temp, frame, is_day)
        frame += 1
        gu.update(d)
        time.sleep(0.15)


def show_clock(seconds):
    end = time.time() + seconds
    while time.time() < end and not rain_pending():
        # localtime() is UTC on this build — apply the TZ offset ourselves
        t = time.localtime(time.time() + tz.utc_offset(TZ, time.time()))
        # 1 Hz blink from ticks_ms (time.time() is int on this build)
        render.clear(d, W, H)
        render.draw_clock(d, W, H, "%02d" % t[3], "%02d" % t[4],
                          time.ticks_ms() % 1000 < 500)
        gu.update(d)
        time.sleep(0.2)


def show_hilo(wx, seconds):
    hi = "%d" % round(wx["daily"]["temperature_2m_max"][0])
    lo = "%d" % round(wx["daily"]["temperature_2m_min"][0])
    end = time.time() + seconds
    while time.time() < end and not rain_pending():
        render.clear(d, W, H)
        render.draw_hilo(d, W, H, hi, lo)
        gu.update(d)
        time.sleep(0.2)


def show_co2(ppm, seconds, alarm=False):
    end = time.time() + seconds
    first = True
    while time.time() < end and not rain_pending():
        render.clear(d, W, H)
        render.draw_co2(d, W, H, ppm)
        gu.update(d)
        if first and alarm:
            co2_alarm(ppm)  # beep while the first frame is already on screen
            first = False
        time.sleep(0.2)


# persistent tick of the animation mode: the rain keeps falling across runs
# instead of restarting from a blank matrix
anim_frame = 0


# Button A toggles the matrix rain via a pin IRQ so no press is ever missed
# (an edge can land anywhere between screen frames). The handler only runs
# the debounced edge -> deadline logic — no drawing, formatting or printing
# inside the hard IRQ; the main loop watches the deadline.
rain_button = Pin(RAINFALL_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
matrix_deadline = 0.0        # time.time() epoch when the rain ends; 0 = off
btn_last_press_ms = None     # ticks_ms() of the last accepted press (None:
                             # no accepted edge yet — ticks_ms wraps, so a
                             # literal 0 would poison the first diffs)
rain_exiting = False         # True once the exit dissolve has begun; a
                             # press must not re-arm the deadline mid-ramp
                             # (a late bounce edge >DEBOUNCE_MS after the
                             # press that ended the rain used to re-set the
                             # deadline, cancelling the exit — the animation
                             # froze and rain resumed for another 120 s)


def _rain_button_irq(pin):
    """Take a debounced fresh press and toggle: deadline unset -> set it to
    now + MATRIX_MODE_S (rain on); deadline active -> zero it (rain off)."""
    global matrix_deadline, btn_last_press_ms
    now_ms = time.ticks_ms()
    if btn_last_press_ms is not None and \
            time.ticks_diff(now_ms, btn_last_press_ms) < BUTTON_DEBOUNCE_MS:
        return  # bounce inside the debounce window: ignore
    btn_last_press_ms = now_ms
    if rain_exiting:
        return  # exit ramp in flight: this press must not re-arm
    if matrix_deadline > time.time():
        matrix_deadline = 0.0
    else:
        matrix_deadline = time.time() + MATRIX_MODE_S


def rain_pending():
    """True while button A's rain deadline is in the future — polled per
    frame by every show_* loop so a press mid-rotation ends the screen
    within a frame and the rain takes over immediately (the check used to
    live only at the slot boundaries, which delayed a mid-rotation press
    by up to ~15 s)."""
    return matrix_deadline > time.time()


rain_button.irq(_rain_button_irq, Pin.IRQ_FALLING)


def maybe_show_rain():
    """While button A's rain deadline is in the future, run full-screen
    matrix rain instead of the following data screens, the clock
    poured over the field (render.draw_rain_clock) when the RTC is trusted.
    The show loops bail on the deadline per frame (rain_pending), so this
    starts within a frame of the press, not at the next slot boundary.
    The clock phases in on entry (one fade level every other frame, ~0.3 s)
    and dissolves out on exit the moment it begins (draw_rain_clock's exit:
    no separate pour phase — the field pours over while the ink converts
    pixel by pixel, ending the moment the clock is fully gone). A second press
    zeroes the deadline (the loop notices within a frame and dissolves) and
    the timebox ends the mode on its own. Paces to
    RAIN_FPS by absolute ticks_us deadlines — render+scanout (~32 ms of the
    33 ms budget) decide whether a frame lands on time; when the loop falls
    behind it restarts the schedule instead of burst-catching-up, so fps
    sags briefly rather than speeds up."""
    global matrix_deadline, anim_frame, rain_exiting
    if matrix_deadline <= time.time():
        return
    print("matrix rain: on (%d s or until A again)" % MATRIX_MODE_S)
    # Frame stability: once the pen memo saturates (~2100 entries, ~1 min of
    # rain) the loop allocates nothing, and the frame time is stable; until
    # then new pens and dict growth allocate, so collect once up front.
    # gc.disable() was measured on the board to be a footgun — dict growth
    # ran out of heap within seconds with no collection to reclaim.
    gc.collect()
    next_frame_us = time.ticks_us()
    fade = 0
    dissolve = 0
    while True:
        past_deadline = time.time() >= matrix_deadline
        if past_deadline:
            # latch the exit: until the dissolve has finished, a press (or a
            # late bounce edge from the one that ended the rain) must not
            # re-arm the deadline and cancel the animation halfway
            rain_exiting = True
            if not rtc_trusted() or \
                    dissolve >= render.MATRIX_DISSOLVE_STEPS:
                break
            if anim_frame % 2 == 0:
                dissolve += 1    # the whole exit: ~1 s total
        elif rtc_trusted():
            # 4 dither levels, one every other frame: a ~0.3 s ramp. A step
            # allocates nothing (the Bayer dither just lights more of the
            # existing dim pens — see render._BAYER4), so the ramp runs at
            # full fps instead of stuttering; the mode entry's collect
            # covers the only real burst (a level's first masked pixels)
            if fade < render.MATRIX_FADE_STEPS and anim_frame % 2 == 0:
                fade += 1
        try:
            if rtc_trusted():
                # rain pours over the clock: localtime() is UTC on this
                # build — apply the tz offset ourselves (same path as
                # show_clock); with the RTC untrusted the rain runs alone
                # rather than show a wrong time (same rule as the
                # rotation's clock-hiding)
                t = time.localtime(time.time() + tz.utc_offset(TZ, time.time()))
                render.draw_rain_clock(d, W, H, "%02d" % t[3], "%02d" % t[4],
                                       time.ticks_ms() % 1000 < 500,
                                       anim_frame, fade=fade,
                                       dissolve=dissolve)
            else:
                render.clear(d, W, H)
                render.draw_matrix(d, W, H, anim_frame)
        except MemoryError:
            # belt and braces: the pen memo is a rebuildable cache — if a
            # frame ever runs out of heap, drop it (the next frame
            # repopulates it) instead of erroring the whole loop
            render._PEN_MEMO.clear()
            gc.collect()
        anim_frame += 1
        gu.update(d)
        next_frame_us = time.ticks_add(next_frame_us, RAIN_FRAME_US)
        delay_us = time.ticks_diff(next_frame_us, time.ticks_us())
        if delay_us > 0:
            time.sleep(delay_us / 1000000.0)
        else:
            next_frame_us = time.ticks_us()
    print("matrix rain: off")
    matrix_deadline = 0.0
    rain_exiting = False       # ramp finished — a fresh press may rain again


# the audible alarm fires at render.CO2_RED_PPM — the same level that turns
# the CO2 font red. SCD41 accuracy is ±(40 ppm + 5%), so the threshold is soft.
ALS_ALARM_MIN = 20     # gu.light() raw 0..4095; dark room established < 20, office lights 20-40

alarm_chs = None


def co2_alarm(ppm):
    """Audible alarm for high CO2, but only when the room has light (i.e.
    someone is around to hear it). Two-voice chirp 660/990/660 Hz: sine on
    the note (ch0), triangle on its fifth (ch1). Note: the synth output must
    be started with gu.play_synth() or nothing is audible, a triggered
    channel sustains until trigger_release(), and frequency must be an int."""
    global alarm_chs
    if ppm < render.CO2_RED_PPM or gu.light() < ALS_ALARM_MIN:
        return
    if alarm_chs is None:
        alarm_chs = [gu.synth_channel(0), gu.synth_channel(1)]
    gu.play_synth()
    for freq in (660, 990, 660):
        alarm_chs[0].configure(waveforms=alarm_chs[0].SINE, frequency=freq,
                               volume=0.16, attack=0.01, decay=0.001,
                               sustain=1.0, release=0.12)
        alarm_chs[1].configure(waveforms=alarm_chs[1].TRIANGLE,
                               frequency=int(freq * 1.5), volume=0.12,
                               attack=0.01, decay=0.001, sustain=1.0,
                               release=0.12)
        alarm_chs[0].trigger_attack()
        alarm_chs[1].trigger_attack()
        time.sleep(0.12)
        alarm_chs[0].trigger_release()
        alarm_chs[1].trigger_release()
        time.sleep(0.12)
    gu.stop_playing()
    print("CO2 ALARM: %d ppm, light %d" % (ppm, gu.light()))


def read_sys():
    """(ALS raw 0..4095, die temp C): gu.light() and the RP2040 temp ADC
    (27 - (V-0.706)/0.001721). Temp is a float — the formula has a
    fractional part (e.g. 27.98 C)."""
    light = gu.light()  # onboard sensor, 0..4095 (float)
    tv = temp_adc.read_u16() * 3.3 / 65535
    temp_c = 27 - (tv - 0.706) / 0.001721
    return light, temp_c


def log_sys():
    """Absolute board readouts over UART (visible in the mpremote REPL)."""
    light, temp_c = read_sys()
    print("sys: light=%d/4095 temp=%.2fC" % (light, temp_c))


def show_text(msg, seconds):
    end = time.time() + seconds
    while time.time() < end and not rain_pending():
        render.clear(d, W, H)
        render.draw_message(d, W, H, msg)
        gu.update(d)
        time.sleep(0.2)


def main():
    tick_boot("boot")
    # measure VSYS before the radio comes up (GP29 is the radio's SPI CS
    # once WLAN is active — see read_vsys); re-measuring later would need a
    # wlan.active(False) -> read -> reconnect cycle, ~seconds of wifi down
    pre = network.WLAN(network.STA_IF)
    print("sys: vsys=%.2fV (radio off)" % read_vsys(pre))
    wlan = connect_wifi()  # None on failure — retried in the loop below
    last_wifi_try = time.time()
    if wlan is None:
        show_now("no wifi")
    sensor = None
    try:
        i2c = PimoroniI2C(sda=I2C_SDA_PIN, scl=I2C_SCL_PIN)
        if SCD41_ADDR in i2c.scan():
            sensor = BreakoutSCD41(i2c)
            sensor.start()
            sensor.set_sensor_altitude(SCD41_ALTITUDE_M)
            print("scd41: periodic measurement started, alt %dm"
                  % SCD41_ALTITUDE_M)
        else:
            print("scd41: not found on i2c")
    except Exception as e:
        print("scd41 init failed:", e)
    wx = None
    last_fetch = 0.0
    while True:
        # one bad iteration must not kill the clock (a dead loop = blank
        # matrix); show the error and keep rotating
        try:
            if (wlan is None or not wlan.isconnected()) \
                    and time.time() - last_wifi_try >= WIFI_RETRY_S:
                # wifi failed at boot or dropped: keep retrying — a successful
                # connect re-runs NTP (connect_wifi latches ntp_synced)
                last_wifi_try = time.time()
                wlan = connect_wifi()
            if wx is None or time.time() - last_fetch > REFRESH_S:
                tick_boot("weather")
                try:
                    wx = fetch_weather()
                    last_fetch = time.time()
                    cur = wx["current"]
                    print("weather: %dC %s" % (round(cur["temperature_2m"]),
                                                WMO.get(cur["weather_code"], "?")))
                except Exception as e:
                    print("weather fetch failed:", e)
                    wx = None
            if rtc_trusted():
                show_clock(5)
            else:
                # never NTP-synced and RTC still < 2026 (fresh boot): showing
                # the clock would display a wrong time — message instead
                show_text("no ntp", 5)
            maybe_show_rain()
            if wx is not None:
                show_weather(wx, 5)
                show_hilo(wx, 5)
            else:
                show_text("no weather", 5)
            maybe_show_rain()
            if sensor is not None and sensor.ready():
                co2, _temp, _rh = sensor.measure()
                # alarm fires inside show_co2 right after the first frame,
                # so the beep overlaps the screen instead of preceding it
                show_co2(co2, 5, alarm=True)
            # telemetry ties to the data screens; the rain below doesn't log
            log_sys()
            # a press mid-rotation makes every show loop bail within a
            # frame (see rain_pending), so this runs almost immediately
            maybe_show_rain()
        except Exception as e:
            print("loop error:", e)
            # the first thing on screen must say *what* failed — the board
            # itself is the only REPL that always captures this
            show_text("err %s" % type(e).__name__[:9], 5)


if __name__ == "__main__":
    main()
