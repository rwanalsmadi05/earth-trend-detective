"""GET /game/round: contract against the real types.ts, and proof that every round is a REAL series with its REAL verdict."""
import math
import random

import pytest
from fastapi.testclient import TestClient

from app import cache, game, grid, stats
from app.main import app
from app.variables import VARIABLES
from tsutil import TSC, keys_match, tsc_ok

client = TestClient(app)
needs_tsc = pytest.mark.skipif(not TSC.exists(), reason="frontend/node_modules not installed")
AZRAQ = (31.88, 36.83)


def rnd(**params):
    return client.get("/game/round", params={"case_id": "azraq", **params})


def recompute(d):
    """Run the real statistics again, from the cache, for the place + variable a round claims to be about."""
    vid, la, lo = d["variable"], d["place"]["lat"], d["place"]["lon"]
    v = VARIABLES[vid]
    if v["kind"] == "modis":
        return stats.trend(cache.load_df(f"modis_ndvi_{la:.2f}_{lo:.2f}_2025")["ndvi"], seasonal=True)
    if v["kind"] == "power_daily":
        h = cache.load_df(f"power_daily_t2mmax_{la:.2f}_{lo:.2f}_1981_2025")
        return stats.trend((h["T2M_MAX"] > 35).groupby(h.index.year).sum().astype(float), seasonal=False)
    df = cache.load_df(grid.point_key(la, lo))
    return stats.trend(df[v["col"]], seasonal=True)


# ---- contract ---------------------------------------------------------------------------------------------------
def test_round_keys_match_types_ts():
    d = rnd().json()
    assert keys_match(d, "GameRound")
    assert set(d["place"]) == {"name", "lat", "lon"} and set(d["period"]) == {"start", "end"}
    assert set(d["data_label"]) == {"origin", "fetched"} and all(set(p) == {"year", "value"} for p in d["series"])


@needs_tsc
@pytest.mark.parametrize("want", [None, "CONFIRMED", "NOT PROVEN"])
def test_round_typechecks_against_types_ts(want, tmp_path):
    params = {"want": want} if want else {}
    for i in range(3):
        r = rnd(**params)
        assert r.status_code == 200
        ok, out = tsc_ok(tmp_path, "GameRound", r.json(), f"round_{want}_{i}".replace(" ", "_"))
        assert ok, out


# ---- want / exclude ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("want", ["CONFIRMED", "NOT PROVEN"])
def test_want_is_honoured_and_verdict_is_the_p_value_rule(want):
    for _ in range(12):                                            # random pick: look at several draws
        d = rnd(want=want).json()
        assert d["verdict"] == want
        assert (d["p"] < 0.05) == (want == "CONFIRMED")


def test_without_want_both_outcomes_can_occur():
    seen = {rnd().json()["verdict"] for _ in range(40)}
    assert seen == {"CONFIRMED", "NOT PROVEN"}


def test_exclude_is_honoured_and_a_frontend_style_session_never_repeats_a_variable():
    used = []
    for i in range(6):
        want = "CONFIRMED" if i % 2 == 0 else "NOT PROVEN"
        r = rnd(want=want, exclude=",".join(used))
        assert r.status_code == 200, (i, want, used, r.text)
        d = r.json()
        assert d["verdict"] == want and d["variable"] not in used
        used.append(d["variable"])
    assert len(set(used)) == 6


def test_empty_exclude_and_unknown_inputs():
    assert rnd(exclude="").status_code == 200
    assert rnd(want="MAYBE").status_code == 422
    assert rnd(exclude="T2M,BOGUS").status_code == 422
    assert client.get("/game/round", params={"case_id": "atlantis"}).status_code == 404


def test_excluding_everything_is_a_404_not_a_fabricated_round():
    assert rnd(exclude=",".join(game.ALL_VARIABLES)).status_code == 404


