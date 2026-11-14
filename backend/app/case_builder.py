"""Question -> plan -> data -> statistics -> CaseResponse (shape of frontend/src/api/types.ts).

The plan (variables, reasons, place, cleaned question, language) comes from planner.py (Gemini, or the rule-based
fallback); manual selection skips the planner. NDVI joins automatically when its cache is complete.
Verdicts and every number come from stats.py, never from the LLM."""
import os
from . import cache, gazetteer, i18n, image_specs, planner, stats
from .config import CASES, LAST_FULL_YEAR, START_YEAR
from .planner import PlaceNotFound
from .sources import gibs, modis, power
from .variables import DEFAULT_PLAN, PLAIN, VARIABLES

API_PREFIX = os.getenv("PUBLIC_API_PREFIX", "/api")  # frontend dev proxy strips /api; images are served at /images/<file>

# plain-language phrase for a significant trend, by (variable, direction). Used in the case headline.
PHRASE = {
    "T2M": ("hotter", "cooler"), "T2M_MAX": ("hotter daytime peaks", "cooler daytime peaks"),
    "HOT_DAYS": ("more extreme-heat days", "fewer extreme-heat days"), "PRECTOTCORR": ("more rain", "less rain"),
    "GWETROOT": ("wetter soil", "drier soil"), "GWETTOP": ("wetter topsoil", "drier topsoil"),
    "RH2M": ("more humid air", "drier air"), "ALLSKY_SFC_SW_DWN": ("more sunshine", "less sunshine"),
    "NDVI": ("more vegetation", "less vegetation"),
}


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def case_headline(witnesses, expert, place):
    """Case-level headline built only from the computed verdicts (no claim beyond what was tested)."""
    total = len(witnesses)
    sig_w = [w for w in witnesses if w["verdict"] == "CONFIRMED"]
    if not sig_w:
        return f"No witness shows a significant change in {place} (0 of {total})"
    phrases = [PHRASE[w["variable"]][0 if w["direction"] == "up" else 1] for w in sig_w]
    out = f"{len(sig_w)} of {total} witnesses show a significant change in {place}: {_join(phrases)}"
    border = [f"{PHRASE[w['variable']][0 if w['direction'] == 'up' else 1]} (p = {w['stats']['p']:.2g})"
              for w in sig_w if expert[w["variable"]]["borderline"]]
    if border:
        out += f". Borderline: {_join(border)}"
    return out


def _case_id(lat, lon):
    for cid, c in CASES.items():
        if abs(c["lat"] - lat) < 0.02 and abs(c["lon"] - lon) < 0.02:
            return cid
    return f"custom_{lat:.2f}_{lon:.2f}"


def _bbox_wsen(bbox):
    """Worldview uses (south, west, north, east); the API returns [west, south, east, north]."""
    s_, w, n, e = bbox
    return [round(w, 4), round(s_, 4), round(e, 4), round(n, 4)]


def _img(case_id, plan, day, layers):
    """Cached local image if prefetched, else the direct Worldview URL (the browser then fetches it from NASA)."""
    name = gibs.image_key(case_id, plan.tag, day)
    if cache.blob_path(name).exists():
        url = f"{API_PREFIX}/images/{name}"
    else:
        url = gibs.snapshot_url(plan.bbox, day, layers)
    return {"date": day, "url": url, "bbox": _bbox_wsen(plan.bbox)}


def _witness_images(case_id, lat, lon, vid, clim):
    """Each witness gets its own real NASA image pair (early vs recent) centred on the place; see image_specs.py."""
    try:
        pl = image_specs.plan(vid, lat, lon, clim)
    except Exception:  # noqa: BLE001  (capabilities unavailable / date not listed): plain true color
        pl = image_specs.plan("RH2M", lat, lon, clim)
    return {"before": _img(case_id, pl, pl.before, pl.layers_before), "after": _img(case_id, pl, pl.after, pl.layers_after)}


def _ndvi_if_cached(lat, lon):
    """NDVI joins automatically once `prefetch.py` has completed it. Never fetched live inside a request (ORNL is too slow)."""
    df = cache.load_df(f"modis_ndvi_{lat:.2f}_{lon:.2f}_{LAST_FULL_YEAR}")
    return None if df is None or df["ndvi"].dropna().empty else df["ndvi"]


