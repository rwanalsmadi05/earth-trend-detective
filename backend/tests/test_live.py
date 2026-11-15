"""Cases for ANY point on Earth, live: POWER monthly+daily on demand, reverse-geocoded name, GIBS images, NDVI note,
caching ("a second click is instant"), a clear time budget. The network is faked; nothing here touches NASA or OSM."""
import re
import shutil
import threading
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import cache, case_builder, geocode, image_specs, main
from app.config import CACHE_DIR, POWER_PARAMS
from app.sources import gibs, power
from tsutil import TSC, TYPES_TS, tsc_compile

client = TestClient(main.app)
NAIROBI = (-1.2921, 36.8219)          # not in the gazetteer, not cached
JPEG = b"\xff\xd8\xff" + b"0" * 6000


def fake_monthly(slope_t=0.04, sleep=0.0, southern=False, nan_cols=()):
    idx = pd.date_range("1981-01-01", "2025-12-01", freq="MS")
    t = np.arange(len(idx)) / 12.0
    rng = np.random.default_rng(3)
    phase = 6 if southern else 0
    season = 8 * np.sin(2 * np.pi * ((idx.month - 1 + phase) % 12) / 12)
    wet = np.where(np.isin(idx.month, [11, 12, 1, 2] if southern else [5, 6, 7, 8]), 3.0, 0.2)   # wet season
    df = pd.DataFrame({c: 0.3 + rng.normal(0, 0.05, len(idx)) for c in POWER_PARAMS}, index=idx)
    df["T2M"] = 18 + season + slope_t * t + rng.normal(0, 0.6, len(idx))
    df["T2M_MAX"] = df["T2M"] + 8
    df["PRECTOTCORR"] = np.clip(wet + rng.normal(0, 0.3, len(idx)), 0, None)
    for c in nan_cols:
        df[c] = np.nan
    df.index.name = "date"
    return df


def fake_daily(sleep=0.0):
    idx = pd.date_range("1981-01-01", "2025-12-31", freq="D")
    rng = np.random.default_rng(4)
    return pd.DataFrame({"T2M_MAX": 30 + 0.05 * (idx.year - 1981) + rng.normal(0, 4, len(idx))}, index=idx)


