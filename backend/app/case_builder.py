"""Question -> plan -> data -> statistics -> CaseResponse (shape of frontend/src/api/types.ts).

The plan (variables, reasons, place, cleaned question, language) comes from planner.py (Gemini, or the rule-based
fallback); manual selection skips the planner. NDVI joins automatically when its cache is complete.
Verdicts and every number come from stats.py, never from the LLM."""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from . import cache, gazetteer, geocode, i18n, image_specs, planner, stats
from .config import CASES, LAST_FULL_YEAR, START_YEAR
from .planner import PlaceNotFound
from .sources import gibs, modis, power
from .variables import DEFAULT_PLAN, PLAIN, SOURCE_NOTE, VARIABLES

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


def _img(case_id, plan, day):
    name = gibs.image_key(case_id, plan.tag, day)
    return {"date": day, "url": f"{API_PREFIX}/images/{name}", "bbox": _bbox_wsen(plan.bbox)}


def _plan_for(vid, lat, lon, clim):
    try:
        return image_specs.plan(vid, lat, lon, clim)
    except Exception:  # noqa: BLE001  (capabilities unavailable / no listed date): plain true color
        return image_specs.plan("RH2M", lat, lon, clim)


def _witness_images(case_id, lat, lon, vid, clim):
    """Each witness gets its own real NASA image pair (early vs recent) centred on the place; see image_specs.py.
    Returns None unless BOTH images are cached here: never a URL that may be broken (Worldview is often down for live
    places), so the frontend shows its chart fallback. Missing images keep being fetched in the background."""
    try:
        pl = _plan_for(vid, lat, lon, clim)
    except Exception:  # noqa: BLE001
        return None
    names = [gibs.image_key(case_id, pl.tag, d) for d in (pl.before, pl.after)]
    if not all(cache.blob_path(n).exists() for n in names):
        return None
    return {"before": _img(case_id, pl, pl.before), "after": _img(case_id, pl, pl.after)}


IMAGE_BUDGET_S = 8        # a request waits at most this long for NASA images; the rest keep downloading in the background
IMAGE_TIMEOUT_S = 10      # per attempt: fail fast (Worldview is sometimes slow or answers 503/429)
RETRY_BACKOFF_S = (20, 60, 180, 600)   # background retries after a failed attempt (exponential-ish); then give up for COOLDOWN_S
COOLDOWN_S = 300          # after the last retry failed, a later request may start over only after this long
_IMG_POOL = ThreadPoolExecutor(max_workers=2)   # module-level: downloads continue (and get cached) after a request returns
_img_lock = threading.Lock()
_inflight: dict = {}      # image file name -> Future (shared by concurrent requests)
_pending: set = set()     # image file names with a background retry scheduled
_failed_at: dict = {}     # image file name -> time of last failure
_timers: list = []        # scheduled retries (daemon timers); cancellable


def shutdown_retries():
    """Cancel every scheduled background retry and forget image state (used by tests and on shutdown)."""
    with _img_lock:
        for t in _timers:
            t.cancel()
        _timers.clear()
        _pending.clear()
        _failed_at.clear()
        _inflight.clear()


def _fetch_image(name, case_id, tag, bbox, day, layers, attempt=0):
    ok = False
    try:
        gibs.snapshot(case_id, tag, bbox, day, layers, timeout=IMAGE_TIMEOUT_S, retries=1)
        ok = True
    except Exception:  # noqa: BLE001
        pass
    with _img_lock:
        _inflight.pop(name, None)
        if ok:
            _pending.discard(name)
            _failed_at.pop(name, None)
            return
        _failed_at[name] = time.monotonic()
        if attempt < len(RETRY_BACKOFF_S):          # try again later, in the background, with growing delays
            _pending.add(name)
            t = threading.Timer(RETRY_BACKOFF_S[attempt], _retry, (name, case_id, tag, bbox, day, layers, attempt + 1))
            t.daemon = True
            _timers.append(t)
            t.start()
        else:
            _pending.discard(name)


def _retry(name, case_id, tag, bbox, day, layers, attempt):
    with _img_lock:
        if cache.blob_path(name).exists() or name in _inflight:
            _pending.discard(name)
            return
        _inflight[name] = _IMG_POOL.submit(_fetch_image, name, case_id, tag, bbox, day, layers, attempt)


