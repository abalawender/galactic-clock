#!/usr/bin/env python3
"""Run the actual main.py fully mocked and capture what the matrix would show.

Mocks sit at the hardware/internet/time boundary — galactic (incl. gu.light()),
picographics, machine.ADC,
network, ntptime, urequests, ujson, secrets, time, and the Pimoroni sensor
modules (pimoroni_i2c, breakout_scd41, frozen into the board firmware) —
which is stable, so the
real app code (screens, rotation loop, state) from any git ref runs
unchanged. Frames are captured from every gu.update(). If the ref has its own
src/render.py, that version is loaded as the `render` module, so each side is
self-consistent. Nothing app-level is hard-coded here, which is what makes
this robust to significant screen changes.

    python3 sim/run_main.py --ref main --seconds 18 --gif /tmp/rot.gif
    python3 sim/run_main.py --seconds 18 --gif /tmp/rot_head.gif   # current tree

before_after.py uses run_at()/run_current() for its "rotation" pseudo-screen.
The canned weather below is a fixed sample — the real secrets.py (location,
WiFi) is never read.
"""
import argparse
import functools
import json
import os
import subprocess
import sys
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import sim as simmod  # noqa: E402
import render as _render  # noqa: E402
from gif import write_gif  # noqa: E402

W, H = 53, 11

CANNED_WX = {
    "current": {"temperature_2m": 21.3, "weather_code": 61},
    "daily": {"temperature_2m_max": [25.4], "temperature_2m_min": [17.6]},
}
CANNED_CO2 = 812  # ppm reported by the mocked SCD41 (tests override)
CANNED_LIGHT = 2048.0  # gu.light() raw 0..4095 (tests override)
SYNCED_EPOCH = 1793972928.0  # pretend NTP fixed the RTC to this
WIFI_OK = True  # tests can set False to simulate a failed wifi connect
BOOT_EPOCH = 1700000000.0  # RTC epoch at boot, before any NTP sync (2023; tests
# can set SYNCED_EPOCH to simulate a soft reset that kept the RTC running)


class FakePimoroniI2C:
    def __init__(self, *a, **k):
        pass

    def scan(self):
        return [0x62]  # SCD41 present


class FakeWLAN:
    connect_calls = 0  # wifi connect attempts (boot + retries); tests reset

    def active(self, on):
        pass

    def connect(self, ssid, pw):
        FakeWLAN.connect_calls += 1

    def isconnected(self):
        return WIFI_OK

    def ifconfig(self):
        return ("192.168.1.42", "255.255.255.0", "192.168.1.1", "1.1.1.1")


class FakeSCD41:
    """Canned SCD41: CANNED_CO2 ppm, 21.5 C, 45 %RH, always ready. Last instance
    is kept on the class so tests can introspect what main.py configured."""
    last = None

    def __init__(self, i2c, address=0x62):
        FakeSCD41.last = self
        self.altitude_m = None

    def start(self):
        pass

    def set_sensor_altitude(self, alt):
        self.altitude_m = alt

    def ready(self):
        return True

    def measure(self):
        return CANNED_CO2, 21.5, 45.0


class _Stop(BaseException):
    # BaseException so the app's own `except Exception` (resilient loop)
    # doesn't swallow the harness stop signal
    pass


class FakeChannel:
    """Records alarm beeps so tests can assert on them."""
    # waveform constants, same values as the board's galactic.Channel
    WAVE, SINE, TRIANGLE, SAW, SQUARE, NOISE = 1, 8, 16, 32, 64, 128
    beeps = 0

    def configure(self, **kw):
        pass

    def trigger_attack(self):
        FakeChannel.beeps += 1

    def trigger_release(self):
        pass


