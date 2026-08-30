#!/usr/bin/env python3
"""Read RFID lines from Arduino serial and call the Gold Miner Slots Pi API."""

from __future__ import annotations

import argparse
import sys
import time

import requests
import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial-port", required=True, help="Example: /dev/ttyACM0, /dev/ttyUSB0, or COM4")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="Pi server base URL")
    parser.add_argument("--pairing-code", help="Optional 4-digit code; if set, the next card links to that player")
    args = parser.parse_args()

    with serial.Serial(args.serial_port, 115200, timeout=1) as port:
        print(f"Listening on {args.serial_port}. Press Ctrl+C to stop.")
        time.sleep(2)
        while True:
            raw = port.readline().decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            print(raw)
            if not raw.startswith("RFID:"):
                continue

            uid = raw.split(":", 1)[1].strip()
            try:
                if args.pairing_code:
                    result = requests.post(
                        f"{args.server}/api/pair-rfid",
                        json={"code": args.pairing_code, "rfid_uid": uid},
                        timeout=5,
                    )
                else:
                    result = requests.get(f"{args.server}/api/rfid/{uid}", timeout=5)
                print(result.status_code, result.json())
            except Exception as exc:
                print(f"API error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
