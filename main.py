"""Weather clock for the Galactic Unicorn. Runs at boot as /main.py.

Connects to WiFi (credentials in /secrets.py, not committed), syncs the RTC
via NTP (clock on screen), fetches the forecast from open-meteo (no API key
needed) and rotates three screens on the 53x11 matrix: clock, weather icon +
temperature, high/low.
"""
import time

import network
import ntptime
import urequests
import ujson

from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
from secrets import LOCATION_LAT, LOCATION_LON, TZ, WIFI_PASSWORD, WIFI_SSID

WX_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_S = 600

gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)

WMO = {
    0: "clear", 1: "clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "heavy snow", 77: "snow",
    80: "showers", 81: "showers", 82: "showers",
    85: "snow", 86: "snow", 95: "storm", 96: "storm", 99: "storm",
}


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    t0 = time.time()
    while not wlan.isconnected() and time.time() - t0 < 20:
        time.sleep(0.5)
    if not wlan.isconnected():
        raise RuntimeError("wifi connect failed")
    print("wifi connected, ip:", wlan.ifconfig()[0])
    for _ in range(3):
        try:
            ntptime.settime()
            break
        except OSError:
            time.sleep(1)
    print("rtc synced, epoch:", time.time())
    return wlan


def fetch_weather():
    url = ("%s?latitude=%s&longitude=%s"
           "&current=temperature_2m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min"
           "&timezone=%s&forecast_days=1"
           % (WX_URL, LOCATION_LAT, LOCATION_LON, TZ.replace("/", "%2F")))
    r = urequests.get(url)
    if r.status_code != 200:
        raise RuntimeError("weather http %d" % r.status_code)
    return ujson.loads(r.content)


def _kind(code):
    if code in (0, 1):
        return "sun"
    if code in (2, 3, 45, 48):
        return "cloud"
    if code >= 95:
        return "storm"
    if code >= 71:
        return "snow"
    return "rain"


def _clear():
    d.set_pen(d.create_pen(0, 0, 0))
    d.rectangle(0, 0, gu.WIDTH, gu.HEIGHT)


def draw_icon(code, frame=0):
    """10x11 animated icon in the left part of the matrix."""
    kind = _kind(code)
    if kind == "sun":
        d.set_pen(d.create_pen(255, 200, 0))
        d.rectangle(3, 4, 4, 4)  # core
        rays = ((5, 1), (5, 9), (1, 6), (9, 6), (2, 3), (8, 3), (2, 9), (8, 9))
        for i, (x, y) in enumerate(rays):
            # twinkle: alternate rays dim/bright
            d.set_pen(d.create_pen(255, 200 if (i + frame) % 2 == 0 else 60, 0))
            d.pixel(x, y)
        return
    d.set_pen(d.create_pen(160, 160, 170))
    d.rectangle(1, 4, 8, 4)   # cloud body
    d.rectangle(3, 2, 4, 2)   # puff
    if kind == "rain":
        d.set_pen(d.create_pen(60, 120, 255))
        for x in (2, 5, 8):
            d.pixel(x, 8 + (frame + x) % 3)  # drops fall
    elif kind == "snow":
        d.set_pen(d.create_pen(255, 255, 255))
        for x in (2, 4, 6, 8):
            d.pixel(x, 8 + (frame + x) % 3)
    elif kind == "storm":
        if frame % 2 == 0:
            d.set_pen(d.create_pen(255, 230, 0))
            for x, y in ((5, 8), (4, 9), (5, 10)):
                d.pixel(x, y)


def show_weather(wx, seconds):
    temp = round(wx["current"]["temperature_2m"])
    end = time.time() + seconds
    while time.time() < end:
        _clear()
        draw_icon(wx["current"]["weather_code"], frame=int(time.time() * 3) % 4)
        d.set_pen(d.create_pen(255, 255, 255))
        d.text("%dC" % temp, 13, 2, scale=1)
        gu.update(d)
        time.sleep(0.15)


def show_clock(seconds):
    colon_adv = 3  # reserved px for the colon, keeps layout stable
    end = time.time() + seconds
    while time.time() < end:
        t = time.localtime()
        hh = "%02d" % t[3]
        mm = "%02d" % t[4]
        w = d.measure_text(hh, 1) + colon_adv + d.measure_text(mm, 1)
        x = (gu.WIDTH - w) // 2
        _clear()
        d.set_pen(d.create_pen(120, 200, 255))
        d.text(hh, x, 2, scale=1)
        if time.ticks_ms() % 1000 < 500:  # 1 Hz blink (time.time() is int here!), two pixels
            cx = x + d.measure_text(hh, 1) + 1
            d.pixel(cx, 4)
            d.pixel(cx, 7)
        d.text(mm, x + d.measure_text(hh, 1) + colon_adv, 2, scale=1)
        gu.update(d)
        time.sleep(0.2)


def _arrow(x, y, up):
    if up:
        pts = ((x, y), (x - 1, y + 1), (x, y + 1), (x + 1, y + 1))
    else:
        pts = ((x, y + 2), (x - 1, y + 1), (x, y + 1), (x + 1, y + 1))
    for px, py in pts:
        d.pixel(px, py)


def show_hilo(wx, seconds):
    hi = round(wx["daily"]["temperature_2m_max"][0])
    lo = round(wx["daily"]["temperature_2m_min"][0])
    end = time.time() + seconds
    while time.time() < end:
        _clear()
        d.set_pen(d.create_pen(255, 90, 60))
        _arrow(6, 3, True)
        d.text("%d" % hi, 12, 2, scale=1)
        d.set_pen(d.create_pen(90, 140, 255))
        _arrow(30, 3, False)
        d.text("%d" % lo, 36, 2, scale=1)
        gu.update(d)
        time.sleep(0.2)


def show_text(msg, seconds):
    end = time.time() + seconds
    while time.time() < end:
        _clear()
        d.set_pen(d.create_pen(255, 160, 40))
        d.text(msg, 4, 2, scale=1)
        gu.update(d)
        time.sleep(0.2)


def main():
    connect_wifi()
    wx = None
    last_fetch = 0.0
    while True:
        if wx is None or time.time() - last_fetch > REFRESH_S:
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


if __name__ == "__main__":
    main()