@pytest.fixture
def live(monkeypatch, tmp_path):
    """Empty cache dir + fake POWER / Nominatim / Worldview that count their calls."""
    shutil.copy(CACHE_DIR / "gibs_capabilities.xml", tmp_path / "gibs_capabilities.xml")     # real capabilities, no network
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "META", tmp_path / "meta.json")
    calls = {"monthly": 0, "daily": 0, "nominatim": [], "wvs": 0}
    opts = {"monthly": fake_monthly(), "sleep": 0.0, "nominatim": {"address": {"city": "Nairobi", "country": "Kenya"},
                                                                    "namedetails": {"name:ar": "نيروبي"}},
            "wvs_ok": True}

    def monthly(lat, lon, start, end):
        calls["monthly"] += 1
        time.sleep(opts["sleep"])
        return opts["monthly"]

    def daily(lat, lon, start, end):
        calls["daily"] += 1
        time.sleep(opts["sleep"])
        return fake_daily()

    def nominatim_get(url, params=None, **kw):
        calls["nominatim"].append({"url": url, "params": params, **kw})
        if opts["nominatim"] is None:
            raise RuntimeError("geocoder down")
        return opts["nominatim"]

    def wvs_get(url, binary=False, **kw):
        calls["wvs"] += 1
        if not opts["wvs_ok"]:
            raise RuntimeError("503")
        return JPEG

    monkeypatch.setattr(power, "_fetch_monthly", monthly)
    monkeypatch.setattr(power, "_fetch_daily", daily)
    monkeypatch.setattr(geocode, "get", nominatim_get)
    monkeypatch.setattr(geocode, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(gibs, "get", wvs_get)
    monkeypatch.setattr(case_builder, "IMAGE_BUDGET_S", 5)
    case_builder.shutdown_retries()
    yield calls, opts
    case_builder.shutdown_retries()      # no scheduled retry may outlive its test (it would hit the real network)


def post(lat=NAIROBI[0], lon=NAIROBI[1], variables=("T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS"), **kw):
    return client.post("/case", json={"question": "", "lat": lat, "lon": lon, "variables": list(variables), **kw})


# ---- a brand-new point, then the second click --------------------------------------------------------------------------
def test_a_new_point_anywhere_gets_a_full_live_case(live):
    calls, _ = live
    r = post()
    assert r.status_code == 200
    c = r.json()
    assert c["place"] == {"name": "Nairobi, Kenya", "name_ar": "نيروبي", "lat": -1.29, "lon": 36.82}      # readable, rounded
    assert c["case_id"] == "custom_-1.29_36.82" and c["data_label"]["origin"] == "live"
    assert [w["variable"] for w in c["witnesses"]] == ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS"]
    assert calls["monthly"] == 1 and calls["daily"] == 1                                                  # each fetched once
    assert c["witnesses"][0]["verdict"] == "CONFIRMED" and c["witnesses"][0]["direction"] == "up"          # the planted warming is found
    for w in c["witnesses"]:                                                                              # real GIBS images, cached here
        for img in (w["images"]["before"], w["images"]["after"]):
            assert img["url"].startswith("/api/images/img_custom_-1.29_36.82_")
            west, south, east, north = img["bbox"]
            assert abs((west + east) / 2 - 36.82) < 1e-3 and abs((south + north) / 2 + 1.29) < 1e-3
    assert calls["wvs"] > 0


def test_second_click_is_instant_and_makes_no_network_calls(live):
    calls, _ = live
    a = post().json()
    before = (calls["monthly"], calls["daily"], len(calls["nominatim"]), calls["wvs"])
    t = time.time()
    b = post().json()
    assert time.time() - t < 3
    assert (calls["monthly"], calls["daily"], len(calls["nominatim"]), calls["wvs"]) == before            # nothing re-fetched
    assert b["data_label"]["origin"] == "cache" and b["place"] == a["place"]
    assert [w["stats"] for w in a["witnesses"]] == [w["stats"] for w in b["witnesses"]]
    assert [w["images"] for w in a["witnesses"]] == [w["images"] for w in b["witnesses"]]


def test_coordinates_are_rounded_so_nearby_clicks_share_the_cache(live):
    calls, _ = live
    post(lat=-1.2921, lon=36.8219)
    post(lat=-1.2949, lon=36.8184)                                                                        # same 0.01 deg cell
    assert calls["monthly"] == 1 and len(calls["nominatim"]) == 1


def test_monthly_and_daily_are_fetched_in_parallel(live):
    calls, opts = live
    opts["sleep"] = 0.5                                                  # each POWER call takes 0.5 s
    t = time.time()
    power.fetch_point(10.0, 20.0)
    elapsed = time.time() - t
    assert calls["monthly"] == 1 and calls["daily"] == 1
    assert elapsed < 0.85, f"took {elapsed:.2f}s: serial would be >= 1.0 s, parallel ~0.5 s"


# ---- reverse geocoding: cached, polite --------------------------------------------------------------------------------
def test_nominatim_is_called_once_with_a_polite_user_agent_and_only_the_coordinates(live):
    calls, _ = live
    post()
    post()
    assert len(calls["nominatim"]) == 1
    c = calls["nominatim"][0]
    ua = c["headers"]["User-Agent"]
    assert "EarthTrendDetective" in ua and "@" not in ua and not re.search(r"\S+@\S+", ua)               # identifies the app, no email
    assert c["url"] == "https://nominatim.openstreetmap.org/reverse"
    assert set(c["params"]) <= {"lat", "lon", "format", "zoom", "addressdetails", "namedetails", "accept-language"}
    assert (c["params"]["lat"], c["params"]["lon"]) == (-1.29, 36.82)


def test_geocode_results_are_cached_on_disk(live):
    calls, _ = live
    geocode.name_for(-1.29, 36.82)
    assert (cache.CACHE_DIR / "geocode" / "-1.29_36.82.json").exists()
    assert geocode.name_for(-1.29, 36.82)["source"] == "cache" and len(calls["nominatim"]) == 1


def test_geocoder_failure_never_blocks_the_case_and_is_not_cached(live):
    calls, opts = live
    opts["nominatim"] = None
    c = post().json()
    assert c["place"]["name"] == "1.29°S, 36.82°E" and c["witnesses"]
    assert not (cache.CACHE_DIR / "geocode").exists() or not list((cache.CACHE_DIR / "geocode").glob("*.json"))
    opts["nominatim"] = {"address": {"city": "Nairobi", "country": "Kenya"}}
    assert geocode.name_for(-1.29, 36.82)["name"] == "Nairobi, Kenya"                                      # retried later


def test_a_click_next_to_a_known_place_uses_the_gazetteer_without_the_network(live):
    calls, _ = live
    c = post(lat=31.9, lon=36.8).json()
    assert c["place"]["name"] == "Azraq" and c["place"]["name_ar"] == "الأزرق" and calls["nominatim"] == []


def test_a_name_given_by_the_client_is_used_as_is(live):
    calls, _ = live
    assert post(place="My field").json()["place"]["name"] == "My field" and calls["nominatim"] == []


def test_open_sea_unable_to_geocode_falls_back_to_coordinates_and_is_cached(live):
    calls, opts = live
    opts["nominatim"] = {"error": "Unable to geocode"}
    assert geocode.name_for(0.0, -30.0)["name"] == "0.00°N, 30.00°W"
    geocode.name_for(0.0, -30.0)
    assert len(calls["nominatim"]) == 1                                                                    # a definitive "nothing here"


def test_geocode_parse_puts_the_locality_first():
    r = geocode.parse({"address": {"village": "Azraq ash Shamali", "state": "Zarqa", "country": "Jordan"}}, 31.9, 36.8)
    assert r["name"] == "Azraq ash Shamali, Jordan" and r["name"].split(",")[0] == "Azraq ash Shamali"
    assert geocode.parse({"address": {"country": "Mongolia"}}, 47, 105)["name"] == "Mongolia"
    assert geocode.parse({}, 10.0, 20.0)["name"] == "10.00°N, 20.00°E"


# ---- NDVI -----------------------------------------------------------------------------------------------------------------
def test_ndvi_is_skipped_for_uncached_places_with_a_clear_note(live):
    c = post(variables=("T2M", "NDVI")).json()
    assert [w["variable"] for w in c["witnesses"]] == ["T2M"]
    notes = [h for h in c["hints"] if "NDVI" in h["text"]]
    assert notes == [{"after": "T2M", "text": "NDVI not available for live places"}]


def test_no_ndvi_note_when_ndvi_was_not_asked_for(live):
    assert not any("NDVI" in h["text"] for h in post(variables=("T2M", "PRECTOTCORR")).json()["hints"])


def test_ndvi_note_in_arabic_for_an_arabic_question(live):
    c = client.post("/case", json={"question": "هل ترتفع الحرارة هنا؟", "lat": NAIROBI[0], "lon": NAIROBI[1], "variables": ["T2M", "NDVI"]}).json()
    assert any(h["text"] == "مؤشر NDVI غير متاح للأماكن المباشرة" for h in c["hints"])


# ---- variables with no data at that point (open sea) -----------------------------------------------------------------------
def test_a_variable_with_no_data_at_the_point_is_skipped_not_faked(live):
    _, opts = live
    opts["monthly"] = fake_monthly(nan_cols=("GWETROOT", "GWETTOP"))
    c = post(variables=("T2M", "GWETROOT", "GWETTOP")).json()
    assert [w["variable"] for w in c["witnesses"]] == ["T2M"]


# ---- images: unavailable -> null (never a broken URL); retried in the background with backoff; cached on success ----------
def wait_until(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_images_that_cannot_be_fetched_are_null_not_a_broken_url(live):
    calls, opts = live
    opts["wvs_ok"] = False
    r = post(variables=("T2M", "PRECTOTCORR"))
    c = r.json()
    assert r.status_code == 200 and [w["images"] for w in c["witnesses"]] == [None, None]
    assert "wvs.earthdata.nasa.gov" not in r.text and "snapshot?" not in r.text                           # no direct Worldview URL anywhere
    assert c["witnesses"][0]["stats"]["n"] > 0 and c["witnesses"][0]["series"]                            # the chart data is all there


def test_a_pair_with_only_one_image_is_null_too(live, monkeypatch):
    calls, opts = live
    first = {"n": 0}

    def flaky(url, binary=False, **kw):
        calls["wvs"] += 1
        first["n"] += 1
        if first["n"] % 2 == 0:
            raise RuntimeError("503")
        return JPEG
    monkeypatch.setattr(gibs, "get", flaky)
    c = post(variables=("T2M",)).json()
    assert c["witnesses"][0]["images"] is None                                                            # never half a polaroid


def test_failed_images_are_retried_in_the_background_with_backoff_and_then_cached(live, monkeypatch):
    calls, opts = live
    monkeypatch.setattr(case_builder, "RETRY_BACKOFF_S", (0.05, 0.1, 0.2))
    opts["wvs_ok"] = False
    c1 = post(variables=("T2M",)).json()
    assert c1["witnesses"][0]["images"] is None
    opts["wvs_ok"] = True                                                                                 # Worldview recovers
    assert wait_until(lambda: len(list(cache.CACHE_DIR.glob("img_custom_-1.29_36.82_*.jpg"))) == 2), "background retry never cached the images"
    c2 = post(variables=("T2M",)).json()
    imgs = c2["witnesses"][0]["images"]
    assert imgs and imgs["before"]["url"].startswith("/api/images/") and imgs["after"]["url"].startswith("/api/images/")
    assert client.get(imgs["before"]["url"].replace("/api", "", 1)).headers["content-type"] == "image/jpeg"   # served from the cache


def test_retries_back_off_instead_of_hammering(live, monkeypatch):
    calls, opts = live
    monkeypatch.setattr(case_builder, "RETRY_BACKOFF_S", (2.5, 5.0))                                       # far longer than a request takes
    opts["wvs_ok"] = False
    post(variables=("T2M",))
    after_first = calls["wvs"]
    assert after_first >= 1
    post(variables=("T2M",))
    post(variables=("T2M",))
    assert calls["wvs"] == after_first                                                                    # new clicks do not start extra fetches
    assert wait_until(lambda: calls["wvs"] > after_first, 6.0)                                           # the scheduled retry does happen


def test_retries_stop_after_the_last_backoff_step(live, monkeypatch):
    calls, opts = live
    monkeypatch.setattr(case_builder, "RETRY_BACKOFF_S", (0.05, 0.05))
    opts["wvs_ok"] = False
    post(variables=("T2M",))
    assert wait_until(lambda: not case_builder._pending and not case_builder._inflight, 3.0)
    settled = calls["wvs"]
    time.sleep(0.3)
    assert calls["wvs"] == settled                                                                        # gave up: 1 try + 2 retries per image
    assert settled == 6                                                                                   # 2 images x (1 try + 2 retries)
    assert post(variables=("T2M",)).json()["witnesses"][0]["images"] is None                             # still null, still a valid case


def test_a_cached_pair_is_never_refetched(live):
    calls, opts = live
    post(variables=("T2M",))
    n = calls["wvs"]
    assert n == 2 and post(variables=("T2M",)).json()["witnesses"][0]["images"] is not None
    assert calls["wvs"] == n


def test_shutdown_retries_cancels_everything(live, monkeypatch):
    calls, opts = live
    monkeypatch.setattr(case_builder, "RETRY_BACKOFF_S", (0.2,))
    opts["wvs_ok"] = False
    post(variables=("T2M",))
    n = calls["wvs"]
    case_builder.shutdown_retries()
    opts["wvs_ok"] = True
    time.sleep(0.5)
    assert calls["wvs"] == n and not case_builder._pending


# ---- cleaned_question for clicks on the globe -------------------------------------------------------------------------------
def test_a_globe_click_gets_a_readable_title(live):
    assert post().json()["cleaned_question"] == "What is changing in Nairobi, Kenya?"


def test_the_title_uses_the_name_the_client_sent_or_the_coordinates_when_geocoding_fails(live):
    calls, opts = live
    assert post(place="My field").json()["cleaned_question"] == "What is changing in My field?"
    opts["nominatim"] = None
    assert post(lat=10.0, lon=20.0).json()["cleaned_question"] == "What is changing in 10.00°N, 20.00°E?"


def test_a_typed_question_is_still_tidied_not_replaced(live):
    c = client.post("/case", json={"question": "  is   it hot here ", "lat": NAIROBI[0], "lon": NAIROBI[1], "variables": ["T2M"]}).json()
    assert c["cleaned_question"] == "Is it hot here?" and c["question"] == "  is   it hot here "


# ---- the time budget --------------------------------------------------------------------------------------------------------
def test_slow_live_fetch_gives_a_clear_504_and_the_retry_is_fast(live, monkeypatch):
    calls, opts = live
    monkeypatch.setattr(main, "LIVE_BUDGET_S", 0.3)
    opts["sleep"] = 0.8
    r = post(variables=("T2M",))
    assert r.status_code == 504
    d = r.json()["detail"]
    assert "longer than" in d and "cached" in d and "trying again" in d
    time.sleep(1.5)                                                                                        # the work finished in the background
    monkeypatch.setattr(main, "LIVE_BUDGET_S", 60)
    t = time.time()
    r2 = post(variables=("T2M",))
    assert r2.status_code == 200 and time.time() - t < 3 and calls["monthly"] == 1                         # no second fetch


# ---- validation ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lat,lon", [(95, 10), (-91, 10), (10, 181), (10, -181)])
def test_points_off_the_earth_are_rejected(live, lat, lon):
    assert client.post("/case", json={"question": "", "lat": lat, "lon": lon, "variables": ["T2M"]}).status_code == 422


def test_lat_without_lon_is_rejected(live):
    assert client.post("/case", json={"question": "", "lat": 10, "variables": ["T2M"]}).status_code == 422
    assert client.post("/case", json={"question": "", "lon": 10, "variables": ["T2M"]}).status_code == 422


@pytest.mark.parametrize("lat,lon", [(0.0, 0.0), (89.9, 10.0), (-89.9, -170.0), (10.0, 179.9), (10.0, -179.9)])
def test_extreme_points_still_work(live, lat, lon):
    r = post(lat=lat, lon=lon, variables=("T2M",))
    assert r.status_code == 200
    for img in (r.json()["witnesses"][0]["images"]["before"], r.json()["witnesses"][0]["images"]["after"]):
        w, s, e, n = img["bbox"]
        assert -180 <= w < e <= 180 and -90 <= s < n <= 90


# ---- image geometry + months anywhere on Earth --------------------------------------------------------------------------
def test_windows_are_centred_and_only_shifted_when_they_would_leave_the_map():
    assert image_specs.window(31.88, 36.83, 2.5, 3.0) == (29.38, 33.83, 34.38, 39.83)
    s, w, n, e = image_specs.window(89.5, 10, 2.5, 3.0)
    assert (n, round(n - s, 4)) == (90.0, 5.0) and (round(e - w, 4)) == 6.0                                # same size, shifted
    s, w, n, e = image_specs.window(0, 179.5, 2.5, 3.0)
    assert e == 180.0 and round(e - w, 4) == 6.0 and (s, n) == (-2.5, 2.5)
    s, w, n, e = image_specs.window(-89.0, -179.0, 2.5, 3.0)
    assert (s, w) == (-90.0, -180.0) and round(n - s, 4) == 5.0 and round(e - w, 4) == 6.0


def test_azraq_image_plan_is_unchanged_by_the_generalised_month_rule():
    m = cache.load_df("power_monthly_31.88_36.83_1981_2025") if (CACHE_DIR / "power_monthly_31.88_36.83_1981_2025.parquet").exists() else None
    if m is None:
        pytest.skip("Azraq not cached")
    tags = {v: image_specs.plan(v, 31.88, 36.83, m).tag for v in ("T2M", "PRECTOTCORR", "GWETROOT", "NDVI", "HOT_DAYS")}
    assert tags["PRECTOTCORR"].endswith("_m03_oasis") and tags["GWETROOT"].endswith("_m03_region") and tags["NDVI"].endswith("_m03_region")
    assert tags["T2M"].endswith("_m04_region") and tags["HOT_DAYS"].endswith("_m07_region")


def test_wet_season_month_is_data_driven_in_the_southern_hemisphere():
    south = fake_monthly(southern=True)                                                                    # wet Nov-Feb, wettest ~ Nov-Feb
    wettest = int(south["PRECTOTCORR"].groupby(south.index.month).mean().idxmax())
    tag = image_specs.plan("NDVI", -30.0, 25.0, south).tag                                                 # month actually planned for the images
    assert tag.endswith(f"_m{wettest % 12 + 1:02d}_region") or tag.endswith(f"_m{(wettest - 1) % 12 + 1:02d}_region")         or tag.endswith(f"_m{(wettest + 1) % 12 + 1:02d}_region")                                          # month after wettest, or a listed neighbour
    assert not tag.endswith("_m03_region") or wettest % 12 + 1 in (2, 3, 4)                               # never Jordan's hard-coded March by accident
    assert image_specs._month("after_wettest", south) == wettest % 12 + 1
    north = fake_monthly()
    assert image_specs._month("after_wettest", north) == int(north["PRECTOTCORR"].groupby(north.index.month).mean().idxmax()) % 12 + 1
    assert image_specs._month("after_wettest", south) != image_specs._month("after_wettest", north)


def test_an_unlisted_date_falls_back_to_a_neighbouring_month(monkeypatch):
    m = fake_monthly()
    base = image_specs.plan("NDVI", 10.0, 20.0, m)
    month = int(base.tag.split("_m")[1][:2])
    real = gibs.covers
    monkeypatch.setattr(gibs, "covers", lambda lyr, day: False if (lyr == image_specs.NDVI_L and f"-{month:02d}-" in day) else real(lyr, day))
    moved = image_specs.plan("NDVI", 10.0, 20.0, m)
    assert int(moved.tag.split("_m")[1][:2]) == (month - 2) % 12 + 1 and moved.before.endswith("-01") is True
    monkeypatch.setattr(gibs, "covers", lambda lyr, day: False if lyr == image_specs.NDVI_L else real(lyr, day))
    with pytest.raises(ValueError):
        image_specs.plan("NDVI", 10.0, 20.0, m)                                                            # never an unlisted date


def test_meta_json_survives_parallel_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "META", tmp_path / "meta.json")
    ts = [threading.Thread(target=lambda i=i: cache._stamp(f"k{i}", {"url": "u"})) for i in range(40)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert set(cache._meta()) == {f"k{i}" for i in range(40)}                                              # no lost updates


@pytest.mark.skipif(not TSC.exists(), reason="frontend/node_modules not installed")
def test_a_response_with_null_images_typechecks_against_the_nullable_type(live, tmp_path):
    """types.ts (the frontend's) still says `images: {before; after}`; the backend now sends null when NASA images are
    unavailable. This compiles the real response against the type the frontend needs: images: {...} | null."""
    import json
    calls, opts = live
    opts["wvs_ok"] = False
    c = post(variables=("T2M", "NDVI")).json()
    assert c["witnesses"][0]["images"] is None
    src = (f'import type {{ CaseResponse, Witness, SatImage }} from "{TYPES_TS.as_posix()[:-3]}";\n'
           'type Img = SatImage & { bbox: [number, number, number, number] };\n'
           'type W = Omit<Witness, "images"> & { images: { before: Img; after: Img } | null };\n'
           'type Case = Omit<CaseResponse, "witnesses" | "cleaned_question"> & { witnesses: W[]; cleaned_question: string };\n'
           f"export const x: Case = {json.dumps(c, ensure_ascii=False)};\n")
    ok, out = tsc_compile(tmp_path, src, "null_images")
    assert ok, out
    ok2, out2 = tsc_compile(tmp_path, src.replace(" | null }", " }"), "strict_images")            # the CURRENT types.ts shape rejects null
    assert not ok2 and "null" in out2
