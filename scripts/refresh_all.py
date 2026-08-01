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
    """Fetch latest observations for each NDBC buoy. Individual text files per buoy."""
    changed = False
    for buoy_id in NDBC_BUOYS:
        url = f"https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt"
        status, body = fetch(url)
        if status == 200 and body:
            changed |= save_if_changed(f"ndbc_{buoy_id}", {"text": body.decode(errors="replace")})
        else:
            print(f"  NDBC {buoy_id}: HTTP {status} or empty")
        time.sleep(0.5)
    return changed


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
    ("iss", "-125544"),
    ("voyager1", "-31"),
    ("voyager2", "-32"),
    ("juno", "-61"),
    ("parker_solar_probe", "-96"),
    ("new_horizons", "-98"),
    ("jwst", "-170"),
    ("solar_orbiter", "-144"),
    ("ceres", "Ceres"),
    ("vesta", "Vesta"),
    ("eris", "136199"),
    ("haumea", "136108"),
    ("makemake", "136472"),
    ("apophis", "99942"),
    ("bennu", "DES=2101955"),
    ("halley", "90000001"),
    ("encke", "90000031"),
    ("interstellar_3i", "3I"),
    ("comet_c2023_a3", "DES=C/2023 A3"),
]

# Orbit trace bodies (full year ephemeris)
ORBIT_BODIES = [
    ("sun", "10"),
    ("mercury", "199"),
    ("venus", "299"),
    ("earth", "399"),
    ("moon", "301"),
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
    ("ceres", "Ceres"),
    ("vesta", "Vesta"),
    ("eris", "136199"),
    ("haumea", "136108"),
    ("makemake", "136472"),
]

# Observer queries (Earth-based view of outer planets)
OBSERVER_BODIES = [
    ("jupiter", "599"),
    ("mars", "499"),
    ("saturn", "699"),
]

# Mass queries
MASS_BODIES = {
    "earth": "399",
    "jupiter": "599",
    "mars": "499",
    "mercury": "199",
    "neptune": "899",
    "saturn": "699",
    "uranus": "799",
    "venus": "299",
}

# Apophis elements
ELEMENTS_BODIES = [
    ("apophis", "99942"),
]


def refresh_horizons():
    """Fetch JPL Horizons vectors for solar system bodies. Individual files per body.
    Sequential with 2s delay (JPL rate limit: ~30 req/min)."""
    from urllib.parse import quote
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    changed = False
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
            changed |= save_if_changed(f"horizons_{name}", data)
        else:
            print(f"  {name}: FAILED")
        time.sleep(2)
    return changed  # return True if any body changed


# ─── JPL FIREBALLS + CLOSE APPROACH ───────────────────────────

def refresh_jpl():
    """Fetch JPL fireball and close-approach data."""
    fireball = fetch_json("https://ssd-api.jpl.nasa.gov/fireball.api?limit=100&sort=date")
    cad = fetch_json(f"https://ssd-api.jpl.nasa.gov/cad.api?dist-max=10LD&limit=200")
    changed = False
    if fireball:
        changed |= save_if_changed("jpl_fireball", {"fireball": fireball})
    if cad:
        changed |= save_if_changed("jpl_cad", {"cad": cad})
    return changed


# ─── SWPC SOLAR WIND ──────────────────────────────────────────

SWPC_URLS = {
    "swpc_ace": "https://services.swpc.noaa.gov/products/ace-swepam-1-day.json",
    "swpc_dscovr": "https://services.swpc.noaa.gov/products/dscovr-1-day.json",
    "swpc_mag_1m": "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
    "swpc_plasma_1m": "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
}


def refresh_swpc():
    """Fetch SWPC solar wind data. Individual files per dataset."""
    changed = False
    for name, url in SWPC_URLS.items():
        data = fetch_json(url)
        if data:
            changed |= save_if_changed(name, data)
        else:
            print(f"  {name}: FAILED")
        time.sleep(1)
    return changed


# ─── ORBIT TRACES (full-year ephemeris) ──────────────────────

