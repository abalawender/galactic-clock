"""Weather clock for the Galactic Unicorn. Runs at boot as /main.py.

Connects to WiFi (credentials in /secrets.py, not committed), syncs the RTC
via NTP, fetches the forecast from open-meteo (no API key needed) and shows
it on the 53x11 matrix: icon + current temperature, then high/low.
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


def draw_icon(code):
    """9x10 icon in the left part of the matrix."""
    kind = _kind(code)
    if kind == "sun":
        d.set_pen(d.create_pen(255, 200, 0))
        d.rectangle(3, 4, 4, 4)
        for x, y in ((5, 1), (5, 9), (1, 6), (9, 6), (2, 3), (8, 3), (2, 9), (8, 9)):
            d.pixel(x, y)
        return
    d.set_pen(d.create_pen(160, 160, 170))
    d.rectangle(1, 5, 8, 3)
    d.rectangle(3, 3, 4, 2)
    if kind == "rain":
        d.set_pen(d.create_pen(60, 120, 255))
        for x, y in ((2, 9), (5, 9), (7, 9)):
            d.pixel(x, y)
    elif kind == "snow":
        d.set_pen(d.create_pen(255, 255, 255))
        for x, y in ((2, 9), (4, 8), (6, 9), (8, 8)):
            d.pixel(x, y)
    elif kind == "storm":
        d.set_pen(d.create_pen(255, 230, 0))
        for x, y in ((5, 8), (4, 9), (5, 10)):
            d.pixel(x, y)


def show_static(wx, seconds):
    temp = round(wx["current"]["temperature_2m"])
    end = time.time() + seconds
    while time.time() < end:
        d.set_pen(d.create_pen(0, 0, 0))
        d.rectangle(0, 0, gu.WIDTH, gu.HEIGHT)
        draw_icon(wx["current"]["weather_code"])
        d.set_pen(d.create_pen(255, 255, 255))
        d.text("%dC" % temp, 11, 2, scale=1)
        gu.update(d)
        time.sleep(0.2)


def show_text(msg, seconds):
    end = time.time() + seconds
    while time.time() < end:
        d.set_pen(d.create_pen(0, 0, 0))
        d.rectangle(0, 0, gu.WIDTH, gu.HEIGHT)
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
        if wx is not None:
            show_static(wx, 5)
            hi = round(wx["daily"]["temperature_2m_max"][0])
            lo = round(wx["daily"]["temperature_2m_min"][0])
            show_text("H%d L%d" % (hi, lo), 5)
        else:
            show_text("no weather", 5)


if __name__ == "__main__":
    main()
