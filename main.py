"""Weather clock for the Galactic Unicorn. Runs at boot as /main.py.

Connects to WiFi (credentials in /secrets.py, not committed), syncs the RTC
via NTP (clock on screen), fetches the forecast from open-meteo (no API key
needed), reads a local SCD41 CO2 sensor over I2C (breakout_scd41 is frozen
into Pimoroni's MicroPython), and rotates the screens on the 53x11 matrix:
clock, weather icon + temperature, high/low, CO2 ppm. Board telemetry
(ambient light, die temperature) is logged over UART each rotation, and
VSYS once at boot with the radio powered down (GP29 is the Pico W radio's
SPI CS, so it is only measurable with WLAN off). A boot/loading screen is
shown while WiFi connects so the matrix is never blank at startup.

All drawing lives in render.py (pure, board-independent) so it can also run in
the host simulator: python3 sim/sim.py play --screen weather --code 61
Deploy with scripts/deploy.sh (mpremote cp main.py + render.py :).
"""
import time

import network
import ntptime
import urequests
import ujson
from machine import ADC
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


def connect_wifi():
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
            break
        except OSError:
            time.sleep(1)
    print("rtc synced, epoch:", time.time())
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
    while time.time() < end:
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
    while time.time() < end:
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
    while time.time() < end:
        render.clear(d, W, H)
        render.draw_hilo(d, W, H, hi, lo)
        gu.update(d)
        time.sleep(0.2)


def show_co2(ppm, seconds):
    end = time.time() + seconds
    while time.time() < end:
        render.clear(d, W, H)
        render.draw_co2(d, W, H, ppm)
        gu.update(d)
        time.sleep(0.2)


CO2_ALARM_PPM = 1200   # SCD41 CO2 accuracy ±(40 ppm + 5%) — threshold is soft
ALS_ALARM_MIN = 20     # gu.light() raw 0..4095; dark room established < 20, office lights 20-40

alarm_chs = None


def co2_alarm(ppm):
    """Audible alarm for high CO2, but only when the room has light (i.e.
    someone is around to hear it). Two-voice chirp 660/990/660 Hz: sine on
    the note (ch0), triangle on its fifth (ch1). Note: the synth output must
    be started with gu.play_synth() or nothing is audible, a triggered
    channel sustains until trigger_release(), and frequency must be an int."""
    global alarm_chs
    if ppm < CO2_ALARM_PPM or gu.light() < ALS_ALARM_MIN:
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
    while time.time() < end:
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
    wlan = connect_wifi()  # None on failure — the loop below shows "no wifi"
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
            show_clock(5)
            if wx is not None:
                show_weather(wx, 5)
                show_hilo(wx, 5)
            else:
                show_text("no weather", 5)
            if sensor is not None and sensor.ready():
                co2, _temp, _rh = sensor.measure()
                # beep first, then show the screen — the alarm is heard at
                # the start of the CO2 screen, leaving the full 5 s to read it
                co2_alarm(co2)
                show_co2(co2, 5)
            log_sys()
        except Exception as e:
            print("loop error:", e)
            show_text("err", 5)


if __name__ == "__main__":
    main()
