"""Explanation guards + LLM-mocked explain(): the LLM may never put an invented number or a wrong verdict in front of the user."""
import pytest

from app import explain, llm
from app.explain import LLMExplain, LLMHint, LLMWitnessText, allowed_numbers, build_context, hint_ok, numbers_ok, verdict_ok


def mini():
    case = {
        "place": {"name": "Azraq", "name_ar": "الأزرق"}, "period": {"start": 1981, "end": 2025},
        "verdict": {"confirmed": 1, "total": 2, "headline": "1 of 2 witnesses show a significant change in Azraq: hotter"},
        "witnesses": [
            {"variable": "T2M", "label": "Temperature", "unit": "°C", "verdict": "CONFIRMED", "direction": "up",
             "headline": "2.2 °C hotter since 1981", "start_year": 1981,
             "stats": {"n": 540, "tau": 0.31, "p": 3.18e-18, "sen_per_decade": 0.4806, "total_change": 2.163, "pct_change": 11.9}},
            {"variable": "NDVI", "label": "Vegetation (NDVI)", "unit": "index", "verdict": "NOT PROVEN", "direction": "down",
             "headline": "No clear change in plant greenness since 2000 — could be chance", "start_year": 2000,
             "stats": {"n": 311, "tau": -0.05, "p": 0.41, "sen_per_decade": -0.0012, "total_change": -0.003, "pct_change": -0.9}},
        ],
        "chain": [{"from": "T2M", "to": "NDVI", "lag_months": 2, "r": -0.31}], "hints": [],
    }
    expert = {"T2M": {"borderline": False}, "NDVI": {"borderline": False}}
    return case, expert


ALLOWED = allowed_numbers(build_context(*mini()))


# ---- numbers_ok ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["2.2 °C hotter since 1981", "about 2 °C warmer", "p = 3.2e-18", "p = 0.41", "tau of 0.31",
                                  "1 of 2 witnesses", "311 months", "ارتفعت 2.2 °م منذ 1981", "ارتفعت ٢٫٢" .replace("٫", ".") + " °م",
                                  "above 35 °C", "the 0.05 level", "a lag of 2 months, r = -0.31", "no numbers here at all"])
def test_numbers_that_were_computed_are_accepted(text):
    assert numbers_ok(text, ALLOWED)[0], text


@pytest.mark.parametrize("text,bad", [("40% hotter", "40"), ("warmed by 3.5 °C", "3.5"), ("since the 1980s", "1980"),
                                      ("p = 0.02", "0.02"), ("a 7 month lag", "7"), ("3 of 5 witnesses", "5"),
                                      ("ارتفعت ٩ درجات", "٩")])
def test_invented_numbers_are_rejected(text, bad):
    ok, offenders = numbers_ok(text, ALLOWED)
    assert not ok and offenders


def test_known_limitation_the_guard_checks_values_not_meaning():
    # 11.9 (pct_change) rounds to 12, so ANY "12" passes, even used for something else. The guard blocks invented
    # numbers; it cannot check what a sentence means. Documented in explain.py; the verdict guard + templates cover the rest.
    assert numbers_ok("a 12 month lag", ALLOWED)[0]


def test_numbers_only_match_when_rounded_the_way_the_text_rounds():
    assert numbers_ok("2.16 °C", ALLOWED)[0] and numbers_ok("2.2 °C", ALLOWED)[0]
    assert not numbers_ok("2.3 °C", ALLOWED)[0]          # 2.163 rounds to 2.2, not 2.3


# ---- verdict_ok ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,verdict,ok", [
    ("The test confirms a real trend.", "NOT PROVEN", False),
    ("This is statistically significant.", "NOT PROVEN", False),
    ("It is not significant; it could be chance.", "NOT PROVEN", True),
    ("The change is not proven.", "NOT PROVEN", True),
    ("There is no significant change.", "NOT PROVEN", True),
    ("هذا التغيّر مؤكد", "NOT PROVEN", False),
    ("التغيّر غير مثبت وقد يكون صدفة", "NOT PROVEN", True),
    ("The change is not proven.", "CONFIRMED", False),
    ("It could be chance.", "CONFIRMED", False),
    ("The data show a clear rise.", "CONFIRMED", True),
    ("التغيّر غير مثبت", "CONFIRMED", False),
    ("ارتفاع واضح", "CONFIRMED", True),
])
def test_verdict_guard(text, verdict, ok):
    assert verdict_ok(text, verdict) is ok


def test_hints_must_have_no_numbers_and_no_verdict_words():
    assert hint_ok("Notice the heat climbed first: did the soil follow?", ALLOWED)
    assert not hint_ok("The heat rose 2.2 degrees first.", ALLOWED)
    assert not hint_ok("This witness is confirmed, look closer.", ALLOWED)
    assert not hint_ok("Not proven yet, so keep digging.", ALLOWED)
    assert not hint_ok("", ALLOWED)


# ---- templates are themselves guarded ---------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_template_text_only_uses_computed_numbers_and_the_true_verdict(lang):
    case, ex = mini()
    t = explain.template_explanation(case, ex, lang)
    allowed = allowed_numbers(build_context(case, ex))
    for vid, text in t["witnesses"].items():
        assert numbers_ok(text, allowed)[0], text
        assert verdict_ok(text, {"T2M": "CONFIRMED", "NDVI": "NOT PROVEN"}[vid]), text
    assert numbers_ok(t["summary"], allowed)[0]
    assert ("correlation" in t["summary"]) if lang == "en" else ("ارتباط" in t["summary"])