def _git_show(ref, path):
    r = subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def run_main_src(src, seconds, render_src=None, capture_func=None,
                 capture_out=None):
    """Exec one main.py source with all externals mocked; return frame list.

    If capture_func is given (e.g. "draw_weather"), every call of that
    render.* function appends a copy of the bitmap to capture_out — i.e. the
    exact screen the ref's own main.py drew, with its own frame argument.
    """
    state = {"t": BOOT_EPOCH, "start": None}
    real_time = sys.modules.get("time")

    fake_time = types.ModuleType("time")
    # this MicroPython build's time.time() returns int seconds — the mock must
    # too, or int(time.time()*3) advances differently than on the real board
    # (jumps of 3 per second, which is what made rain appear to fall upwards)
    fake_time.time = lambda: int(state["t"])
    fake_time.ticks_ms = lambda: int(state["t"] * 1000) % (1 << 30)
    fake_time.localtime = lambda t=None: real_time.gmtime(
        state["t"] if t is None else t)

    def _sleep(s):
        if state["start"] is None:
            state["start"] = state["t"]
        state["t"] += s
        if state["t"] - state["start"] >= seconds:
            raise _Stop()

    fake_time.sleep = _sleep

    # boot is its own animation (exported via the 'boot' screen), not part of
    # the rotation: don't record frames while a draw_boot call is in progress
    booting = {"on": False}

    class FakeGu:
        WIDTH, HEIGHT = W, H

        def __init__(self):
            self.frames = []

        def update(self, d):
            if not booting["on"]:
                self.frames.append([row[:] for row in d.fb])

        def clear(self):
            pass

        def light(self):
            return CANNED_LIGHT  # raw 0..4095 float, like the board

        def synth_channel(self, ch):
            return FakeChannel()

        def play_synth(self):
            pass

        def stop_playing(self):
            pass

    machine = types.ModuleType("machine")

    class FakeADC:
        # canned read_u16: ch4 -> ~24.3 C die temp, ch29 (VSYS/3) -> ~5.0 V
        READINGS = {4: 14117, 29: 33008}

        def __init__(self, ch):
            self.ch = ch

        def read_u16(self):
            return FakeADC.READINGS.get(self.ch, 0)

    machine.ADC = FakeADC

    galactic = types.ModuleType("galactic")
    galactic.GalacticUnicorn = FakeGu
    picographics = types.ModuleType("picographics")
    picographics.DISPLAY_GALACTIC_UNICORN = 0
    picographics.PicoGraphics = lambda display=0: simmod.SimGraphics(W, H)

    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda iface: FakeWLAN()

    ntptime = types.ModuleType("ntptime")
    # the RTC jump must not count against the virtual run budget — reset the
    # clock reference so _Stop measures from after the sync
    ntptime.settime = mock.Mock(
        side_effect=lambda: state.update(t=SYNCED_EPOCH, start=None))

    class FakeResp:
        status_code = 200
        content = json.dumps(CANNED_WX).encode()

    urequests = types.ModuleType("urequests")
    urequests.get = mock.Mock(side_effect=lambda url: FakeResp())
    ujson = types.ModuleType("ujson")
    ujson.loads = json.loads
    ujson.dumps = json.dumps

    secrets = types.ModuleType("secrets")
    for k in ("LOCATION_LAT", "LOCATION_LON", "TZ", "WIFI_PASSWORD", "WIFI_SSID"):
        setattr(secrets, k, "mock")
    secrets.SCD41_ALTITUDE_M = 470  # canned, like the other secrets
    secrets.TZ = "Europe/Warsaw"  # canned timezone, exercises tz.utc_offset

    pimoroni_i2c = types.ModuleType("pimoroni_i2c")
    pimoroni_i2c.PimoroniI2C = FakePimoroniI2C
    breakout_scd41 = types.ModuleType("breakout_scd41")
    breakout_scd41.BreakoutSCD41 = FakeSCD41

    stubs = {"time": fake_time, "galactic": galactic,
             "picographics": picographics, "secrets": secrets,
             "network": network, "ntptime": ntptime,
             "urequests": urequests, "ujson": ujson, "machine": machine,
             "pimoroni_i2c": pimoroni_i2c, "breakout_scd41": breakout_scd41}
    rmod = _render
    if render_src is not None:
        rmod = types.ModuleType("render_at_ref")
        exec(compile(render_src, "render.py@ref", "exec"), rmod.__dict__)
        stubs["render"] = rmod
    # mark the boot phase: wrap every draw_* so FakeGu.update can skip those
    # frames (tolerant of refs whose render.py has no draw_boot)
    for name in [n for n in vars(rmod) if n.startswith("draw_")]:
        fn = getattr(rmod, name)

        def make(n, f):
            @functools.wraps(f)  # keep signature: render_icons detects is_day via inspect
            def wrapped(d, *a, **k):
                booting["on"] = (n == "draw_boot")
                return f(d, *a, **k)
            return wrapped
        setattr(rmod, name, make(name, fn))
    orig = None
    if capture_func is not None:
        orig = getattr(rmod, capture_func, None)
        if orig is not None:
            @functools.wraps(orig)
            def wrapper(d, *a, _orig=orig, **k):
                _orig(d, *a, **k)
                capture_out.append([row[:] for row in d.fb])
            setattr(rmod, capture_func, wrapper)

    # patch.dict swaps the stub modules in and restores them atomically,
    # even if the app code raises
    try:
        with mock.patch.dict(sys.modules, stubs):
            g = {"__name__": "__main__"}
            try:
                exec(compile(src, "main.py", "exec"), g)
            except _Stop:
                pass
    finally:
        if orig is not None:
            setattr(rmod, capture_func, orig)
    # the app really did go through the mocked internet (+ RTC sync if wifi ok)
    assert urequests.get.called, "main.py never fetched weather"
    if WIFI_OK:
        assert ntptime.settime.called, "main.py never synced the RTC"
    assert "api.open-meteo.com" in urequests.get.call_args[0][0]
    return g["gu"].frames


