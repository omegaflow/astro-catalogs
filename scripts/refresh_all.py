#!/usr/bin/env python3
"""GitHub Actions cron script: refresh dynamic data from upstream APIs.
Each module fetches data, saves to data/<name>.json.
Only writes if content changed (SHA-256 hash).
"""
import json
import os
import urllib.request
import time
import sys
import hashlib

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
UA = "omegaflow-catalogs-bot/1.0"


def fetch(url, timeout=30):
    """Fetch raw bytes from URL. Returns (status, bytes) or (0, None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return 0, None


def fetch_json(url, timeout=30):
    _, data = fetch(url, timeout)
    if data:
        try:
            return json.loads(data.decode())
        except Exception:
            return None
    return None


def save_if_changed(name, data):
    """Save data to data/<name>.json only if content changed."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    new_bytes = json.dumps(data, ensure_ascii=False).encode()
    new_hash = hashlib.sha256(new_bytes).hexdigest()
    if os.path.exists(path):
        old_hash = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if old_hash == new_hash:
            print(f"  {name}: unchanged")
            return False
    with open(path, "wb") as f:
        f.write(new_bytes)
    print(f"  {name}: updated ({len(new_bytes)}B)")
    return True


# ─── NDBC BUOYS ────────────────────────────────────────────────

NDBC_BUOYS = [
    41001, 42001, 42002, 42036, 42040, 42055,
    44009, 44013, 44014, 44025,
    46001, 46002, 46005, 46006, 46012, 46013,
    46022, 46025, 46026, 46027, 46029, 46047,
    46053, 46054, 46059, 46069, 46086,
    51000, 51001, 51002, 51004,
]


def refresh_ndbc():
    """Fetch latest observations for each NDBC buoy. Returns {buoy_id: raw_text}."""
    result = {}
    for buoy_id in NDBC_BUOYS:
        url = f"https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt"
        status, body = fetch(url)
        if status == 200 and body:
            result[str(buoy_id)] = body.decode(errors="replace")
        else:
            print(f"  NDBC {buoy_id}: HTTP {status} or empty")
        time.sleep(0.5)
    return result


# ─── JPL HORIZONS VECTORS ─────────────────────────────────────

HORIZONS_BODIES = [
    ("sun", "10"),
    ("mercury", "199"),
    ("venus", "299"),
    ("earth", "399"),
    ("luna", "301"),
    ("mars", "499"),
    ("jupiter", "599"),
    ("io", "501"),
    ("europa", "502"),
    ("ganymede", "503"),
    ("callisto", "504"),
    ("saturn", "699"),
    ("titan", "606"),
    ("enceladus", "602"),
    ("uranus", "799"),
    ("neptune", "899"),
    ("triton", "801"),
    ("pluto", "999"),
]


def refresh_horizons():
    """Fetch JPL Horizons vectors for solar system bodies. Sequential with 2s delay."""
    result = {}
    # Today to tomorrow for daily ephemeris
    from urllib.parse import quote
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    for name, command in HORIZONS_BODIES:
        url = (
            f"https://ssd.jpl.nasa.gov/api/horizons.api?format=json"
            f"&COMMAND=%27{quote(command)}%27"
            f"&OBJ_DATA=%27NO%27"
            f"&MAKE_EPHEM=%27YES%27"
            f"&EPHEM_TYPE=%27VECTORS%27"
            f"&CENTER=%27500@0%27"
            f"&START_TIME=%27{quote(today)}%27"
            f"&STOP_TIME=%27{quote(tomorrow)}%27"
            f"&STEP_SIZE=%271%20d%27"
        )
        data = fetch_json(url)
        if data:
            result[name] = data
            print(f"  {name}: OK")
        else:
            print(f"  {name}: FAILED")
        time.sleep(2)  # JPL rate limit: ~30 req/min
    return result


# ─── JPL FIREBALLS + CLOSE APPROACH ───────────────────────────

def refresh_jpl():
    """Fetch JPL fireball and close-approach data for today."""
    fireball = fetch_json("https://ssd-api.jpl.nasa.gov/fireball.api?limit=100&sort=date")
    cad = fetch_json(f"https://ssd-api.jpl.nasa.gov/cad.api?dist-max=10LD&limit=200")
    return {"fireball": fireball, "cad": cad}


# ─── SWPC SOLAR WIND ──────────────────────────────────────────

SWPC_URLS = {
    "swpc_ace": "https://services.swpc.noaa.gov/products/ace-swepam-1-day.json",
    "swpc_dscovr": "https://services.swpc.noaa.gov/products/dscovr-1-day.json",
    "swpc_mag_1m": "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
    "swpc_plasma_1m": "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
}


def refresh_swpc():
    """Fetch SWPC solar wind data (small, <100KB each)."""
    result = {}
    for name, url in SWPC_URLS.items():
        data = fetch_json(url)
        if data:
            result[name] = data
        else:
            print(f"  {name}: FAILED")
        time.sleep(1)
    return result


# ─── MAIN ──────────────────────────────────────────────────────

MODULES = [
    ("horizons", refresh_horizons),
    ("jpl", refresh_jpl),
    ("ndbc", refresh_ndbc),
    ("swpc", refresh_swpc),
]

if __name__ == "__main__":
    print(f"=== omegaflow catalogs refresh {time.strftime('%Y-%m-%dT%H:%M:%SZ')} ===")
    changed = False
    for name, func in MODULES:
        print(f"[{name}]")
        try:
            data = func()
            if data:
                if save_if_changed(name, data):
                    changed = True
        except Exception as e:
            print(f"  CRASH {name}: {e}")

    print(f"\nDone. Changed: {changed}")
    sys.exit(0)
