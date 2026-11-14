"""Daily-data URL is exact everywhere it is stored or returned; soil-moisture and rainfall are labelled honestly."""
import json
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import cache, case_builder, stats
from app.config import CACHE_DIR, LAST_FULL_YEAR, START_YEAR
from app.main import app
from app.sources import power

client = TestClient(app)


@pytest.fixture(scope="module")
def azraq():
    c = client.post("/case", json={"question": "Is Azraq drying up?", "variables": ["T2M", "PRECTOTCORR", "GWETROOT", "GWETTOP", "HOT_DAYS"]}).json()
    e = client.post("/case/expert", json={"question": "Is Azraq drying up?", "variables": ["T2M", "PRECTOTCORR", "GWETROOT", "GWETTOP", "HOT_DAYS"]}).json()["variables"]
    return c, e, {w["variable"]: w for w in c["witnesses"]}


# ---- daily URL --------------------------------------------------------------------------------------------------
def q(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_daily_url_is_exactly_the_request_that_is_sent():
    sent = str(httpx.Request("GET", power.DAILY, params=power.daily_params(31.88, 36.83, 1981, 2025)).url)
    assert q(power.daily_url(31.88, 36.83, 1981, 2025)) == q(sent)
    assert q(sent) == {"parameters": "T2M_MAX", "community": "AG", "latitude": "31.88", "longitude": "36.83",
                       "start": "19810101", "end": "20251231", "format": "JSON"}


def test_case_returns_the_full_daily_url_as_source_url(azraq):
    c, _, w = azraq
    url = w["HOT_DAYS"]["source_url"]
    assert url == power.daily_url(31.88, 36.83, START_YEAR, LAST_FULL_YEAR)
    assert q(url)["start"] == f"{START_YEAR}0101" and q(url)["end"] == f"{LAST_FULL_YEAR}1231" and q(url)["community"] == "AG"
    assert urlparse(url).path.endswith("/temporal/daily/point")


def test_every_stored_daily_url_in_the_cache_metadata_is_complete():
    meta = json.loads((CACHE_DIR / "meta.json").read_text("utf-8"))
    keys = [k for k in meta if k.startswith("power_daily_t2mmax_")]
    assert keys, "expected cached daily series"
    for k in keys:
        a, b = re.search(r"_(\d{4})_(\d{4})$", k).groups()
        u = q(meta[k]["url"])
        assert (u["start"], u["end"], u["community"], u["format"], u["parameters"]) == (f"{a}0101", f"{b}1231", "AG", "JSON", "T2M_MAX"), k
        assert "latitude" in u and "longitude" in u


def test_a_fresh_fetch_stores_the_full_url(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "META", tmp_path / "meta.json")
    idx = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    monkeypatch.setattr(power, "_fetch_daily", lambda *a: pd.DataFrame({"T2M_MAX": np.full(len(idx), 36.0)}, index=idx))
    power.hot_days_per_year(10.0, 20.0, start=2000, end=2001)
    stored = cache.meta_for("power_daily_t2mmax_10.00_20.00_2000_2001")["url"]
    assert stored == power.daily_url(10.0, 20.0, 2000, 2001) and "start=20000101" in stored and "end=20011231" in stored


# ---- honest labels ----------------------------------------------------------------------------------------------
def test_root_zone_soil_moisture_is_labelled_as_a_model_index(azraq):
    c, e, w = azraq
    g = w["GWETROOT"]
    assert g["unit"] == "soil-wetness index (0-1)"
    assert "model soil-wetness index (MERRA-2 via POWER)" in g["source"] and g["source"].startswith("NASA POWER · GWETROOT")
    t = e["GWETROOT"]["test_on"]
    assert "model soil-wetness index (MERRA-2 via POWER)" in t and "small absolute change" in t and "not measured moisture" in t
    assert f"{g['stats']['total_change']:+.3f} index units since {g['start_year']}" in t          # the number is the computed one


def test_surface_soil_moisture_gets_the_same_label(azraq):
    _, e, w = azraq
    assert "model soil-wetness index (MERRA-2 via POWER)" in w["GWETTOP"]["source"]
    assert "model soil-wetness index (MERRA-2 via POWER)" in e["GWETTOP"]["test_on"]


def test_small_is_only_said_when_the_change_is_small():
    tr = lambda tc: SimpleNamespace(total_change=tc, first_year=1981)  # noqa: E731
    assert "small absolute change" in case_builder.expert_note("GWETROOT", tr(-0.011), "Azraq")
    assert "small absolute change" not in case_builder.expert_note("GWETROOT", tr(-0.2), "Azraq")
    assert "-0.200 index units since 1981" in case_builder.expert_note("GWETROOT", tr(-0.2), "Azraq")


def test_rainfall_carries_the_cell_size_caveat(azraq):
    _, e, w = azraq
    assert "~0.5 deg cell" in w["PRECTOTCORR"]["source"] and "may read higher than a local station" in w["PRECTOTCORR"]["source"]
    t = e["PRECTOTCORR"]["test_on"]
    assert "~0.5 deg" in t and "uplands" in t and "rainfall may be higher than the Azraq station" in t


def test_other_variables_are_not_touched(azraq):
    _, e, w = azraq
    assert w["T2M"]["source"] == "NASA POWER · T2M" and " · data:" not in e["T2M"]["test_on"]
    assert e["HOT_DAYS"]["test_on"] == "annual values"


def test_labels_do_not_change_any_statistic(azraq):
    c, e, w = azraq
    m = cache.load_df("power_monthly_31.88_36.83_1981_2025")
    tr = stats.trend(m["GWETROOT"], seasonal=True)
    assert w["GWETROOT"]["stats"]["p"] == tr.p and w["GWETROOT"]["stats"]["total_change"] == tr.total_change
