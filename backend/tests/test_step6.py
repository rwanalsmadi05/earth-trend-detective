"""Step 6: GET /grid, GET /twist, GET /lifetime. Logic on synthetic grids with planted trends; contract on real cached data."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import cache, grid, stats
from app.main import app
from tsutil import TSC, keys_match, tsc_ok

client = TestClient(app)
IDX = pd.date_range("1981-01-01", periods=45 * 12, freq="MS")
YEARS = np.arange(len(IDX)) / 12.0
needs_tsc = pytest.mark.skipif(not TSC.exists(), reason="frontend/node_modules not installed")
have_grid = grid.n_cached() == len(grid.points())
needs_grid = pytest.mark.skipif(not have_grid, reason="grid not prefetched: python prefetch.py --grid")


# ---- synthetic grid: planted trends + noise, injected in place of the POWER cache -----------------------------------
def synth(slope, seed, noise=0.5):
    rng = np.random.default_rng(seed)
    season = 8 * np.sin(2 * np.pi * (IDX.month - 1) / 12)
    return pd.DataFrame({"T2M": 15 + season + slope * YEARS + rng.normal(0, noise, len(IDX))}, index=IDX)


def install_grid(monkeypatch, tmp_path, slopes):
    """slopes: {(lat, lon): slope per year}. Replaces the grid points and the per-point cache with synthetic data."""
    pts = list(slopes)
    frames = {p: synth(s, i) for i, (p, s) in enumerate(slopes.items())}
    monkeypatch.setattr(grid, "points", lambda *a, **k: pts)
    monkeypatch.setattr(grid, "n_cached", lambda *a, **k: len(pts))
    monkeypatch.setattr(grid, "fetched_date", lambda *a, **k: "2026-01-01")
    monkeypatch.setattr(grid, "RESULTS_DIR", tmp_path)
    grid._MEM.clear()
    inv = {grid.point_key(*p): f for p, f in frames.items()}
    monkeypatch.setattr(cache, "load_df", lambda key, _o=cache.load_df: inv.get(key, _o(key)))
    return pts


def mixed_grid():
    """3 clearly rising cells, 2 clearly falling cells, 40 pure-noise cells."""
    s = {}
    for i in range(45):
        s[(29.0 + 0.5 * (i // 9), 34.0 + 0.5 * (i % 9))] = 0.0
    keys = list(s)
    for k in keys[:3]:
        s[k] = 0.06
    for k in keys[3:5]:
        s[k] = -0.06
    return s


def test_every_cell_gets_the_same_test_as_a_witness(monkeypatch, tmp_path):
    slopes = mixed_grid()
    install_grid(monkeypatch, tmp_path, slopes)
    res = grid.compute("T2M")
    cell = res["cells"][0]
    direct = stats.trend(synth(0.06, 0)["T2M"], seasonal=True)
    assert cell["value"] == pytest.approx(direct.total_change, rel=1e-3)           # Sen's total on annual means, deg C
    assert cell["p"] == pytest.approx(direct.p, rel=1e-3)                           # same monthly-anomaly Hamed-Rao (lag cap 12)
    assert res["years"] == list(range(1981, 2026)) and all(len(c["series"]) == len(res["years"]) for c in res["cells"])


def test_bh_fdr_is_applied_across_cells_and_blocks_noise(monkeypatch, tmp_path):
    install_grid(monkeypatch, tmp_path, mixed_grid())
    cells = grid.compute("T2M")["cells"]
    p, q = np.array([c["p"] for c in cells]), np.array([c["q"] for c in cells])
    assert (q >= p - 1e-12).all()                                                   # BH never lowers a p-value
    assert all(c["significant"] == (c["q"] < 0.05) for c in cells)
    assert all(c["verdict"] == ("CONFIRMED" if c["significant"] else "NOT PROVEN") for c in cells)
    sig = [c for c in cells if c["significant"]]
    assert {(c["lat"], c["lon"]) for c in sig} >= set(list(mixed_grid())[:5])      # all 5 planted trends found
    assert len(sig) <= 7                                                            # at most a couple of noise cells slip through
    assert (p < 0.05).sum() >= len(sig)                                             # FDR is at least as strict as raw 0.05
    ref = stats.benjamini_hochberg(p, 0.05)[1]
    assert np.allclose(q, ref, rtol=1e-3)                                           # identical to the BH used elsewhere


def test_signs_follow_the_planted_trends(monkeypatch, tmp_path):
    slopes = mixed_grid()
    install_grid(monkeypatch, tmp_path, slopes)
    by = {(c["lat"], c["lon"]): c for c in grid.compute("T2M")["cells"]}
    for k, sl in slopes.items():
        if sl > 0:
            assert by[k]["value"] > 0 and by[k]["significant"]
        if sl < 0:
            assert by[k]["value"] < 0 and by[k]["significant"]


def test_grid_response_shape_units_and_bbox_filter(monkeypatch, tmp_path):
    slopes = mixed_grid()
    install_grid(monkeypatch, tmp_path, slopes)
    g = grid.grid_response("T2M")
    assert g["display_unit"] == "°C" and g["words"] == {"up": "hotter", "down": "cooler"} and g["fdr"] == "benjamini-hochberg"
    assert g["step"] == 0.5 and g["bbox"] == [34.0, 29.0, 40.0, 34.0] and len(g["cells"]) == len(slopes)
    sub = grid.grid_response("T2M", (34.0, 29.0, 35.0, 29.5))
    assert 0 < len(sub["cells"]) < len(g["cells"]) and all(34 <= c["lon"] <= 35 and 29 <= c["lat"] <= 29.5 for c in sub["cells"])


# ---- The Twist --------------------------------------------------------------------------------------------------
def planted(monkeypatch, tmp_path, a_slope, others):
    """Case place 'azraq' (31.88, 36.83) -> nearest grid point (32.0, 37.0) gets a_slope; `others` {(lat, lon): slope}."""
    slopes = {(32.0, 37.0): a_slope}
    slopes.update(others)
    for i in range(30):
        slopes.setdefault((29.0 + 0.5 * (i // 6), 34.0 + 0.5 * (i % 6)), 0.0)
    install_grid(monkeypatch, tmp_path, slopes)
    monkeypatch.setattr(grid, "GRID_VARIABLES", ["T2M"])
    return slopes


def test_twist_found_picks_the_strongest_opposite_significant_cell(monkeypatch, tmp_path):
    planted(monkeypatch, tmp_path, -0.05, {(33.0, 35.0): 0.03, (33.5, 35.5): 0.07, (30.0, 36.0): -0.07})
    t = grid.twist("azraq")
    assert t["found"] and t["variable"] == "T2M" and t["label"] == "Temperature"
    assert t["a"]["name"] == "Azraq" and (t["a"]["lat"], t["a"]["lon"]) == (32.0, 37.0)
    assert t["a"]["value"] < 0 < t["b"]["value"]                                    # opposite signs
    assert t["a"]["verdict"] == t["b"]["verdict"] == "CONFIRMED"
    assert (t["b"]["lat"], t["b"]["lon"]) in [(33.0, 35.0), (33.5, 35.5)]           # never the same-sign cell at (30.0, 36.0)
    assert "cooler" in t["sentence"] and "hotter" in t["sentence"] and "false-discovery" in t["sentence"]


def test_twist_not_found_when_everything_moves_the_same_way(monkeypatch, tmp_path):
    planted(monkeypatch, tmp_path, 0.05, {(33.0, 35.0): 0.04, (33.5, 35.5): 0.06})
    assert grid.twist("azraq") == {"found": False}


def test_twist_not_found_when_the_case_place_has_no_significant_trend(monkeypatch, tmp_path):
    planted(monkeypatch, tmp_path, 0.0, {(33.0, 35.0): 0.06, (33.5, 35.5): -0.06})
    assert grid.twist("azraq") == {"found": False}


def test_twist_opposite_cell_must_itself_survive_fdr(monkeypatch, tmp_path):
    planted(monkeypatch, tmp_path, 0.05, {(33.0, 35.0): -0.001})                      # tiny, non-significant opposite trend
    assert grid.twist("azraq") == {"found": False}


def test_twist_unknown_case_is_none():
    assert grid.twist("atlantis") is None


@needs_tsc
def test_twist_found_true_shape_typechecks(monkeypatch, tmp_path):
    planted(monkeypatch, tmp_path, -0.05, {(33.0, 35.0): 0.06})
    t = grid.twist("azraq")
    assert t["found"] and keys_match(t, "TwistResponse")
    ok, out = tsc_ok(tmp_path, "TwistResponse", t, "twist_found")
    assert ok, out
    for side in ("a", "b"):
        assert keys_match(t[side], "TwistSide")


# ---- real cached data: contract ---------------------------------------------------------------------------------
@needs_grid
def test_grid_endpoint_contract():
    r = client.get("/grid", params={"variable": "T2M", "bbox": "34,29,40,34"})
    assert r.status_code == 200
    g = r.json()
    assert keys_match(g, "GridResponse") and all(keys_match(c, "GridCell") for c in g["cells"])
    assert g["variable"] == "T2M" and g["bbox"] == [34.0, 29.0, 40.0, 34.0] and g["fdr"] == "benjamini-hochberg" and g["step"] == 0.5
    assert len(g["cells"]) == 143 and g["years"] == list(range(1981, 2026))
    for c in g["cells"]:
        assert 29 <= c["lat"] <= 34 and 34 <= c["lon"] <= 40 and len(c["series"]) == len(g["years"])
        assert c["significant"] == (c["q"] < 0.05) and c["verdict"] == ("CONFIRMED" if c["significant"] else "NOT PROVEN")


@needs_grid
@needs_tsc
@pytest.mark.parametrize("variable", ["T2M", "PRECTOTCORR", "GWETROOT", "ALLSKY_SFC_SW_DWN"])
def test_grid_response_typechecks_against_types_ts(variable, tmp_path):
    g = client.get("/grid", params={"variable": variable}).json()
    ok, out = tsc_ok(tmp_path, "GridResponse", g, f"grid_{variable}")
    assert ok, out


@needs_grid
def test_grid_units_words_and_year_axis_per_variable():
    t = client.get("/grid", params={"variable": "PRECTOTCORR"}).json()
    assert t["display_unit"] == "%" and t["words"] == {"up": "more rain", "down": "less rain"}
    s = client.get("/grid", params={"variable": "ALLSKY_SFC_SW_DWN"}).json()
    assert s["years"][0] == 1984                                                    # solar radiation starts in 1984: slider axis follows the data
    sea = client.get("/grid", params={"variable": "GWETROOT"}).json()
    assert len(sea["cells"]) < 143                                                  # sea cells have no soil moisture: skipped, not invented


@needs_grid
def test_grid_bbox_subset_and_validation():
    sub = client.get("/grid", params={"variable": "T2M", "bbox": "35,31,36,32"}).json()
    assert 0 < len(sub["cells"]) < 143 and sub["bbox"] == [35.0, 31.0, 36.0, 32.0]
    assert client.get("/grid", params={"variable": "T2M", "bbox": "36,31,35,32"}).status_code == 422
    assert client.get("/grid", params={"variable": "T2M", "bbox": "a,b,c,d"}).status_code == 422
    assert client.get("/grid", params={"variable": "HOT_DAYS"}).status_code == 422     # not a POWER monthly variable
    assert client.get("/grid", params={"variable": "NDVI"}).status_code == 422
    assert client.get("/grid", params={"variable": "BOGUS"}).status_code == 422


@needs_grid
@needs_tsc
def test_twist_endpoint_contract_on_real_data(tmp_path):
    r = client.get("/twist", params={"case_id": "azraq"})
    assert r.status_code == 200
    t = r.json()
    assert isinstance(t["found"], bool) and keys_match(t, "TwistResponse")
    if not t["found"]:
        assert set(t) == {"found"}                                                  # nothing else: the UI hides The Twist
    ok, out = tsc_ok(tmp_path, "TwistResponse", t, "twist_real")
    assert ok, out
    assert client.get("/twist", params={"case_id": "atlantis"}).status_code == 404


@needs_grid
def test_twist_found_false_is_consistent_with_the_grid_data():
    # if /twist says none, then for every variable the significant cells do not include both signs at once with the case cell
    t = client.get("/twist", params={"case_id": "azraq"}).json()
    if t["found"]:
        assert t["a"]["value"] * t["b"]["value"] < 0 and t["a"]["verdict"] == t["b"]["verdict"] == "CONFIRMED"
        return
    for v in grid.GRID_VARIABLES:
        cells = grid.compute(v)["cells"]
        a = min(cells, key=lambda c: (c["lat"] - 31.88) ** 2 + (c["lon"] - 36.83) ** 2)
        if a["significant"]:
            assert not any(c["significant"] and c["value"] * a["value"] < 0 for c in cells), v


# ---- /lifetime ---------------------------------------------------------------------------------------------------
@needs_tsc
def test_lifetime_contract():
    r = client.get("/lifetime", params={"place": "Azraq", "birth_year": 2005})
    assert r.status_code == 200
    d = r.json()
    assert keys_match(d, "LifetimeResponse") and all(keys_match(i, "LifetimeItem") for i in d["items"])
    assert (d["birth_year"], d["end_year"], d["years"]) == (2005, 2025, 20)
    assert [i["variable"] for i in d["items"]] == ["T2M", "PRECTOTCORR", "HOT_DAYS"]
    assert [i["display_unit"] for i in d["items"]] == ["°C", "%", " days"]
    assert d["place"]["name"] == "Azraq" and d["place"]["lat"] == 31.88


@needs_tsc
def test_lifetime_typechecks_against_types_ts(tmp_path):
    ok, out = tsc_ok(tmp_path, "LifetimeResponse", client.get("/lifetime", params={"place": "Azraq", "birth_year": 2005}).json(), "lifetime")
    assert ok, out


def test_lifetime_verdicts_and_headlines_come_from_the_statistics():
    d = client.get("/lifetime", params={"place": "Azraq", "birth_year": 2005}).json()
    for i in d["items"]:
        assert i["verdict"] == ("CONFIRMED" if i["p"] < 0.05 else "NOT PROVEN")
        assert f"since {d['birth_year']}" in i["headline"]
        assert i["direction"] == ("up" if i["value"] >= 0 else "down")
        if i["verdict"] == "NOT PROVEN":
            assert "could be chance" in i["headline"] and not any(ch.isdigit() for ch in i["headline"].replace(str(d["birth_year"]), ""))
    t2m = d["items"][0]
    assert f"{abs(t2m['value']):.1f} °C" in t2m["headline"] or t2m["verdict"] == "NOT PROVEN"


def test_lifetime_equals_the_same_statistics_run_by_hand():
    d = client.get("/lifetime", params={"place": "Azraq", "birth_year": 2005}).json()
    m = cache.load_df("power_monthly_31.88_36.83_1981_2025")
    tr = stats.trend(m["T2M"][m.index.year >= 2005], seasonal=True)
    assert d["items"][0]["value"] == pytest.approx(tr.total_change) and d["items"][0]["p"] == pytest.approx(tr.p)


def test_lifetime_birth_year_is_clamped_to_the_data():
    early = client.get("/lifetime", params={"place": "Azraq", "birth_year": 1950}).json()
    assert early["birth_year"] == 1981 and early["years"] == 44
    late = client.get("/lifetime", params={"place": "Azraq", "birth_year": 2024}).json()
    assert late["birth_year"] == 2016 and late["end_year"] == 2025 and late["years"] == 9        # hot-days needs >= 10 yearly values


def test_lifetime_unknown_place_is_422():
    assert client.get("/lifetime", params={"place": "zzzz nowhere", "birth_year": 2005}).status_code in (422, 503)
