#!/usr/bin/env python3
"""Minimal MicroPython host interface for the board (over USB serial).

Usage:
    python3 scripts/mp.py ls [path]              # list files on the board
    python3 scripts/mp.py exec "print(1+1)"      # run a code string (--raw for raw output)
    python3 scripts/mp.py run main.py            # run a local file on the board
    python3 scripts/mp.py put local.py /main.py  # upload a file
    python3 scripts/mp.py get /main.py [local]   # download a file

Requires: pyserial (pip install pyserial)
"""
import argparse
import ast
import os
import re
import sys
import time

import serial


def run_code(code, port="/dev/ttyACM0", baud=115200, timeout=8.0, hold=0.0) -> str:
    """Execute code on the board in paste mode; return raw REPL output.

    hold: keep the serial port open this many seconds after the output is
    collected before closing — the matrix goes dark when the host closes the
    port, so keep it open while you want to look at the result.
    """
    ser = serial.Serial(port, baud, timeout=0.2, write_timeout=2)
    time.sleep(0.5)
    ser.reset_input_buffer()
    # Ctrl-C twice: interrupt any running code, get a clean ">>>" prompt
    ser.write(b"\r\x03\x03")
    time.sleep(0.3)
    ser.read(ser.in_waiting or 1)

    # Paste mode (Ctrl-E) handles multi-line code, then Ctrl-D executes it.
    # Send in small chunks: a single large write can overflow the board's USB
    # buffer and garble the paste.
    ser.write(b"\x05")
    time.sleep(0.1)
    data = code.encode() + b"\r"
    for i in range(0, len(data), 64):
        ser.write(data[i:i + 64])
        time.sleep(0.02)
    ser.write(b"\x04")

    buf = b""
    deadline = time.time() + timeout
    seen_ok = False
    while time.time() < deadline:
        n = ser.in_waiting
        if not n:
            time.sleep(0.01)  # nothing available; don't block on a read
            continue
        chunk = ser.read(n)  # read exactly what's there
        if chunk:
            buf += chunk
            if not seen_ok and b"OK" in buf:
                seen_ok = True
                deadline = time.time() + timeout
            elif seen_ok and buf.rstrip().endswith(b">>>"):
                break
    if hold:
        time.sleep(hold)
    ser.close()
    return buf.decode(errors="replace")


def board_output(out):
    """Strip paste-mode echo/prompt, return the board's printed lines."""
    keep, in_paste = [], False
    for l in out.splitlines():
        l = l.strip("\r").rstrip()
        if l == "===":
            in_paste = False
            continue
        if l.startswith("=== "):
            in_paste = True
            continue
        if in_paste:
            continue
        if l.startswith(">>>") or l == "OK" or l.startswith("paste mode"):
            continue
        keep.append(l)
    return "\n".join(keep)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--timeout", type=float, default=15.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ls"); p.add_argument("path", nargs="?", default="/")
    p = sub.add_parser("exec"); p.add_argument("code"); p.add_argument("--raw", action="store_true")
    p = sub.add_parser("run"); p.add_argument("file")
    p = sub.add_parser("put"); p.add_argument("local"); p.add_argument("remote")
    p = sub.add_parser("get"); p.add_argument("remote"); p.add_argument("local", nargs="?")
    args = ap.parse_args()

    if args.cmd == "ls":
        out = run_code(f"import os; print(os.listdir({args.path!r}))", args.port, timeout=args.timeout)
        print(board_output(out))
    elif args.cmd == "exec":
        out = run_code(args.code, args.port, timeout=args.timeout)
        print(out if args.raw else board_output(out))
    elif args.cmd == "run":
        with open(args.file) as f:
            code = f.read()
        print(board_output(run_code(code, args.port, timeout=args.timeout)))
    elif args.cmd == "put":
        with open(args.local, "rb") as f:
            data = f.read()
        code = f"open({args.remote!r}, 'wb').write({data!r})\nprint('wrote', {args.remote!r}, len({data!r}))"
        print(board_output(run_code(code, args.port, timeout=args.timeout)))
    elif args.cmd == "get":
        out = run_code(f"print(repr(open({args.remote!r}, 'rb').read()))", args.port, timeout=args.timeout)
        m = re.search(r"^(b['\"].*)$", board_output(out), re.M)
        if not m:
            print(out)
            return 1
        data = ast.literal_eval(m.group(1))
        dest = args.local or os.path.basename(args.remote)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"saved {len(data)} bytes -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
