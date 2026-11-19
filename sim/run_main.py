#!/usr/bin/env python3
"""Run the actual main.py fully mocked and capture what the matrix would show.

Mocks sit at the hardware/internet/time boundary — galactic (incl. gu.light()),
picographics, machine.ADC/machine.Pin (buttons: FakePin plays a
press/release pattern for tests),
network, ntptime, urequests, ujson, secrets, time, and the Pimoroni sensor
modules (pimoroni_i2c, breakout_scd41, frozen into the board firmware) —
which is stable, so the
real app code (screens, rotation loop, state) from any git ref runs
unchanged. Frames are captured from every gu.update(). If the ref has its own
src/render.py, that version is loaded as the `render` module, so each side is
self-consistent. Nothing app-level is hard-coded here, which is what makes
this robust to significant screen changes.

Gotcha (burned once, in the co2 extraction): a host-side import of a board
module — including inside this harness — binds the REAL `time`, not the
mock, because `sys.modules` caches it outside the stub window. Any `src/`
module that needs the clock must therefore take it injected (see
`Co2Ring.sample(sensor, t)`); do not `import time` inside a `src/` service
and trust it under sim.

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
import co2 as co2mod  # noqa: E402  (real module: clock is injected, so safe here)
from gif import write_gif  # noqa: E402

W, H = 53, 11

CANNED_WX = {
    "current": {"temperature_2m": 21.3, "weather_code": 61},
    "daily": {"temperature_2m_max": [25.4], "temperature_2m_min": [17.6]},
}
CANNED_CO2 = None  # ppm pin that overrides the script below (alarm tests)
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


def _co2_script():
    """The canned SCD41 measurement script: every reading comes from
    sim.py's single co2_script_ppm() generator — one slow sine cycle,
    550..1250 ppm over ~3 h (720 readings, ~15-20 s apart; 12 = one
    3-minute ring bucket at the full cadence). One reading per sequential
    measure() call; CANNED_CO2 can pin every reading (alarm tests)."""
    return [simmod.co2_script_ppm(i) for i in range(720)]


CO2_SCRIPT = _co2_script()


class FakeSCD41:
    """Mocked SCD41 serving CO2_SCRIPT sequentially (CANNED_CO2 pins every
    reading when set). 21.5 C, 45 %RH, always ready. Last instance is kept
    on the class so tests can introspect what main.py configured."""
    last = None

    SLOT_BASE = 0  # preseeded runs start the script here (seed_co2_ring)

    def __init__(self, i2c, address=0x62):
        FakeSCD41.last = self
        self.altitude_m = None
        self.slot = FakeSCD41.SLOT_BASE

    def start(self):
        pass

    def set_sensor_altitude(self, alt):
        self.altitude_m = alt

    def ready(self):
        return True

    def measure(self):
        # board-faithful types (REPL-verified): measure() returns FLOATS,
        # so the real code's int() casts are exercised by the suite — the
        # original single-deploy ERR TYPEE lived exactly across this fork
        if CANNED_CO2 is not None:
            return float(CANNED_CO2), 21.5, 45.0
        ppm = CO2_SCRIPT[self.slot % len(CO2_SCRIPT)]
        self.slot += 1
        return float(ppm), 21.5, 45.0


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


class FakePin:
    """machine.Pin stub for the button code. The app registers an IRQ handler
    via irq(); every sleep() call in the mocked time module fires registered
    handlers when the virtual clock crosses press_at epochs — tests then
    inject presses deterministically (board buttons are active-low, the IRQ
    trigger is falling edge). value() plays press_pattern[call#] for level
    polling if any screen code reads levels."""
    press_pattern = (1,)
    press_at = ()                 # virtual epochs; one press per entry
    handlers = ()                 # handlers registered by the app
    fired = ()                    # press_at indexes already fired

    @classmethod
    def maybe_fire(cls, now):
        if not cls.handlers:
            return
        for i in cls.press_at:
            if i not in cls.fired and now >= i:
                cls.fired += (i,)
                for h in cls.handlers:
                    h(None)

    def __init__(self, *a, **k):
        self.calls = 0

    def value(self):
        p = FakePin.press_pattern
        v = p[min(self.calls, len(p) - 1)]
        self.calls += 1
        return v

    def irq(self, handler, trigger=None):
        FakePin.handlers = (handler,)  # each app run (re)registers one

    # IRQ trigger bits, same values as machine.Pin on this port
    IRQ_RISING = 4
    IRQ_FALLING = 8


def seed_co2_ring(g, n):
    """Fill main.py's co2 ring with n committed 3-minute wall-clock buckets
    — slot-aligned (ts//CO2_BUCKET_S) timestamps ending just before the
    NTP-synced epoch (main() — not module level — does the sync, so
    seeding happens after main.py's exec but before main() runs and must
    anchor on the post-sync clock). Each bucket averages the 12 scripted
    readings (~15 s apart at full cadence) it covers. The ring's own
    restore() does the storing, so the seed rides exactly the same entry
    path a live reading would. The sensor then carries on from the same
    script position: its live readings continue the history seamlessly."""
    READS_PER_BUCKET = co2mod.CO2_BUCKET_S // co2mod.CO2_INTERVAL_S
    n = min(n, len(CO2_SCRIPT) // READS_PER_BUCKET, co2mod.CO2_LOG_N)
    synced = int(SYNCED_EPOCH)
    aligned = synced - synced % co2mod.CO2_BUCKET_S  # buckets align to the wall clock
    means = [(sum(CO2_SCRIPT[READS_PER_BUCKET * k:
                                   READS_PER_BUCKET * (k + 1)])
              + READS_PER_BUCKET // 2) // READS_PER_BUCKET
             for k in range(n)]
    ts = [aligned - co2mod.CO2_BUCKET_S * (n - 1 - k) for k in range(n)]
    g["co2"].restore([(t, m) for t, m in zip(ts, means)])
    # main() constructs the sensor only when called below
    FakeSCD41.SLOT_BASE = READS_PER_BUCKET * n


def run_main_src(src, seconds, render_src=None, capture_func=None,
                 capture_out=None, out_globals=None, preseed_co2=None):
    """Exec one main.py source with all externals mocked; return frame list.

    If capture_func is given (e.g. "draw_weather"), every call of that
    render.* function appends a copy of the bitmap to capture_out — i.e. the
    exact screen the ref's own main.py drew, with its own frame argument.
    If out_globals is given, the exec'd namespace is copied into it after
    the run (a test can then inspect main.py's module state).
    """
    state = {"t": BOOT_EPOCH, "start": None}
    real_time = sys.modules.get("time")

    fake_time = types.ModuleType("time")
    # this MicroPython build's time.time() returns int seconds
    # (REPL-verified: type(time.time()) is 'int') — the mock must too, or
    # arithmetic advanced differently than on the real board once (which
    # is what made rain appear to fall upwards in an early sim)
    fake_time.time = lambda: int(state["t"])
    fake_time.ticks_ms = lambda: int(state["t"] * 1000) % (1 << 30)
    fake_time.ticks_us = lambda: int(state["t"] * 1000000) % (1 << 30)
    # MicroPython ticks_add: wraparound-aware addition in the ticks domain
    fake_time.ticks_add = lambda a, b: (a + b) % (1 << 30)
    # MicroPython ticks_diff: wraparound-aware signed difference over the
    # full ticks range (used by the button debounce)
    fake_time.ticks_diff = lambda a, b: \
        ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)
    fake_time.localtime = lambda t=None: real_time.gmtime(
        state["t"] if t is None else t)

    def _sleep(s):
        if state["start"] is None:
            state["start"] = state["t"]
        state["t"] += s
        FakePin.maybe_fire(state["t"])  # injected button presses
        if state["t"] - state["start"] >= seconds:
            raise _Stop()

    fake_time.sleep = _sleep

    # boot is its own animation (exported via the 'boot' screen), not part of
    # the rotation: don't record frames while a draw_boot call is in progress
    booting = {"on": False}

    class FakeGu:
        WIDTH, HEIGHT = W, H
        # button pins, same map as the frozen galactic firmware
        # (probed on hardware: A=0 B=1 C=3 D=6, BRI 21/26, VOL 7/8, SLEEP 27)
        SWITCH_A = 0
        SWITCH_B = 1
        SWITCH_C = 3
        SWITCH_D = 6
        SWITCH_BRIGHTNESS_UP = 21
        SWITCH_BRIGHTNESS_DOWN = 26
        SWITCH_VOLUME_UP = 7
        SWITCH_VOLUME_DOWN = 8
        SWITCH_SLEEP = 27

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

    machine.Pin = FakePin
    machine.Pin.IN = 0     # pin mode/pull constants, same numbers as the board
    machine.Pin.OUT = 1
    machine.Pin.PULL_UP = 2

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
    FakePin.fired = ()  # each app run starts with untriggered press injections
    FakeSCD41.SLOT_BASE = 0  # each run replays the script from its start
    try:
        with mock.patch.dict(sys.modules, stubs):
            # a preseed run imports main.py without launching it (the
            # __name__ guard), fills the ring with script history, then
            # calls main() under the same mocks — the rotation then
            # previews hours of history, not just the seconds it ran
            g = {"__name__": "main_preseed" if preseed_co2 else "__main__"}
            try:
                exec(compile(src, "main.py", "exec"), g)
                if preseed_co2 and "co2" in g:
                    seed_co2_ring(g, preseed_co2)
                    g["main"]()
            except _Stop:
                pass
    finally:
        if orig is not None:
            setattr(rmod, capture_func, orig)
        if out_globals is not None and "gu" in g:
            out_globals.update(g)
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


def run_current(seconds, out_globals=None, preseed_co2=None):
    """Frames from the working-tree main.py (its `import render` resolves normally)."""
    with open(os.path.join(REPO, "main.py")) as fh:
        src = fh.read()
    return run_main_src(src, seconds, out_globals=out_globals,
                        preseed_co2=preseed_co2)


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
    ap.add_argument("--preseed-co2", type=int, default=None,
                    help="preload the ring with N 3-minute bucket means "
                         "(180 s apart, one per strip column) before the "
                         "loop starts")
    args = ap.parse_args()

    frames = run_at(args.ref, args.seconds) if args.ref else run_current(
        args.seconds, preseed_co2=args.preseed_co2)
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