def prefetch_images(case_id, lat, lon, vids, clim):
    """Start downloading + caching the NASA images this case needs, wait a bounded time, return. Cached images are
    skipped; downloads already running or already scheduled for a retry (another request, or an earlier failure) are not
    started again, so a struggling service is never hammered. What is not cached when the case is assembled is simply
    reported as images: null (and keeps being retried in the background, with backoff)."""
    mine = []
    now = time.monotonic()
    for vid in vids:
        try:
            pl = _plan_for(vid, lat, lon, clim)
        except Exception:  # noqa: BLE001
            continue
        for day, layers in ((pl.before, pl.layers_before), (pl.after, pl.layers_after)):
            name = gibs.image_key(case_id, pl.tag, day)
            if cache.blob_path(name).exists():
                continue
            with _img_lock:
                if name in _inflight or name in _pending or now - _failed_at.get(name, -1e9) < COOLDOWN_S:
                    continue
                _inflight[name] = _IMG_POOL.submit(_fetch_image, name, case_id, pl.tag, pl.bbox, day, layers)
                mine.append(_inflight[name])
    if mine:
        wait(mine, timeout=IMAGE_BUDGET_S)


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
        note = f" — {SOURCE_NOTE[vid]}" if vid in SOURCE_NOTE else ""
        return f"NASA POWER · {v['col']}{note}", power.monthly_url(lat, lon, start, end)
    if v["kind"] == "power_daily":
        return "NASA POWER daily · T2M_MAX (days above 35 °C)", power.daily_url(lat, lon)   # the full record is always fetched
    return "MODIS MOD13Q1 · ORNL DAAC (250 m, from 2000)", f"{modis.BASE}/subset?latitude={lat}&longitude={lon}&band={modis.BAND}"


def expert_note(vid, tr, place_name):
    """Honest data-provenance text for the expert drawer / report (computed numbers only; no new claims)."""
    if vid in ("GWETROOT", "GWETTOP"):
        small = ", small absolute change" if abs(tr.total_change) < 0.05 else ""
        return (f"data: {SOURCE_NOTE[vid]}{small} ({tr.total_change:+.3f} index units since {tr.first_year}; "
                "a model index, not measured moisture)")
    if vid == "PRECTOTCORR":
        return (f"data: POWER cell is ~0.5 deg (MERRA-2 reanalysis) and averages a wider area that can include uplands, "
                f"so rainfall may be higher than the {place_name} station")
    return ""


def build_case(*args, **kw):
    """The CaseResponse dict only (exactly the shape of frontend types.ts)."""
    return build_case_and_expert(*args, **kw)[0]


def build_case_and_expert(question, variables=None, lat=None, lon=None, place=None, start=None, end=None, plan=None):
    """`plan` (planner.Plan) supplies place, variables, reasons, language and the cleaned question. Without a plan
    (manual selection / explicit coordinates) the place comes from the request or the gazetteer, reasons are templates."""
    if lat is not None and lon is not None:
        lat, lon = round(lat, 2), round(lon, 2)       # one grid-cell precision: cache key, URLs and the place all agree
        if place:
            pl = {"name": place, "name_ar": "", "lat": lat, "lon": lon}
        else:                                         # readable name for any point on Earth (gazetteer, cache, Nominatim)
            g = geocode.name_for(lat, lon)
            pl = {"name": g["name"], "name_ar": g["name_ar"], "lat": lat, "lon": lon}
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
    if not plan and not question.strip():            # a click on the globe has no question: give the case a title
        cleaned = f"What is changing in {pl['name']}?"
    lat, lon = pl["lat"], pl["lon"]
    if plan and not variables:
        variables = [v["variable"] for v in plan.variables]
    start = max(start or (plan.period["start"] if plan else START_YEAR), START_YEAR)
    end = min(end or (plan.period["end"] if plan else LAST_FULL_YEAR), LAST_FULL_YEAR)

    power_df, st, key, hot, st2 = power.fetch_point(lat, lon)     # monthly + daily in parallel; cached after the first time
    clim = power_df  # full record: used to pick the image months
    power_df = power_df[(power_df.index.year >= start) & (power_df.index.year <= end)]
    hot = hot[(hot.index >= start) & (hot.index <= end)]
    ndvi = _ndvi_if_cached(lat, lon)
    if ndvi is not None:
        ndvi = ndvi[(ndvi.index.year >= start) & (ndvi.index.year <= end)]

    chosen = list(variables) if variables else DEFAULT_PLAN + (["NDVI"] if ndvi is not None else [])
    case_id = _case_id(lat, lon)
    prefetch_images(case_id, lat, lon, [v for v in chosen if v != "NDVI" or ndvi is not None], clim)

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
                       "n_tested": tr.n_tested,
                       "test_on": ("monthly anomalies (seasonality removed), Hamed-Rao lag cap 12" if seasonal else "annual values")
                                  + (f" · {expert_note(vid, tr, pl['name'])}" if expert_note(vid, tr, pl["name"]) else ""),
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

    if "NDVI" in chosen and ndvi is None and witnesses:       # asked for, but NDVI is only prefetched for demo places
        hints.append({"after": witnesses[0]["variable"],
                      "text": "مؤشر NDVI غير متاح للأماكن المباشرة" if lang == "ar" else "NDVI not available for live places"})

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
