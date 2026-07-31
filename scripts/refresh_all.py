#!/usr/bin/env python3
"""GitHub Actions cron script: refresh dynamic data sources.
Each module fetches data from an upstream API and saves to data/<name>.json.
Only writes if data changed from previous version.
"""
import json, os, urllib.request, time, sys, hashlib

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_json(url, headers=None, timeout=30):
    """Fetch JSON from URL, return parsed object or None."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        req.add_header('User-Agent', 'omegaflow-catalogs-bot/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f'  ERROR {url}: {e}')
        return None

def save_if_changed(name, data):
    """Save data to data/<name>.json only if content changed."""
    path = os.path.join(DATA_DIR, f'{name}.json')
    # Compute hash of current file
    old_hash = ''
    if os.path.exists(path):
        old_hash = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    # Compute hash of new data
    new_bytes = json.dumps(data).encode()
    new_hash = hashlib.sha256(new_bytes).hexdigest()
    if old_hash == new_hash:
        print(f'  {name}: unchanged')
        return False
    with open(path, 'wb') as f:
        f.write(new_bytes)
    print(f'  {name}: updated ({len(new_bytes)//1024}KB)')
    return True

def refresh_horizons():
    """Fetch JPL Horizons vectors for solar system bodies."""
    bodies = [
        ('mercury', '199'), ('venus', '299'), ('earth', '399'),
        ('mars', '499'), ('jupiter', '599'), ('saturn', '699'),
        ('uranus', '799'), ('neptune', '899'), ('pluto', '999'),
        ('sun', '10'), ('luna', '301'),
        ('callisto', '504'), ('ganymede', '503'), ('europa', '502'),
    ]
    result = {}
    for name, command in bodies:
        url = (f'https://ssd.jpl.nasa.gov/api/horizons.api?format=json'
               f'&COMMAND=%27{command}%27&OBJ_DATA=%27NO%27&MAKE_EPHEM=%27YES%27'
               f'&EPHEM_TYPE=%27VECTORS%27&CENTER=%27500%400%27'
               f'&START_TIME=%27{today}%27&STOP_TIME=%27{tomorrow}%27'
               f'&STEP_SIZE=%271+d%27')
        data = fetch_json(url)
        if data:
            result[name] = data
        time.sleep(2)  # rate limit: 2s between requests
    return result

def refresh_jpl_fireballs():
    """Fetch JPL fireball/close approach data."""
    fireball = fetch_json('https://ssd-api.jpl.nasa.gov/fireball.api?limit=100&sort=date')
    cad = fetch_json('https://ssd-api.jpl.nasa.gov/cad.api?dist-max=10LD&date-min=2026-07-31&limit=100')
    return {'fireball': fireball, 'cad': cad}

# Modules to run
MODULES = [
    ('horizons', refresh_horizons),
    ('jpl', refresh_jpl_fireballs),
    # Add more modules here:
    # ('ndbc', refresh_ndbc),
    # ('stix', refresh_stix),
]

if __name__ == '__main__':
    print(f'=== refresh {time.strftime("%Y-%m-%dT%H:%M:%SZ")} ===')
    for name, func in MODULES:
        print(f'[{name}]')
        data = func()
        if data:
            save_if_changed(name, data)
    print('Done.')
