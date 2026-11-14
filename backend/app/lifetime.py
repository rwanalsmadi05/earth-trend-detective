"""'Since you were born' (CLAUDE.md feature 6): three giant numbers from the user's birth year to the latest full year.
Same statistics as everywhere else (stats.trend), computed on the series sliced from the birth year."""
from . import cache, gazetteer, stats
from .case_builder import _headline, _source
from .config import LAST_FULL_YEAR, START_YEAR
from .planner import PlaceNotFound
from .sources import power
from .variables import VARIABLES

LIFETIME_VARS = ["T2M", "PRECTOTCORR", "HOT_DAYS"]
UNIT = {"T2M": "°C", "PRECTOTCORR": "%", "HOT_DAYS": " days"}


def lifetime(place: str, birth_year: int) -> dict:
    hit = gazetteer.lookup(place)
    if not hit:
        raise PlaceNotFound(f"could not find a place: {place!r}")
    lat, lon = hit["lat"], hit["lon"]
    end = LAST_FULL_YEAR
    need = max(stats.MIN_N, stats.MIN_ANNUAL)        # the hot-days series is annual: it needs MIN_N yearly values
    used = int(min(max(birth_year, START_YEAR), end - need + 1))   # clamped to the data period (and to a testable length)

    power_df, st, key = power.monthly(lat, lon)
    hot, st2 = power.hot_days_per_year(lat, lon)
    power_df = power_df[(power_df.index.year >= used) & (power_df.index.year <= end)]
    hot = hot[(hot.index >= used) & (hot.index <= end)]

    items = []
    for vid in LIFETIME_VARS:
        v = VARIABLES[vid]
        raw, seasonal = (hot, False) if v["kind"] == "power_daily" else (power_df[v["col"]], True)
        tr = stats.trend(raw, seasonal=seasonal)
        value = tr.pct_change if vid == "PRECTOTCORR" else tr.total_change
        items.append({"variable": vid, "label": v["label"], "value": value, "display_unit": UNIT[vid],
                      "headline": _headline(vid, tr), "direction": tr.direction, "verdict": tr.verdict, "p": tr.p,
                      "source": _source(vid, lat, lon, used, end)[0]})
    fetched = (cache.meta_for(key).get("fetched") or "")[:10]
    return {"place": {"name": hit["name"], "lat": lat, "lon": lon}, "birth_year": used, "end_year": end,
            "years": end - used, "items": items,
            "data_label": {"origin": "live" if "fresh" in (st, st2) else "cache", "fetched": fetched}}