# ---- explain() with a fake LLM ---------------------------------------------------------------------------------
def fake(monkeypatch, out=None, exc=None):
    def gen(system, prompt, schema, temperature=0.2):
        if exc:
            raise exc
        return out, "fake-model"
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", gen)


GOOD = LLMExplain(
    summary="One of the two witnesses passed the test: it got hotter in Azraq. The plant record is inconclusive.",
    witnesses=[LLMWitnessText(variable="T2M", text="It got about 2.2 °C hotter since 1981, and the test passed."),
               LLMWitnessText(variable="NDVI", text="The plant greenness change is not proven; it could be chance.")],
    hints=[LLMHint(after="T2M", text="Did the soil dry out after the heat rose?")])


def test_good_llm_text_is_used(monkeypatch):
    fake(monkeypatch, GOOD)
    r = explain.explain(*mini(), "en", use_cache=False)
    assert r["source"] == "gemini" and r["model"] == "fake-model" and r["rejected"] == []
    assert r["witnesses"]["T2M"].startswith("It got about 2.2") and r["hints"] == [{"after": "T2M", "text": "Did the soil dry out after the heat rose?"}]


def test_invented_number_is_rejected_and_replaced_by_the_template(monkeypatch):
    bad = GOOD.model_copy(update={"witnesses": [LLMWitnessText(variable="T2M", text="It got 4.7 °C hotter!"),
                                                GOOD.witnesses[1]]})
    fake(monkeypatch, bad)
    r = explain.explain(*mini(), "en", use_cache=False)
    assert "4.7" not in r["witnesses"]["T2M"] and r["witnesses"]["T2M"].startswith("Temperature: 2.2 °C hotter since 1981")
    assert any("T2M" in x and "4.7" in x for x in r["rejected"])
    assert r["witnesses"]["NDVI"].startswith("The plant greenness")       # the good one is kept


def test_wrong_verdict_is_rejected(monkeypatch):
    bad = GOOD.model_copy(update={"witnesses": [GOOD.witnesses[0],
                                                LLMWitnessText(variable="NDVI", text="Plants clearly declined: confirmed trend.")]})
    fake(monkeypatch, bad)
    r = explain.explain(*mini(), "en", use_cache=False)
    assert "Verdict: NOT PROVEN" in r["witnesses"]["NDVI"] and any("contradicts" in x for x in r["rejected"])


def test_invented_summary_number_and_bad_hints_are_dropped(monkeypatch):
    bad = LLMExplain(summary="Azraq warmed 9 degrees.", witnesses=GOOD.witnesses,
                     hints=[LLMHint(after="T2M", text="It rose 2.2 degrees: look!"), LLMHint(after="NDVI", text="This is proven, right?")])
    fake(monkeypatch, bad)
    r = explain.explain(*mini(), "en", use_cache=False)
    assert "9" not in r["summary"] and r["summary"].startswith("1 of 2 witnesses show a significant change in Azraq")
    assert r["hints"] == [] and len(r["rejected"]) >= 3


def test_hint_for_a_witness_that_does_not_exist_is_dropped(monkeypatch):
    fake(monkeypatch, GOOD.model_copy(update={"hints": [LLMHint(after="RH2M", text="Is the air drier?")]}))
    assert explain.explain(*mini(), "en", use_cache=False)["hints"] == []


def test_llm_failure_gives_template_and_a_reason(monkeypatch):
    fake(monkeypatch, exc=TimeoutError("timed out"))
    r = explain.explain(*mini(), "en", use_cache=False)
    assert r["source"] == "template" and "TimeoutError" in r["fallback_reason"] and r["witnesses"]["T2M"].startswith("Temperature:")


def test_no_key_gives_template(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    r = explain.explain(*mini(), "ar", use_cache=False)
    assert r["source"] == "template" and r["fallback_reason"] == "no LLM configured" and "الحكم" in r["witnesses"]["T2M"]


def test_llm_never_sees_anything_but_the_computed_context(monkeypatch):
    seen = {}

    def gen(system, prompt, schema, temperature=0.2):
        seen["prompt"], seen["system"] = prompt, system
        return GOOD, "fake-model"
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", gen)
    explain.explain(*mini(), "en", use_cache=False)
    assert "3.18e-18" in seen["prompt"] and "Azraq" in seen["prompt"]
    assert "ONLY numbers that appear" in seen["system"] and "never decide significance" in seen["system"].lower().replace("you never decide significance", "never decide significance")


def test_explain_endpoint_with_a_fake_llm(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(llm, "available", lambda: False)
    r = TestClient(app).post("/case/explain", json={"question": "Is Azraq drying up?"}).json()
    assert r["language"] == "en" and r["source"] == "template" and r["summary"] and r["witnesses"]
    ar = TestClient(app).post("/case/explain", json={"question": "هل إربد عم تسخن؟"}).json()
    assert ar["language"] == "ar" and "الحكم" in next(iter(ar["witnesses"].values()))
