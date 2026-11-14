"""The "where" map (CLAUDE.md 3.4, 4.5, 4.6): one trend test per grid cell, Benjamini-Hochberg FDR across the grid,
and The Twist (same variable, significant trends of opposite sign).

Grid: POWER monthly series at every point of a regular lat/lon grid (default 29-34 N, 34-40 E, 0.5 deg). A grid point is
treated as a cell CENTRE. Each cell uses exactly the same test as a witness (stats.trend: de-seasonalised monthly
anomalies, Hamed-Rao with the 12-lag cap; Sen's slope and total change on annual means).
FDR family = every tested cell of the prefetched grid, per variable (a bbox query only filters what is returned)."""
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import cache, gazetteer, stats
from .config import CACHE_DIR, CASES, GRID_BBOX, GRID_STEP, LAST_FULL_YEAR, START_YEAR
from .sources import power
from .variables import VARIABLES

RESULTS_DIR = CACHE_DIR / "grid_results"
GRID_VARIABLES = ["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN"]  # POWER monthly columns
ALPHA = 0.05
VERSION = "v1"


def display_unit(variable: str) -> str:
    """Temperatures in °C; everything else as % change relative to the cell's own first-decade mean (comparable across cells)."""
    return "°C" if variable in ("T2M", "T2M_MAX") else "%"


def axis(lo: float, hi: float, step: float):
    return [round(float(x), 4) for x in np.arange(lo, hi + step / 2, step)]


def points(bbox_snwe=GRID_BBOX, step=GRID_STEP):
    south, west, north, east = bbox_snwe
    return [(la, lo) for la in axis(south, north, step) for lo in axis(west, east, step)]


def point_key(lat: float, lon: float) -> str:
    return f"power_monthly_{lat:.2f}_{lon:.2f}_{START_YEAR}_{LAST_FULL_YEAR}"


# ---- fetching (resumable) -------------------------------------------------------------------------------------
def prefetch_points(workers: int = 3, bbox_snwe=GRID_BBOX, step=GRID_STEP, log=print):
    """Fetch + cache POWER monthly for every grid point. Resumable: cached points are skipped."""
    pts = points(bbox_snwe, step)
    todo = [p for p in pts if cache.load_df(point_key(*p)) is None]
    log(f"grid: {len(pts)} points, {len(pts) - len(todo)} cached, {len(todo)} to fetch")
    failed = []

    def one(p):
        power.monthly(*p)
        return p

    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(one, p): p for p in todo}
        for n, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                failed.append(futs[f])
                log(f"  point {futs[f]} failed: {str(e)[:90]}")
            if n % 10 == 0 or n == len(todo):
                log(f"  grid fetch {n}/{len(todo)}")
    log(f"grid: fetched, {len(failed)} failed" + (" (re-run to resume)" if failed else ""))
    return failed


def n_cached(bbox_snwe=GRID_BBOX, step=GRID_STEP) -> int:
    """How many grid points are cached (file-exists check only: cheap, used as the result-cache signature)."""
    return sum(1 for p in points(bbox_snwe, step) if (CACHE_DIR / f"{point_key(*p)}.parquet").exists())


def fetched_date(bbox_snwe=GRID_BBOX, step=GRID_STEP) -> str:
    meta = cache._meta()                    # read once, not once per point
    dates = [meta.get(point_key(*p), {}).get("fetched") for p in points(bbox_snwe, step)]
    dates = [d for d in dates if d]
    return max(dates)[:10] if dates else ""


_MEM: dict = {}   # variable -> (result file mtime, result): avoids re-parsing the JSON on every request


# ---- per-cell tests + FDR -------------------------------------------------------------------------------------
def _cell(variable: str, lat: float, lon: float):
    df = cache.load_df(point_key(lat, lon))
    if df is None:
        return None
    try:
        tr = stats.trend(df[VARIABLES[variable]["col"]], seasonal=True)
    except stats.TooShort:      # e.g. soil moisture over the sea is all NaN: no test, no cell
        return None
    pct = display_unit(variable) == "%"
    if pct and abs(tr.baseline) < 1e-9:
        return None
    conv = (lambda v: v / tr.baseline * 100.0) if pct else (lambda v: v)
    return {"lat": lat, "lon": lon, "p": tr.p, "value": tr.pct_change if pct else tr.total_change,
            "annual": {a["year"]: conv(a["value"]) for a in tr.annual}}


