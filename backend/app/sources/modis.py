"""MODIS MOD13Q1 NDVI via ORNL DAAC web service (no auth). Record starts Feb 2000.

The ORNL service is slow and flaky (503s, 30-80 s calls), so every chunk of dates is cached
to disk as soon as it arrives. A re-run only fetches what is missing (resumable)."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
from ..http import get
from ..config import LAST_FULL_YEAR, CACHE_DIR
from .. import cache

BASE = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
BAND = "250m_16_days_NDVI"
SCALE = 0.0001
CHUNK = 10  # the service limits dates per call
WORKERS = 4


def _dates(lat, lon):
    js = get(f"{BASE}/dates", {"latitude": lat, "longitude": lon})
    return [d["modis_date"] for d in js["dates"]]


def _chunk(lat, lon, chunk, km):
    """Fetch one chunk (cached on disk). Returns list of (calendar_date, mean NDVI)."""
    p = CACHE_DIR / "modis_chunks" / f"{lat:.2f}_{lon:.2f}_km{km}_{chunk[0]}_{chunk[-1]}.json"
    if p.exists():
        return json.loads(p.read_text())
    js = get(f"{BASE}/subset", {"latitude": lat, "longitude": lon, "band": BAND, "startDate": chunk[0],
                                "endDate": chunk[-1], "kmAboveBelow": km, "kmLeftRight": km}, retries=6)
    out = []
    for s in js.get("subset", []):
        vals = np.array(s["data"], dtype=float)
        vals[(vals < -2000) | (vals > 10000)] = np.nan  # fill value -3000 / invalid
        out.append((s["calendar_date"], float(np.nanmean(vals) * SCALE) if np.isfinite(vals).any() else None))
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out))
    return out


def _fetch(lat, lon, end_year, km=1) -> pd.DataFrame:
    dates = [d for d in _dates(lat, lon) if int(d[1:5]) <= end_year]
    chunks = [dates[i:i + CHUNK] for i in range(0, len(dates), CHUNK)]
    recs, failed = [], 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(_chunk, lat, lon, c, km): c for c in chunks}
        for n, f in enumerate(as_completed(futs), 1):
            try:
                recs += f.result()
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"   chunk {futs[f][0]}..{futs[f][-1]} failed: {str(e)[:80]}")
            if n % 5 == 0:
                print(f"   MODIS chunks {n}/{len(chunks)}", flush=True)
    if failed:
        raise RuntimeError(f"{failed}/{len(chunks)} MODIS chunks failed; re-run to resume (done chunks are cached)")
    df = pd.DataFrame(recs, columns=["date", "ndvi"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index().astype(float)
    return df.resample("MS").mean()  # monthly means


def monthly_ndvi(lat, lon, end_year=LAST_FULL_YEAR, refresh=False, km=1):
    key = f"modis_ndvi_{lat:.2f}_{lon:.2f}_{end_year}"
    df, st = cache.cached_df(key, lambda: _fetch(lat, lon, end_year, km), refresh,
                             {"url": f"{BASE}/subset?latitude={lat}&longitude={lon}&band={BAND}"})
    return df, st, key
