"""The forecast service: one open-meteo fetch + cache. The network is
touched only through `urequests` (sandbox: mocked in sim/run_main.py), so
`_fetch()` is deterministic anywhere else. Cadence lives here: the loop
calls `refresh_if_due()` every pass, the module decides when to re-fetch."""

import time

import ujson
import urequests

WX_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_S = 600  # one successful fetch serves this long (10 min)


class Weather:
    """The forecast cache: `refresh_if_due()` re-fetches when the
    successful one is stale — and every pass while nothing succeeded yet
    (a failed fetch clears the cache, exactly like main() used to).
    `current()` is the latest forecast dict, None before the first
    success."""

    def __init__(self, lat, lon, tz_name):
        self._lat = lat
        self._lon = lon
        self._tz = tz_name
        self._wx = None          # the latest forecast dict
        self._fetched_at = None  # epoch of the last successful fetch

    def due(self):
        """True when the next `refresh_if_due()` call would fetch — the
        caller uses this to draw the boot spinner BEFORE the blocking
        fetch, not after."""
        return self._fetched_at is None or \
            time.time() - self._fetched_at > REFRESH_S

    def refresh_if_due(self):
        """Re-fetch when stale; returns True only when a fetch was
        attempted this call (so the caller can log the fresh result)."""
        if not self.due():
            return False
        try:
            self._wx = self._fetch()
            self._fetched_at = time.time()
        except Exception as e:
            self._wx = None  # nothing stale survives a failure: retry
            print("weather fetch failed:", e)
        return True

    def current(self):
        """The latest forecast dict, or None before the first success."""
        return self._wx

    def _fetch(self):
        """One open-meteo round-trip: GET + JSON parse, raising on any
        HTTP or network failure (the caller decides what that means)."""
        url = ("%s?latitude=%s&longitude=%s"
               "&current=temperature_2m,weather_code,is_day"
               "&daily=temperature_2m_max,temperature_2m_min"
               "&timezone=%s&forecast_days=1"
               % (WX_URL, self._lat, self._lon, self._tz.replace("/", "%2F")))
        r = urequests.get(url)
        if r.status_code != 200:
            raise RuntimeError("weather http %d" % r.status_code)
        return ujson.loads(r.content)
