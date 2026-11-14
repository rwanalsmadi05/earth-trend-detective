"""API contract tests against the real cached Azraq data (run `python prefetch.py --case azraq` first)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
TYPES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "types.ts"
TSC = Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / ".bin" / ("tsc.cmd" if shutil.which("cmd") else "tsc")


@pytest.fixture(scope="module")
def azraq():
    r = client.post("/case", json={"question": "Is Azraq drying up?"})
    assert r.status_code == 200, r.text
    return r.json()


def _ts_keys(src, interface):
    block = src.split(f"export interface {interface} {{")[1].split("\n}")[0]
    req, opt = set(), set()
    for ln in block.splitlines():
        ln = ln.split("//")[0]
        while re.search(r"\{[^{}]*\}", ln):        # drop nested object types: only top-level keys count
            ln = re.sub(r"\{[^{}]*\}", "T", ln)
        for part in ln.split(";"):
            if ":" in part:
                k = part.split(":")[0].strip()
                if k:
                    (opt if k.endswith("?") else req).add(k.rstrip("?"))
    return req, opt


def test_top_level_keys_match_types_ts(azraq):
    req, opt = _ts_keys(TYPES_TS.read_text(encoding="utf-8"), "CaseResponse")
    assert req <= set(azraq) <= req | opt          # every required key present, nothing the type does not know
    assert "expert" in opt and "expert" not in azraq  # the client merges POST /case/expert into case.expert itself


def test_expert_items_match_types_ts_exactly():
    r = client.post("/case/expert", json={"question": "Is Azraq drying up?"}).json()["variables"]
    req, opt = _ts_keys(TYPES_TS.read_text(encoding="utf-8"), "ExpertItem")
    for item in r.values():
        assert set(item) == req and not opt


def test_verdict_is_decided_by_p_value_only(azraq):
    for w in azraq["witnesses"]:
        assert (w["verdict"] == "CONFIRMED") == (w["stats"]["p"] < 0.05)
        assert w["direction"] == ("up" if w["stats"]["sen_per_decade"] >= 0 else "down")
    assert azraq["verdict"]["total"] == len(azraq["witnesses"])


def test_unknown_place_is_422_not_a_crash():
    r = client.post("/case", json={"question": "zzzqqq nowhere", "lat": None})
    assert r.status_code in (422, 503)


def test_manual_variable_selection_works_without_llm():
    r = client.post("/case", json={"question": "Azraq", "variables": ["RH2M", "T2M_MAX"]})
    assert r.status_code == 200
    assert [w["variable"] for w in r.json()["witnesses"]] == ["RH2M", "T2M_MAX"]


def test_image_route_serves_cached_jpeg_and_rejects_traversal(azraq):
    url = azraq["witnesses"][0]["images"]["before"]["url"]
    assert url.startswith("/api/images/")
    assert client.get(url.replace("/api", "", 1)).headers["content-type"] == "image/jpeg"
    assert client.get("/images/..%5C..%5Cmeta.json").status_code == 404


@pytest.mark.skipif(not TSC.exists(), reason="frontend/node_modules not installed")
def test_response_typechecks_against_the_real_types_ts(azraq, tmp_path):
    """Compile the actual JSON as a CaseResponse literal with the frontend's own TypeScript:
    catches missing/extra fields, wrong literal unions and wrong value types."""
    ts = tmp_path / "check.ts"
    expert = client.post("/case/expert", json={"question": "Is Azraq drying up?"}).json()["variables"]
    merged = {**azraq, "expert": expert}                 # exactly what client.ts builds
    # types.ts is the frontend's file. Fields agreed in coordination but not yet in it (image `bbox`, a required
    # `cleaned_question`) are layered on locally, so this passes whether or not the frontend has added them yet.
    ts.write_text(
        f'import type {{ CaseResponse, Witness, SatImage }} from "{TYPES_TS.as_posix()[:-3]}";\n'
        "type BBox = [number, number, number, number];\n"
        "type Img = SatImage & { bbox: BBox };\n"
        'type W = Omit<Witness, "images"> & { images: { before: Img; after: Img } };\n'
        'type Case = Omit<CaseResponse, "witnesses" | "cleaned_question"> & { witnesses: W[]; cleaned_question: string };\n'
        f"export const x: Case = {json.dumps(merged, ensure_ascii=False)};\n", encoding="utf-8")
    out = subprocess.run([str(TSC), "--noEmit", "--strict", "--skipLibCheck", "--target", "es2020",
                          "--module", "esnext", "--moduleResolution", "bundler", str(ts)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_headline_is_data_derived_and_accurate(azraq):
    h = azraq["verdict"]["headline"]
    ws = azraq["witnesses"]
    k = sum(w["verdict"] == "CONFIRMED" for w in ws)
    assert azraq["verdict"]["confirmed"] == k and azraq["verdict"]["total"] == len(ws)
    assert h.startswith(f"{k} of {len(ws)} witnesses show a significant change in Azraq")
    for w in ws:                                  # every confirmed witness is described, in its real direction
        if w["verdict"] == "CONFIRMED":
            from app.case_builder import PHRASE
            assert PHRASE[w["variable"]][0 if w["direction"] == "up" else 1] in h
    assert "drier" not in h or any(w["variable"] in ("GWETROOT", "GWETTOP", "RH2M") and w["direction"] == "down" for w in ws)


def test_headline_no_confirmed_and_borderline_wording():
    from app.case_builder import case_headline
    w = [{"variable": "T2M", "direction": "up", "verdict": "NOT PROVEN", "stats": {"p": 0.4}},
         {"variable": "PRECTOTCORR", "direction": "down", "verdict": "NOT PROVEN", "stats": {"p": 0.2}}]
    ex = {"T2M": {"borderline": False}, "PRECTOTCORR": {"borderline": False}}
    assert case_headline(w, ex, "X") == "No witness shows a significant change in X (0 of 2)"
    w[1].update(verdict="CONFIRMED", stats={"p": 0.04}); ex["PRECTOTCORR"]["borderline"] = True
    assert case_headline(w, ex, "X") == "1 of 2 witnesses show a significant change in X: less rain. Borderline: less rain (p = 0.04)"


def test_expert_endpoint_exposes_method_and_borderline_consistent_with_p(azraq):
    r = client.post("/case/expert", json={"question": "Is Azraq drying up?"})
    assert r.status_code == 200
    ex = r.json()["variables"]
    assert set(ex) == {w["variable"] for w in azraq["witnesses"]}
    for w in azraq["witnesses"]:
        e = ex[w["variable"]]
        assert e["p"] == w["stats"]["p"] and e["method"] in ("hamed-rao", "trend-free pre-whitening", "none")
        assert e["borderline"] == (w["verdict"] == "CONFIRMED" and 0.01 <= w["stats"]["p"] < 0.05)


def test_every_witness_headline_uses_the_same_since_wording_and_matches_its_numbers(azraq):
    for w in azraq["witnesses"]:
        h, st = w["headline"], w["stats"]
        assert "1980s" not in h and "than in" not in h and "over 19" not in h
        assert f"since {w['start_year']}" in h
        if w["verdict"] == "CONFIRMED" and w["variable"] in ("T2M", "T2M_MAX"):
            assert f"{abs(st['total_change']):.1f} °C" in h
        elif w["verdict"] == "CONFIRMED" and w["variable"] == "HOT_DAYS":
            assert f"{abs(st['total_change']):.0f} " in h
        elif w["verdict"] == "CONFIRMED":
            assert f"{abs(st['pct_change']):.0f}%" in h


def test_not_proven_headline_also_says_since():
    from app.case_builder import _headline
    from app.stats import TrendResult
    tr = TrendResult(n=540, n_tested=540, tau=0.01, p=0.6, sen_per_decade=0.01, total_change=0.04, pct_change=1.0,
                     baseline=1.0, verdict="NOT PROVEN", direction="up", method="hamed-rao", reason=None,
                     borderline=False, first_year=2000, last_year=2025, annual=[])
    assert _headline("NDVI", tr) == "No clear change in plant greenness since 2000 — could be chance"
    assert _headline("NDVI", tr, "ar") == "لا يوجد تغيّر واضح في الغطاء النباتي منذ 2000 (قد يكون صدفة)"


def test_not_proven_headlines_are_plain_language_with_no_exact_numbers(azraq):
    # general-audience wording: only the year may appear; exact numbers live in the expert data
    from app.case_builder import _headline
    from app.stats import TrendResult
    for vid in ("T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS", "NDVI", "RH2M"):
        tr = TrendResult(n=540, n_tested=540, tau=0.01, p=0.6, sen_per_decade=0.0123, total_change=0.0456, pct_change=1.7,
                         baseline=1.0, verdict="NOT PROVEN", direction="up", method="hamed-rao", reason=None,
                         borderline=False, first_year=1981, last_year=2025, annual=[])
        h = _headline(vid, tr)
        assert re.sub(r"\b(19|20)\d\d\b", "", h).count("0") == 0 and not re.search(r"\d", re.sub(r"\b(19|20)\d\d\b", "", h)), h
        assert h.startswith("No clear change in ") and h.endswith("— could be chance")
    for w in azraq["witnesses"]:
        if w["verdict"] == "NOT PROVEN":
            assert not re.search(r"\d", re.sub(r"\b(19|20)\d\d\b", "", w["headline"]))


def test_cleaned_question_is_always_returned(azraq):
    assert isinstance(azraq["cleaned_question"], str) and azraq["cleaned_question"] == "Is Azraq drying up?"
    r = client.post("/case", json={"question": "  is   azraq drying up ", "variables": ["T2M"]}).json()
    assert r["cleaned_question"] == "Is azraq drying up?"       # manual path: rules tidy-up (whitespace, capital, ?)


def test_image_bbox_is_west_south_east_north_and_centred_on_the_place(azraq):
    lat, lon = azraq["place"]["lat"], azraq["place"]["lon"]
    for w in azraq["witnesses"]:
        for img in (w["images"]["before"], w["images"]["after"]):
            west, south, east, north = img["bbox"]
            assert west < east and south < north                      # [west, south, east, north]
            assert abs((west + east) / 2 - lon) < 1e-3 and abs((south + north) / 2 - lat) < 1e-3
            assert west <= lon <= east and south <= lat <= north
    # each witness kind has its own image, not one shared picture
    urls = {w["variable"]: w["images"]["before"]["url"] for w in azraq["witnesses"]}
    assert len(set(urls.values())) == len(urls)
