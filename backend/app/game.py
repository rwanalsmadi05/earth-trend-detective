"""'Real or noise?' (CLAUDE.md feature 7): one round = one REAL series and its REAL verdict from stats.trend.
Nothing is simulated or labelled by hand: `verdict` is the same Hamed-Rao / Sen result a witness gets (p < 0.05).

Source of rounds, in order:
  1. the case place itself (every catalog variable that has a series there);
  2. only if the case place has no non-excluded series with the wanted verdict: other cached POWER grid cells
     (nearest first), reported with their own coordinates as `place`. Still real series, real tests.
If nothing real matches, the endpoint says so (404) and the frontend falls back to the case's own witnesses."""
import math
import random
from functools import lru_cache

from . import cache, grid, stats
from .case_builder import _headline, _ndvi_if_cached
from .config import LAST_FULL_YEAR
from .sources import power
from .variables import PLAIN, VARIABLES

ALL_VARIABLES = ["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN", "HOT_DAYS", "NDVI"]
_rng = random.Random()          # tests may replace this for determinism
NEAREST_POOL = 12               # fallback: pick randomly among the nearest matching cells


class NoRound(Exception):
    pass


@lru_cache(maxsize=1024)
def _trend_at(lat: float, lon: float, vid: str, year: int = LAST_FULL_YEAR):
    """(TrendResult, origin, fetched) for one variable at one point, or None if that variable has no series there."""
    v = VARIABLES[vid]
    if v["kind"] == "modis":
        s = _ndvi_if_cached(lat, lon)
        if s is None:
            return None
        raw, seasonal, key = s, True, f"modis_ndvi_{lat:.2f}_{lon:.2f}_{LAST_FULL_YEAR}"
        origin = "cache"
    elif v["kind"] == "power_daily":
        raw, st = power.hot_days_per_year(lat, lon)
        seasonal, key, origin = False, f"power_daily_t2mmax_{lat:.2f}_{lon:.2f}_1981_{LAST_FULL_YEAR}", ("live" if st == "fresh" else "cache")
    else:
        df, st, key = power.monthly(lat, lon)
        raw, seasonal, origin = df[v["col"]], True, ("live" if st == "fresh" else "cache")
    try:
        tr = stats.trend(raw, seasonal=seasonal)
    except stats.TooShort:
        return None
    return tr, origin, (cache.meta_for(key).get("fetched") or "")[:10]


def _explanation(vid: str, tr, place: str) -> str:
    """One plain line, built only from the computed result (same wording the frontend uses for the reveal)."""
    label = PLAIN[vid]
    p ="p < 0.0001" if tr.p < 1e-4 else f"p = {tr.p:.3f}"
    if tr.reason:
        return f"The test could not be run on this series, so nothing is proven ({label} at {place})."
    if tr.verdict == "CONFIRMED":
        h = _headline(vid, tr)
        tail = "It only just passes the bar, so it is a borderline call." if tr.borderline else "Chance alone would rarely draw a line this steady."
        return f"Real trend: {h[:1].lower()}{h[1:]} at {place} ({p}). {tail}"
    return f"Just noise, as far as the test can tell: {label} at {place} wobbles about as much as chance would make it ({p})."


def _round(vid: str, lat: float, lon: float, place_name: str, hit) -> dict:
    tr, origin, fetched = hit
    v = VARIABLES[vid]
    return {"variable": vid, "label": v["label"], "unit": v["unit"],
            "place": {"name": place_name, "lat": lat, "lon": lon},
            "period": {"start": tr.annual[0]["year"], "end": tr.annual[-1]["year"]},
            "series": tr.annual, "verdict": tr.verdict, "p": tr.p, "tau": tr.tau, "sen_per_decade": tr.sen_per_decade,
            "n": tr.n, "borderline": tr.borderline, "explanation": _explanation(vid, tr, place_name),
            "data_label": {"origin": origin, "fetched": fetched}}


def _dist(la1, lo1, la2, lo2) -> float:
    return math.hypot(la1 - la2, (lo1 - lo2) * math.cos(math.radians(la1)))


def game_round(case_id: str, want: str | None = None, exclude=()) -> dict:
    cp = grid.case_place(case_id)
    if cp is None:
        raise KeyError(case_id)
    place_name, lat, lon = cp
    skip = set(exclude)

    # 1) the case place
    pool = []
    for vid in ALL_VARIABLES:
        if vid in skip:
            continue
        try:
            hit = _trend_at(lat, lon, vid)
        except Exception:  # noqa: BLE001  (data unavailable for this place): just not a candidate
            continue
        if hit and (want is None or hit[0].verdict == want):
            pool.append((vid, hit))
    if pool:
        vid, hit = _rng.choice(pool)
        return _round(vid, lat, lon, place_name, hit)

    # 2) real series from other cached grid cells, nearest first
    cands = []
    for vid in grid.GRID_VARIABLES:
        if vid in skip:
            continue
        try:
            cells = grid.compute(vid)["cells"]
        except Exception:  # noqa: BLE001
            continue
        for c in cells:
            verdict = "CONFIRMED" if c["p"] < stats.ALPHA else "NOT PROVEN"      # same single-series rule as a witness
            if want is None or verdict == want:
                cands.append((_dist(lat, lon, c["lat"], c["lon"]), vid, c["lat"], c["lon"]))
    cands.sort()
    for _, vid, la, lo in _rng.sample(cands[:NEAREST_POOL], min(NEAREST_POOL, len(cands))):
        hit = _trend_at(la, lo, vid)
        if hit and (want is None or hit[0].verdict == want):          # re-check with the full test (never trust the shortlist)
            nm = grid._nearest_name(la, lo)
            return _round(vid, la, lo, nm if nm[0].isdigit() else f"near {nm}", hit)    # a 0.5 deg cell is "near" a town, not the town
    raise NoRound("no real series with that verdict is available")