def _headline(vid, tr, lang="en"):
    """One method for every witness: the TOTAL change of the Sen's-slope trend line over the record (annual means),
    worded "since <first year of the record>". Percentages are that total relative to the first-decade mean.
    Never worded "than in the 1980s": that would claim a decade-vs-decade comparison we did not compute.
    NOT PROVEN headlines are plain language with no numbers; exact numbers live in the expert data."""
    if lang == "ar":
        return i18n.headline_ar(vid, tr.direction, tr.total_change, tr.pct_change, tr.first_year, tr.verdict, tr.reason)
    v, plain = VARIABLES[vid], PLAIN[vid]
    since = f"since {tr.first_year}"
    if tr.reason:
        return f"Not enough reliable evidence to judge {plain} {since} — not proven"
    if tr.verdict == "NOT PROVEN":
        return f"No clear change in {plain} {since} — could be chance"
    more = tr.direction == "up"
    if vid in ("T2M", "T2M_MAX"):
        return f"{abs(tr.total_change):.1f} °C {'hotter' if more else 'cooler'} {since}"
    if vid == "HOT_DAYS":
        return f"{abs(tr.total_change):.0f} {'more' if more else 'fewer'} days above 35 °C per year {since}"
    return f"{abs(tr.pct_change):.0f}% {'more' if more else 'less'} {v['noun']} {since}"


def _series_for(vid, lat, lon, power_df, hot, ndvi):
    """Return (raw series, seasonal?) or None if unavailable."""
    v = VARIABLES[vid]
    if v["kind"] == "power":
        return power_df[v["col"]], True
    if v["kind"] == "power_daily":
        return hot, False
    return (ndvi, True) if ndvi is not None else None


def _source(vid, lat, lon, start, end):
    v = VARIABLES[vid]
    if v["kind"] == "power":
        return f"NASA POWER · {v['col']}", power.monthly_url(lat, lon, start, end)
    if v["kind"] == "power_daily":
        return "NASA POWER daily · T2M_MAX (days above 35 °C)", f"{power.DAILY}?parameters=T2M_MAX&community=AG&latitude={lat}&longitude={lon}&format=JSON"
    return "MODIS MOD13Q1 · ORNL DAAC (250 m, from 2000)", f"{modis.BASE}/subset?latitude={lat}&longitude={lon}&band={modis.BAND}"


def build_case(*args, **kw):
    """The CaseResponse dict only (exactly the shape of frontend types.ts)."""
    return build_case_and_expert(*args, **kw)[0]


