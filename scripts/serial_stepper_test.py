#!/usr/bin/env python3
"""
Simple serial test harness for SentryBOT Arduino stepper PID using NDJSON commands.
Sends commands, sweeps target speeds, logs pid_status responses to CSV.

Requires: pyserial
pip install pyserial

Usage example:
    python scripts/serial_stepper_test.py --port COM4 --baud 115200 --id 0 --start 10 --stop 200 --step 10 --log pid_log.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.arduino_serial.contract import (  # noqa: E402
    build_pid_enable_cmd,
    build_pid_set_cmd,
    build_pid_status_cmd,
)


def _send(ser, payload: dict) -> None:
    ser.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))


def _read_line(ser, timeout: float = 1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        line = ser.readline()
        if line:
            try:
                return line.decode("utf-8").strip()
            except UnicodeDecodeError:
                return line
    return None


def main(argv: Optional[List[str]] = None) -> int:
    import serial

    parser = argparse.ArgumentParser(description="SentryBOT Arduino stepper PID serial sweep test")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--id", type=int, default=0)
    parser.add_argument("--start", type=float, default=10.0)
    parser.add_argument("--stop", type=float, default=100.0)
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--dwell", type=float, default=3.0, help="seconds to wait after setting target")
    parser.add_argument("--log", default="pid_log.csv")
    args = parser.parse_args(argv)

    ser = serial.Serial(args.port, args.baud, timeout=1)
    try:
        time.sleep(0.2)
        ser.reset_input_buffer()

        with open(args.log, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["timestamp_ms", "id", "target", "measured", "stalled", "raw"])

            _send(ser, build_pid_enable_cmd(args.id, True))
            time.sleep(0.2)

            v = args.start
            while v <= args.stop:
                _send(ser, build_pid_set_cmd(args.id, target=v))
                time.sleep(max(0.0, args.dwell))
                _send(ser, build_pid_status_cmd(args.id))
                line = _read_line(ser, 2.0)
                ts = int(time.time() * 1000)
                if line is None:
                    writer.writerow([ts, args.id, v, "", "timeout", ""])
                    print("No response for target", v)
                else:
                    measured = ""
                    stalled = ""
                    try:
                        parsed = json.loads(line)
                        measured = parsed.get("measured", "")
                        stalled = parsed.get("stalled", "")
                    except Exception:
                        pass
                    writer.writerow([ts, args.id, v, measured, stalled, line])
                    print(ts, "->", line)
                v += args.step
    finally:
        # Always zero motor target and disable PID before closing serial port
        try:
            _send(ser, build_pid_set_cmd(args.id, target=0))
            _send(ser, build_pid_enable_cmd(args.id, False))
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass

    print("Log written to", args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
