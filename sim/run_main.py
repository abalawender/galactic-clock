#!/usr/bin/env python3
"""Run the actual main.py fully mocked and capture what the matrix would show.

Mocks sit at the hardware/internet/time boundary — galactic, picographics,
network, ntptime, urequests, ujson, secrets, time — which is stable, so the
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
from gif import write_gif  # noqa: E402

W, H = 53, 11

CANNED_WX = {
    "current": {"temperature_2m": 21.3, "weather_code": 61},
    "daily": {"temperature_2m_max": [25.4], "temperature_2m_min": [17.6]},
}
SYNCED_EPOCH = 1793972928.0  # pretend NTP fixed the RTC to this


class _Stop(Exception):
    pass


def _git_show(ref, path):
    r = subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def run_main_src(src, seconds, render_src=None):
    """Exec one main.py source with all externals mocked; return frame list."""
    state = {"t": 1700000000.0, "start": None}
    real_time = sys.modules.get("time")

    fake_time = types.ModuleType("time")
    fake_time.time = lambda: state["t"]
    fake_time.ticks_ms = lambda: int(state["t"] * 1000) % (1 << 30)
    fake_time.localtime = lambda: real_time.gmtime(state["t"])

    def _sleep(s):
        if state["start"] is None:
            state["start"] = state["t"]
        state["t"] += s
        if state["t"] - state["start"] >= seconds:
            raise _Stop()

    fake_time.sleep = _sleep

    class FakeGu:
        WIDTH, HEIGHT = W, H

        def __init__(self):
            self.frames = []

        def update(self, d):
            self.frames.append([row[:] for row in d.fb])

        def clear(self):
            pass

    galactic = types.ModuleType("galactic")
    galactic.GalacticUnicorn = FakeGu
    picographics = types.ModuleType("picographics")
    picographics.DISPLAY_GALACTIC_UNICORN = 0
    picographics.PicoGraphics = lambda display=0: simmod.SimGraphics(W, H)

    class FakeWLAN:
        def active(self, on):
            pass

        def connect(self, ssid, pw):
            pass

        def isconnected(self):
            return True

        def ifconfig(self):
            return ("192.168.1.42", "255.255.255.0", "192.168.1.1", "1.1.1.1")

    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda iface: FakeWLAN()

    ntptime = types.ModuleType("ntptime")
    ntptime.settime = mock.Mock(side_effect=lambda: state.update(t=SYNCED_EPOCH))

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

    stubs = {"time": fake_time, "galactic": galactic,
             "picographics": picographics, "secrets": secrets,
             "network": network, "ntptime": ntptime,
             "urequests": urequests, "ujson": ujson}
    if render_src is not None:
        rmod = types.ModuleType("render_at_ref")
        exec(compile(render_src, "render.py@ref", "exec"), rmod.__dict__)
        stubs["render"] = rmod

    # patch.dict swaps the stub modules in and restores them atomically,
    # even if the app code raises
    with mock.patch.dict(sys.modules, stubs):
        g = {"__name__": "__main__"}
        try:
            exec(compile(src, "main.py", "exec"), g)
        except _Stop:
            pass
    # the app really did go through the mocked internet + RTC sync
    assert urequests.get.called, "main.py never fetched weather"
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