def refresh_orbits():
    from urllib.parse import quote
    year = time.strftime("%Y")
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    changed = False
    for name, command in ORBIT_BODIES:
        url = (
            f"https://ssd.jpl.nasa.gov/api/horizons.api?format=json"
            f"&COMMAND=%27{quote(command)}%27"
            f"&OBJ_DATA=%27NO%27"
            f"&MAKE_EPHEM=%27YES%27"
            f"&EPHEM_TYPE=%27VECTORS%27"
            f"&CENTER=%27500@0%27"
            f"&START_TIME=%27{quote(start)}%27"
            f"&STOP_TIME=%27{quote(end)}%27"
            f"&STEP_SIZE=%271%20d%27"
        )
        data = fetch_json(url)
        if data:
            changed |= save_if_changed(f"orbit_{name}", data)
        else:
            print(f"  {name}: FAILED")
        time.sleep(2)
    return changed


# ─── JPL MASS QUERIES ─────────────────────────────────────────

def refresh_mass():
    changed = False
    for name, command in MASS_BODIES.items():
        url = f"https://ssd.jpl.nasa.gov/api/horizons.api?format=json&COMMAND={command}&OBJ_DATA=YES"
        data = fetch_json(url)
        if data:
            changed |= save_if_changed(f"mass_{name}", data)
        else:
            print(f"  {name}: FAILED")
        time.sleep(2)
    return changed


# ─── JPL OBSERVER QUERIES ─────────────────────────────────────

def refresh_observer():
    from urllib.parse import quote
    today = time.strftime("%Y-%m-%d")
    changed = False
    for name, command in OBSERVER_BODIES:
        url = (
            f"https://ssd.jpl.nasa.gov/api/horizons.api?format=text"
            f"&COMMAND=%27{quote(command)}%27"
            f"&OBJ_DATA=%27NO%27"
            f"&MAKE_EPHEM=%27YES%27"
            f"&EPHEM_TYPE=%27OBSERVER%27"
            f"&CENTER=%27500@399%27"
            f"&START_TIME=%27{quote(today)}%27"
            f"&STOP_TIME=%27{quote(today)}%27"
            f"&STEP_SIZE=%271%20d%27"
            f"&QUANTITIES=%271,2,3,4,20%27"
        )
        status, body = fetch(url)
        if status == 200 and body and len(body) > 200:
            changed |= save_if_changed(f"observer_{name}", {"text": body.decode(errors="replace")})
        else:
            print(f"  {name}: FAILED (status={status}, size={len(body) if body else 0})")
        time.sleep(2)
    return changed


# ─── JPL ELEMENTS ────────────────────────────────────────────

def refresh_elements():
    from urllib.parse import quote
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    changed = False
    for name, command in ELEMENTS_BODIES:
        url = (
            f"https://ssd.jpl.nasa.gov/api/horizons.api?format=text"
            f"&COMMAND=%27{quote(command)}%27"
            f"&OBJ_DATA=%27YES%27"
            f"&MAKE_EPHEM=%27YES%27"
            f"&EPHEM_TYPE=%27ELEMENTS%27"
            f"&CENTER=%27@0%27"
            f"&START_TIME=%27{quote(today)}%27"
            f"&STOP_TIME=%27{quote(tomorrow)}%27"
            f"&STEP_SIZE=%271+d%27"
            f"&REF_PLANE=%27ECLIPTIC%27"
        )
        status, body = fetch(url)
        if status == 200 and body:
            changed |= save_if_changed(f"elements_{name}", {"text": body.decode(errors="replace")})
        else:
            print(f"  {name}: FAILED")
        time.sleep(2)
    return changed


# ─── MAIN ──────────────────────────────────────────────────────

MODULES = [
    ("horizons", refresh_horizons),
    ("orbits", refresh_orbits),
    ("observer", refresh_observer),
    ("mass", refresh_mass),
    ("elements", refresh_elements),
    ("jpl", refresh_jpl),
    ("ndbc", refresh_ndbc),
    ("swpc", refresh_swpc),
]

if __name__ == "__main__":
    print(f"=== omegaflow catalogs refresh {time.strftime('%Y-%m-%dT%H:%M:%SZ')} ===")
    any_changed = False
    for name, func in MODULES:
        print(f"[{name}]")
        try:
            any_changed |= func()
        except Exception as e:
            print(f"  CRASH {name}: {e}")

    print(f"\nDone. Changed: {any_changed}")
    sys.exit(0)
