#!/usr/bin/env python3
"""Download Gaia DR3 stars brighter than a magnitude limit, paginating by RA.
Fits within GitHub Actions 6h limit. Uses TAP with RA-range pagination.
Saves as compact JSON {ra, dec, plx, pmra, pmdec, gmag}."""
import urllib.request, urllib.parse, json, ssl, time, os, sys

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
TAP = "https://gea.esac.esa.int/tap-server/tap/sync"

def tap(query, timeout=120, retries=5):
    url = f"{TAP}?REQUEST=doQuery&LANG=ADQL&FORMAT=json&QUERY={urllib.parse.quote(query)}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"omegaflow/1.0"})
            r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            return json.loads(r.read())
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"    retry {attempt+1}/w{wait}s: {str(e)[:50]}", flush=True)
            time.sleep(wait)
    return None

def download_mag_limit(mag_limit, ra_step=10):
    """Download all stars with phot_g_mean_mag < mag_limit, paginating by RA."""
    # Get column metadata
    d = tap('SELECT TOP 1 * FROM gaiadr3.gaia_source')
    if not d or "metadata" not in d:
        print(f"  no metadata", flush=True)
        return None
    cols = [m["name"] for m in d["metadata"]]
    # Columns we need
    needed = ["ra","dec","parallax","pmra","pmdec","phot_g_mean_mag"]
    col_str = ",".join(f'"{c}"' for c in needed)
    
    all_rows = []
    lo = 0
    while lo < 360:
        hi = lo + ra_step
        q = (f'SELECT {col_str} FROM gaiadr3.gaia_source '
             f'WHERE phot_g_mean_mag < {mag_limit} AND ra >= {lo} AND ra < {hi}')
        d = tap(q, timeout=180)
        chunk = d["data"] if d and "data" in d else []
        all_rows.extend(chunk)
        print(f"  RA[{lo},{hi}): {len(chunk)} stars, {len(all_rows)} total", flush=True)
        if not chunk and (len(all_rows) > 0 or lo > 0):
            pass  # empty RA band is fine
        lo = hi
        time.sleep(1)
    
    # Convert to compact form
    out = []
    for r in all_rows:
        row = {}
        for i, c in enumerate(needed):
            if i < len(r):
                v = r[i]
                if v is not None:
                    row[c] = float(v) if isinstance(v, (int, float, str)) else v
        out.append(row)
    
    fn = f"data/gaia_mag{mag_limit}.json"
    with open(fn, "w") as f:
        json.dump(out, f)
    print(f"Saved {fn} ({len(out)} stars, {os.path.getsize(fn)/1e6:.1f}MB)", flush=True)
    return out

if __name__ == "__main__":
    mag = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    os.makedirs("data", exist_ok=True)
    download_mag_limit(mag)