def build_case_and_expert(question, variables=None, lat=None, lon=None, place=None, start=None, end=None, plan=None):
    """`plan` (planner.Plan) supplies place, variables, reasons, language and the cleaned question. Without a plan
    (manual selection / explicit coordinates) the place comes from the request or the gazetteer, reasons are templates."""
    if lat is not None and lon is not None:
        pl = {"name": place or f"{lat:.2f}°N, {lon:.2f}°E", "name_ar": "", "lat": lat, "lon": lon}
    elif plan is not None:
        pl = {"name": plan.place["name"], "name_ar": plan.place.get("name_ar") or "", "lat": plan.place["lat"], "lon": plan.place["lon"]}
    else:
        hit = gazetteer.lookup(question)
        if not hit:
            raise PlaceNotFound(f"could not find a place in: {question!r}")
        pl = {"name": hit["name"], "name_ar": hit["name_ar"] or "", "lat": hit["lat"], "lon": hit["lon"]}
    lang = plan.language if plan else i18n.detect_language(question)
    reasons = plan.reasons() if plan else {}
    cleaned = plan.cleaned_question if plan else planner.rules_clean(question)
    lat, lon = pl["lat"], pl["lon"]
    if plan and not variables:
        variables = [v["variable"] for v in plan.variables]
    start = max(start or (plan.period["start"] if plan else START_YEAR), START_YEAR)
    end = min(end or (plan.period["end"] if plan else LAST_FULL_YEAR), LAST_FULL_YEAR)

    power_df, st, key = power.monthly(lat, lon)
    hot, st2 = power.hot_days_per_year(lat, lon)
    clim = power_df  # full record: used to pick the image months
    power_df = power_df[(power_df.index.year >= start) & (power_df.index.year <= end)]
    hot = hot[(hot.index >= start) & (hot.index <= end)]
    ndvi = _ndvi_if_cached(lat, lon)
    if ndvi is not None:
        ndvi = ndvi[(ndvi.index.year >= start) & (ndvi.index.year <= end)]

    chosen = list(variables) if variables else DEFAULT_PLAN + (["NDVI"] if ndvi is not None else [])
    case_id = _case_id(lat, lon)

    witnesses, anoms, expert = [], {}, {}
    for vid in chosen:
        got = _series_for(vid, lat, lon, power_df, hot, ndvi)
        if got is None:
            continue  # e.g. NDVI requested but not cached yet
        raw, seasonal = got
        try:
            tr = stats.trend(raw, seasonal=seasonal)
        except stats.TooShort:
            continue
        v = VARIABLES[vid]
        source, url = _source(vid, lat, lon, start, end)
        witnesses.append({
            "variable": vid, "label": i18n.LABEL_AR[vid] if lang == "ar" else v["label"], "unit": v["unit"],
            "reason": reasons.get(vid) or (i18n.REASON_AR[vid] if lang == "ar" else v["reason"]),
            "source": source, "source_url": url, "start_year": tr.first_year,
            "images": _witness_images(case_id, lat, lon, vid, clim),
            "stats": {"n": tr.n, "tau": tr.tau, "p": tr.p, "sen_per_decade": tr.sen_per_decade,
                      "total_change": tr.total_change, "pct_change": tr.pct_change},
            "verdict": tr.verdict, "headline": _headline(vid, tr, lang),
            "direction": tr.direction, "series": tr.annual,
        })
        expert[vid] = {"method": tr.method, "reason": tr.reason, "n_months": tr.n if seasonal else None,
                       "n_tested": tr.n_tested, "test_on": "monthly anomalies (seasonality removed), Hamed-Rao lag cap 12" if seasonal else "annual values",
                       "baseline": tr.baseline, "borderline": tr.borderline, "tau": tr.tau, "p": tr.p, "sen_per_decade": tr.sen_per_decade}
        if seasonal:
            anoms[vid] = stats.deseasonalize(raw.astype(float)).dropna()

    labels = {w["variable"]: w["label"] for w in witnesses}
    chain = stats.chain_of_evidence(anoms)
    hints = []
    if lang != "ar":   # Arabic hints come from the AI partner's /case/explain (guarded); no template hints in Arabic yet
        if chain:
            c = chain[0]
            when = "moved together with" if c["lag_months"] == 0 else f"moved about {c['lag_months']} months before"
            hints.append({"after": c["from"], "text": f"Notice: {labels[c['from']].lower()} {when} {labels[c['to']].lower()}. Correlation, not proof of cause: what else could link them?"})
        if any(w["variable"] == "NDVI" for w in witnesses):
            hints.append({"after": "NDVI", "text": "The satellite plant record only starts in 2000. A shorter record has less power to detect a trend."})

    total = len(witnesses)
    k = sum(1 for w in witnesses if w["verdict"] == "CONFIRMED")
    headline = (i18n.case_headline_ar(witnesses, expert, pl["name_ar"] or pl["name"]) if lang == "ar"
                else case_headline(witnesses, expert, pl["name"]))

    fetched = (cache.meta_for(key).get("fetched") or "")[:10]
    case = {
        "case_id": case_id, "question": question, "cleaned_question": cleaned, "place": pl,
        "period": {"start": start, "end": end},
        "witnesses": witnesses, "chain": chain, "hints": hints,
        "verdict": {"confirmed": k, "total": total, "headline": headline},
        "data_label": {"origin": "live" if "fresh" in (st, st2) else "cache", "fetched": fetched},
    }
    return case, {"case_id": case_id, "variables": expert}