def compute(variable: str, refresh: bool = False) -> dict:
    """Test every cell, BH-correct across cells, cache. -> {"variable","years","cells":[...],"n_tested","fetched"}"""
    if variable not in GRID_VARIABLES:
        raise KeyError(variable)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    f = RESULTS_DIR / f"{variable}_{VERSION}.json"
    sig = n_cached()
    if f.exists() and not refresh:
        mt = f.stat().st_mtime_ns
        hit = _MEM.get(variable)
        if hit and hit[0] == mt and hit[1].get("points_used") == sig:
            return hit[1]
        res = json.loads(f.read_text("utf-8"))
        if res.get("points_used") == sig:
            _MEM[variable] = (mt, res)
            return res
    raw = [c for c in (_cell(variable, la, lo) for la, lo in points()) if c]
    if not raw:
        raise RuntimeError("no grid data cached: run `python prefetch.py --grid`")
    years = sorted(set.intersection(*[set(c["annual"]) for c in raw]))     # years present in every cell (slider axis)
    reject, q = stats.benjamini_hochberg([c["p"] for c in raw], ALPHA)
    cells = []
    for c, qq in zip(raw, q):
        significant = bool(qq < ALPHA)
        cells.append({"lat": c["lat"], "lon": c["lon"], "value": stats.sig(c["value"]), "p": stats.sig(c["p"]),
                      "q": stats.sig(float(qq)), "significant": significant,
                      "verdict": "CONFIRMED" if significant else "NOT PROVEN",
                      "series": [stats.sig(c["annual"][y]) if c["annual"][y] != 0 else 0.0 for y in years]})
    res = {"variable": variable, "years": years, "cells": cells, "n_tested": len(cells), "points_used": sig,
           "fetched": fetched_date()}
    f.write_text(json.dumps(res), "utf-8")
    _MEM[variable] = (f.stat().st_mtime_ns, res)
    return res


def compute_all(refresh: bool = False, log=print):
    for v in GRID_VARIABLES:
        r = compute(v, refresh)
        log(f"grid {v:18s} {r['n_tested']} cells tested, {sum(c['significant'] for c in r['cells'])} significant after BH-FDR")


# ---- API shapes --------------------------------------------------------------------------------------------------
def words(variable: str) -> dict:
    from .case_builder import PHRASE
    up, down = PHRASE[variable]
    return {"up": up, "down": down}


def grid_response(variable: str, bbox_wsen=None) -> dict:
    res = compute(variable)
    south, west, north, east = GRID_BBOX
    w, s, e, n = bbox_wsen or (west, south, east, north)
    cells = [{k: c[k] for k in ("lat", "lon", "value", "q", "significant", "verdict", "series")} for c in res["cells"]
             if w <= c["lon"] <= e and s <= c["lat"] <= n]
    return {"variable": variable, "label": VARIABLES[variable]["label"], "display_unit": display_unit(variable),
            "words": words(variable), "bbox": [w, s, e, n], "step": GRID_STEP, "years": res["years"], "cells": cells,
            "fdr": "benjamini-hochberg", "data_label": {"origin": "cache", "fetched": res["fetched"]}}


def _fmt(v: float, unit: str) -> str:
    return f"{v:+.1f} °C" if unit == "°C" else f"{v:+.0f}%"


def _nearest_name(lat: float, lon: float, max_km: float = 45.0) -> str:
    best, bd = None, 1e9
    for en, ar, la, lo in gazetteer.PLACES:
        d = math.hypot((la - lat) * 111.0, (lo - lon) * 111.0 * math.cos(math.radians(lat)))
        if d < bd:
            best, bd = en, d
    return best if best and bd <= max_km else f"{lat:.1f}°N, {lon:.1f}°E"


def case_place(case_id: str):
    """(name, lat, lon) for a demo case id or a custom_<lat>_<lon> id; None if unknown."""
    if case_id in CASES:
        c = CASES[case_id]
        return c["name"], c["lat"], c["lon"]
    if case_id.startswith("custom_"):
        try:
            _, la, lo = case_id.split("_")
            return f"{float(la):.2f}°N, {float(lo):.2f}°E", float(la), float(lo)
        except ValueError:
            return None
    return None


def _score(q: float) -> float:
    return -math.log10(max(q, 1e-300))


def twist(case_id: str):
    """Strongest same-variable pair: `a` = the grid cell of the case place, `b` = a cell elsewhere whose trend is significant
    (BH-FDR) with the OPPOSITE sign. Ranked by the weaker of the two q-values (unit-free). None if there is no such pair."""
    cp = case_place(case_id)
    if cp is None:
        return None
    name, lat, lon = cp
    best = None
    for variable in GRID_VARIABLES:
        res = compute(variable)
        cells = res["cells"]
        a = min(cells, key=lambda c: (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2)
        if not a["significant"] or a["value"] == 0:
            continue
        for b in cells:
            if b is a or not b["significant"] or b["value"] * a["value"] >= 0:
                continue
            score = (min(_score(a["q"]), _score(b["q"])), abs(a["value"] - b["value"]))
            if best is None or score > best[0]:
                best = (score, variable, a, b, res)
    if best is None:
        return {"found": False}
    _, variable, a, b, res = best
    unit, wd = display_unit(variable), words(variable)
    side = lambda c, nm: {"name": nm, "lat": c["lat"], "lon": c["lon"], "value": c["value"], "display_unit": unit,  # noqa: E731
                          "p": c["p"], "verdict": c["verdict"]}
    sa, sb = side(a, name), side(b, _nearest_name(b["lat"], b["lon"]))
    pos, neg = (sa, sb) if a["value"] > 0 else (sb, sa)
    sentence = (f"{VARIABLES[variable]['label']}: {wd['up']} near {pos['name']} ({_fmt(pos['value'], unit)}) but "
                f"{wd['down']} near {neg['name']} ({_fmt(neg['value'], unit)}); both survive the false-discovery-rate check.")
    return {"found": True, "variable": variable, "label": VARIABLES[variable]["label"], "words": wd, "a": sa, "b": sb,
            "sentence": sentence, "data_label": {"origin": "cache", "fetched": res["fetched"]}}
