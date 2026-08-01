#!/usr/bin/env python3
"""Download full tables from VizieR/HEASARC/IRSA TAP services. Paginate by RA range for giant tables."""
import urllib.request, urllib.parse, json, ssl, time, os, sys

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

TAP_CONFIGS = {
    "vizier": {
        "url": "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync",
        "params": "request=doQuery&lang=ADQL&format=json",
        "max_top": 200000,
        "ra_col": "RAJ2000",
    },
    "heasarc": {
        "url": "https://heasarc.gsfc.nasa.gov/xamin/vo/tap",  
        "params": "REQUEST=doQuery&LANG=ADQL&FORMAT=json",
        "max_top": 100000,
        "ra_col": "ra",
    },
    "irsa": {
        "url": "https://irsa.ipac.caltech.edu/TAP/sync",
        "params": "REQUEST=doQuery&LANG=ADQL&FORMAT=json",
        "max_top": 100000,
        "ra_col": "ra",
    },
}

def tap_query(service, query, timeout=120):
    cfg = TAP_CONFIGS[service]
    url = f"{cfg['url']}?{cfg['params']}&QUERY={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent":"omegaflow/1.0"})
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            return json.loads(r.read())
        except Exception as e:
            if attempt == 2: raise
            time.sleep(3)

def download_table(service, table_id, max_rows=None):
    cfg = TAP_CONFIGS[service]
    
    # Get columns
    d = tap_query(service, f'SELECT TOP 1 * FROM "{table_id}"', timeout=30)
    if not d or "metadata" not in d:
        print(f"  no metadata", flush=True)
        return None
    cols = [m["name"] for m in d["metadata"]]
    ra_col = cfg["ra_col"]
    if ra_col not in cols:
        # Try alternative RA column names
        for alt in ["RAJ2000","_RA","ra_epoch","s_ra"]:
            if alt in cols:
                ra_col = alt
                break
    
    col_str = ",".join(f'"{c}"' for c in cols)
    
    # Try single query first
    d = tap_query(service, f'SELECT TOP {cfg["max_top"]} {col_str} FROM "{table_id}"', timeout=60)
    if not d or "data" not in d:
        print(f"  query failed", flush=True)
        return None
    rows = d["data"]
    
    if len(rows) < cfg["max_top"]:
        # Fits in one query
        out = [{cols[i]: r[i] for i in range(min(len(cols), len(r)))} for r in rows]
        print(f"  single query: {len(out)} rows", flush=True)
        return out
    
    # Giant table — paginate by RA range
    print(f"  >= {cfg['max_top']} rows — paginating by {ra_col}", flush=True)
    all_rows = []
    lo, step, hi_max = 0, 5, 365 if ra_col.startswith("_") else 360
    while lo < hi_max:
        hi = min(lo + step, hi_max)
        q = f'SELECT {col_str} FROM "{table_id}" WHERE {ra_col} >= {lo} AND {ra_col} < {hi}'
        try:
            d = tap_query(service, q, timeout=60)
            chunk = d["data"] if d and "data" in d else []
            all_rows.extend(chunk)
            if len(all_rows) % 50000 == 0:
                print(f"    [{lo},{hi}): {len(all_rows)} total", flush=True)
        except Exception as e:
            print(f"    [{lo},{hi}) failed: {e}", flush=True)
        lo = hi
        time.sleep(0.3)
    
    out = [{cols[i]: r[i] for i in range(min(len(cols), len(r)))} for r in all_rows]
    print(f"  paginated: {len(out)} rows", flush=True)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: tap_downloader.py <service> <table_id> [max_rows]")
        print(f"  Services: {list(TAP_CONFIGS.keys())}")
        sys.exit(1)
    service = sys.argv[1]
    table = sys.argv[2]
    max_rows = int(sys.argv[3]) if len(sys.argv) > 3 else None
    os.makedirs("data", exist_ok=True)
    rows = download_table(service, table, max_rows)
    if rows:
        fn = f"data/tap_{service}_{table.replace('/','_').replace('+','plus')}.json"
        with open(fn, "w") as f:
            json.dump(rows, f)
        print(f"Saved {fn} ({len(rows)} rows, {os.path.getsize(fn)//1024}KB)", flush=True)
