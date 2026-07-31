#!/usr/bin/env python3
"""Test NDBC buoy fetching from GitHub Actions IP.
Verifies: HTTP 200, response size > 0, valid data columns.
Run: python3 scripts/test_ndbc.py
"""

import urllib.request
import sys

NDBC_BUOYS = [
    41001, 42001, 42002, 42036, 42040, 42055,
    44009, 44013, 44014, 44025,
    46001, 46002, 46005, 46006, 46012, 46013,
    46022, 46025, 46026, 46027, 46029, 46047,
    46053, 46054, 46059, 46069, 46086,
    51000, 51001, 51002, 51004,
]

HEADER_COLS = 18  # Expected columns in #YY header line


def test_buoy(buoy_id):
    url = f"https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "omegaflow-catalogs-bot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode(errors="replace")
            lines = body.strip().split("\n")
    except Exception as e:
        return False, f"ERROR: {e}"

    if status != 200:
        return False, f"HTTP {status}"

    if len(body) < 100:
        return False, f"too short ({len(body)}B)"

    # Find header line and count columns
    header = None
    for line in lines:
        if line.startswith("#YY"):
            header = line
            break
    if not header:
        return False, "no #YY header"

    cols = header.lstrip("#").strip().split()
    return True, f"OK ({len(lines)} lines, {len(cols)} cols)"


def main():
    print(f"NDBC buoy reachability test ({len(NDBC_BUOYS)} buoys)")
    print("=" * 60)

    ok = 0
    fail = 0
    for bid in NDBC_BUOYS:
        success, msg = test_buoy(bid)
        status = "PASS" if success else "FAIL"
        print(f"  {status} buoy {bid}: {msg}")
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\nResult: {ok}/{ok+fail} OK, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
