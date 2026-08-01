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
        "quote_table": True,
    },
    "heasarc": {
        "url": "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync",
        "params": "REQUEST=doQuery&LANG=ADQL",
        "max_top": 100000,
        "ra_col": "ra",
        "quote_table": False,
        "format": "votable",
    },
    "irsa": {
        "url": "https://irsa.ipac.caltech.edu/TAP/sync",
        "params": "LANG=ADQL&FORMAT=csv",
        "max_top": 50000,
        "ra_col": "ra",
        "quote_table": False,
        "format": "csv",
    },
    "gaia": {
        "url": "https://gea.esac.esa.int/tap-server/tap/sync",
        "params": "REQUEST=doQuery&LANG=ADQL&FORMAT=json",
        "max_top": 50000,
        "ra_col": "ra",
        "quote_table": False,
    },
}

def tap_query(service, query, timeout=120):
    cfg = TAP_CONFIGS[service]
    url = f"{cfg['url']}?{cfg['params']}&QUERY={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent":"omegaflow/1.0"})
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            body = r.read()
            if cfg.get("format") == "csv":
                # Parse CSV: header line then data lines
                text = body.decode("utf-8", errors="replace")
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines: return None
                header = lines[0].split(",")
                data = []
                for ln in lines[1:]:
                    vals = ln.split(",")
                    if len(vals) == len(header):
                        data.append(vals)
                return {"metadata": [{"name": h} for h in header], "data": data}
            return json.loads(body)
        except Exception as e:
            if attempt == 2: raise
            time.sleep(3)

def download_table(service, table_id, max_rows=None):
    cfg = TAP_CONFIGS[service]
    
    # Get columns
    table_ref = f'"{table_id}"' if cfg.get("quote_table", False) else table_id
    d = tap_query(service, f'SELECT TOP 1 * FROM {table_ref}', timeout=30)
    if not d or "metadata" not in d:
        print(f"  no metadata", flush=True)
        return None
    cols = [m["name"] for m in d["metadata"]]
    ra_col = cfg["ra_col"]
    if ra_col not in cols:
        for alt in ["RAJ2000","_RA","ra_epoch","s_ra","right_ascension","raj2000"]:
            if alt in cols:
                ra_col = alt
                break
    
    col_str = ",".join(f'"{c}"' if cfg.get("quote_table", False) else c for c in cols)
    
    # Try single query first
    d = tap_query(service, f'SELECT TOP {cfg["max_top"]} {col_str} FROM {table_ref}', timeout=60)
    if not d or "data" not in d:
        print(f"  query failed", flush=True)
        return None
    rows = d["data"]
    out = [{cols[i]: r[i] for i in range(min(len(cols), len(r)))} for r in rows]
    fn = f"data/tap_{service}_{table_id.replace('/','_').replace('+','plus')}.json"
    if cfg.get("format") == "csv":
        fn = fn.replace(".json", ".csv")
        with open(fn, "w") as f:
            f.write(",".join(cols) + "\n")
            for r in rows:
                f.write(",".join(str(x) if x is not None else "" for x in r) + "\n")
    else:
        with open(fn, "w") as f:
            json.dump(out, f)
    print(f"  {len(out)} rows, {os.path.getsize(fn)//1024}KB", flush=True)
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