def run_at(ref, seconds):
    """Frames from main.py (+ its own render.py) as of git ref; None if absent."""
    src = _git_show(ref, "main.py")
    if src is None:
        return None
    return run_main_src(src, seconds, render_src=_git_show(ref, "src/render.py"))


def run_current(seconds):
    """Frames from the working-tree main.py (its `import render` resolves normally)."""
    with open(os.path.join(REPO, "main.py")) as fh:
        src = fh.read()
    return run_main_src(src, seconds)


def run_screen_at(ref, func, seconds):
    """Bitmaps of each render.<func> call while running ref's real main.py.

    Returns None if the ref has no main.py or never called the function.
    """
    src = _git_show(ref, "main.py")
    if src is None:
        return None
    out = []
    run_main_src(src, seconds, render_src=_git_show(ref, "src/render.py"),
                 capture_func=func, capture_out=out)
    return out or None


def run_screen_current(func, seconds):
    """Same as run_screen_at but for the working tree."""
    with open(os.path.join(REPO, "main.py")) as fh:
        src = fh.read()
    out = []
    run_main_src(src, seconds, capture_func=func, capture_out=out)
    return out or None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default=None,
                    help="git ref to run (default: current working tree)")
    ap.add_argument("--seconds", type=float, default=18.0,
                    help="virtual seconds to run the main loop")
    ap.add_argument("--gif", default=None, help="write an animated GIF here")
    ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.15)
    args = ap.parse_args()

    frames = run_at(args.ref, args.seconds) if args.ref else run_current(args.seconds)
    if frames is None:
        raise SystemExit("no main.py at ref %s" % args.ref)
    print("captured %d frames over %.1f virtual seconds" % (len(frames), args.seconds))
    if args.gif:
        write_gif(frames, args.gif, scale=args.scale,
                  delay_ms=int(args.delay * 1000))
        print("wrote gif: %s" % args.gif)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