# ---- real series, real verdicts ---------------------------------------------------------------------------------
def test_every_round_is_the_real_statistics_recomputed_from_the_cache():
    for want in ("CONFIRMED", "NOT PROVEN", None) * 4:
        d = rnd(**({"want": want} if want else {})).json()
        tr = recompute(d)
        assert d["verdict"] == tr.verdict and d["p"] == tr.p and d["tau"] == tr.tau and d["sen_per_decade"] == tr.sen_per_decade
        assert d["n"] == tr.n and d["series"] == tr.annual            # the plotted points are the tested series, untouched
        assert d["period"] == {"start": tr.annual[0]["year"], "end": tr.annual[-1]["year"]}


def test_series_are_real_enough_to_play_with():
    for _ in range(15):
        s = rnd().json()["series"]
        years = [p["year"] for p in s]
        assert len(s) >= 8 and years == sorted(years) and len(set(years)) == len(years)
        assert all(math.isfinite(p["value"]) for p in s)
        assert len({p["value"] for p in s}) > 1                         # not a flat line


def test_label_unit_and_borderline_are_consistent():
    for _ in range(20):
        d = rnd().json()
        assert d["label"] == VARIABLES[d["variable"]]["label"] and d["unit"] == VARIABLES[d["variable"]]["unit"]
        assert d["borderline"] == (d["verdict"] == "CONFIRMED" and 0.01 <= d["p"] < 0.05)


def test_explanation_matches_the_verdict_and_quotes_the_computed_p():
    for _ in range(20):
        d = rnd().json()
        if d["verdict"] == "CONFIRMED":
            assert d["explanation"].startswith("Real trend:")
            assert "borderline" in d["explanation"] if d["borderline"] else "Chance alone" in d["explanation"]
        else:
            assert d["explanation"].startswith("Just noise")
        txt = "p < 0.0001" if d["p"] < 1e-4 else f"p = {d['p']:.3f}"
        assert txt in d["explanation"]


# ---- where the series come from ---------------------------------------------------------------------------------
def test_case_place_is_used_first():
    ds = [rnd().json() for _ in range(25)]
    assert any((d["place"]["lat"], d["place"]["lon"]) == AZRAQ for d in ds)
    assert all(d["place"]["name"] == "Azraq" for d in ds if (d["place"]["lat"], d["place"]["lon"]) == AZRAQ)


def test_when_the_case_place_has_none_left_a_real_nearby_grid_cell_is_used():
    # exclude every variable that is NOT PROVEN at Azraq: the only NOT PROVEN rounds left must come from other real cells
    azraq_np = [v for v in game.ALL_VARIABLES if (h := game._trend_at(*AZRAQ, v)) and h[0].verdict == "NOT PROVEN"]
    assert azraq_np, "Azraq should have at least one NOT PROVEN series (NDVI)"
    d = rnd(want="NOT PROVEN", exclude=",".join(azraq_np)).json()
    assert (d["place"]["lat"], d["place"]["lon"]) != AZRAQ
    assert d["place"]["name"].startswith("near ") or d["place"]["name"][0].isdigit()   # "near <town>" or plain coordinates
    assert d["verdict"] == "NOT PROVEN" and d["variable"] not in azraq_np
    assert 29 <= d["place"]["lat"] <= 34 and 34 <= d["place"]["lon"] <= 40       # a real grid cell
    tr = recompute(d)
    assert tr.verdict == "NOT PROVEN" and d["series"] == tr.annual


def test_fallback_cells_are_labelled_near_a_town_not_as_the_town():
    azraq_np = [v for v in game.ALL_VARIABLES if (h := game._trend_at(*AZRAQ, v)) and h[0].verdict == "NOT PROVEN"]
    for _ in range(10):
        d = rnd(want="NOT PROVEN", exclude=",".join(azraq_np)).json()
        assert d["place"]["name"].startswith("near ") or d["place"]["name"][0].isdigit()


def test_selection_uses_the_rng_so_tests_can_pin_it(monkeypatch):
    monkeypatch.setattr(game, "_rng", random.Random(7))
    a = [rnd().json()["variable"] for _ in range(5)]
    monkeypatch.setattr(game, "_rng", random.Random(7))
    assert a == [rnd().json()["variable"] for _ in range(5)]
