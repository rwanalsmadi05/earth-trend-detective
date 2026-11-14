"""Planner tests. The LLM is always a fake: no network, no key."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import gazetteer, llm, planner
from app.main import app
from app.planner import LLMPlan, LLMVar, PlaceNotFound
from app.variables import VARIABLES

client = TestClient(app)


def fake_llm(monkeypatch, plan=None, exc=None):
    """Pretend a key is configured and make generate_json return `plan` (or raise `exc`)."""
    calls = []

    def gen(system, prompt, schema, temperature=0.2):
        calls.append(prompt)
        if exc:
            raise exc
        return plan, "fake-model"

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", gen)
    return calls


def lp(**kw):
    base = dict(cleaned_question="Is Azraq drying up?", place_query="Azraq", language="en",
                variables=[LLMVar(variable="PRECTOTCORR", reason="Rain refills the oasis."),
                           LLMVar(variable="GWETROOT", reason="Soil moisture shows if roots still get water."),
                           LLMVar(variable="T2M", reason="Heat pulls water out of the ground.")])
    base.update(kw)
    return LLMPlan(**base)


@pytest.fixture(autouse=True)
def _no_nominatim(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network disabled in tests")
    monkeypatch.setattr(gazetteer, "get", boom)


# ---- the schema itself is the first line of defence -----------------------------------------------------------
def test_schema_rejects_variables_outside_the_catalog():
    with pytest.raises(ValidationError):
        LLMVar(variable="WATER_TABLE", reason="x")
    assert set(LLMVar.model_fields["variable"].annotation.__args__) == set(VARIABLES)   # enum == catalog, nothing more


# ---- Gemini path (mocked) -------------------------------------------------------------------------------------
def test_valid_llm_plan_is_used_and_place_comes_from_the_gazetteer(monkeypatch):
    fake_llm(monkeypatch, lp(cleaned_question="Is Azraq drying up?"))
    p = planner.plan_question("is azraq drying up", use_cache=False)
    assert p.planner == "gemini" and p.model == "fake-model" and p.fallback_reason is None
    assert (p.place["lat"], p.place["lon"], p.place["source"]) == (31.88, 36.83, "gazetteer")   # never from the LLM
    # a drying question always considers T2M and HOT_DAYS (evaporation): the LLM's 3 + HOT_DAYS added, LLM order kept
    assert [v["variable"] for v in p.variables] == ["PRECTOTCORR", "GWETROOT", "T2M", "HOT_DAYS"]
    assert p.variables[0]["reason"] == "Rain refills the oasis." and p.variables[0]["label"] == "Rainfall"
    assert p.variables[3]["reason"] == VARIABLES["HOT_DAYS"]["reason"]      # added variable gets a template reason
    assert p.cleaned_question == "Is Azraq drying up?" and p.language == "en"


def test_llm_has_no_way_to_supply_coordinates():
    assert "lat" not in LLMPlan.model_fields and "lon" not in LLMPlan.model_fields


def test_place_query_nonsense_falls_back_to_a_known_name_in_the_question(monkeypatch):
    fake_llm(monkeypatch, lp(place_query="the oasis thing"))
    assert planner.plan_question("Is Azraq drying up?", use_cache=False).place["name"] == "Azraq"


def test_unknown_place_raises_place_not_found(monkeypatch):
    fake_llm(monkeypatch, lp(place_query="Atlantis"))
    with pytest.raises(PlaceNotFound):
        planner.plan_question("Is Atlantis sinking?", use_cache=False)


def test_reasons_with_numbers_are_replaced_by_the_template(monkeypatch):
    fake_llm(monkeypatch, lp(variables=[LLMVar(variable="T2M", reason="It warmed by 3.5 degrees!"),
                                        LLMVar(variable="PRECTOTCORR", reason="Rain is the first suspect.")]))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert p.variables[0]["reason"] == VARIABLES["T2M"]["reason"]          # LLM reason rejected (digits)
    assert p.variables[1]["reason"] == "Rain is the first suspect."


def test_arabic_digit_reasons_are_also_rejected(monkeypatch):
    fake_llm(monkeypatch, lp(variables=[LLMVar(variable="T2M", reason="ارتفعت ٣ درجات")]))
    assert planner.plan_question("Is Azraq hot?", use_cache=False).variables[0]["reason"] == VARIABLES["T2M"]["reason"]


def test_duplicates_removed_and_capped_at_five(monkeypatch):
    many = [LLMVar(variable=v, reason="Because.") for v in
            ["T2M", "T2M", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "NDVI", "HOT_DAYS"]]
    fake_llm(monkeypatch, lp(variables=many))
    vs = [v["variable"] for v in planner.plan_question("Is Azraq drying up?", use_cache=False).variables]
    # deduped, capped at 5, and the required T2M + HOT_DAYS survive the trim (drying question)
    assert len(vs) == 5 and len(set(vs)) == 5 and "T2M" in vs and "HOT_DAYS" in vs
    assert vs == ["T2M", "PRECTOTCORR", "GWETROOT", "GWETTOP", "HOT_DAYS"]


def test_period_only_when_valid(monkeypatch):
    fake_llm(monkeypatch, lp(start_year=1995, end_year=2020))
    assert planner.plan_question("Azraq since 1995?", use_cache=False).period == {"start": 1995, "end": 2020}
    fake_llm(monkeypatch, lp(start_year=2020, end_year=1995))
    assert planner.plan_question("Azraq?", use_cache=False).period["start"] == 1981          # reversed -> default
    fake_llm(monkeypatch, lp(start_year=1500, end_year=2999))
    assert planner.plan_question("Azraq?", use_cache=False).period["start"] == 1981          # out of range -> default


def test_cleaned_question_must_be_a_real_cleanup(monkeypatch):
    fake_llm(monkeypatch, lp(cleaned_question="Is Azraq losing 40 percent of its water?"))   # new number, new meaning
    assert planner.plan_question("is azraq drying up", use_cache=False).cleaned_question == "Is azraq drying up?"
    fake_llm(monkeypatch, lp(cleaned_question="هل الأزرق يجف؟"))                              # wrong language
    assert planner.plan_question("is azraq drying up", use_cache=False).cleaned_question == "Is azraq drying up?"


def test_clean_ok_and_rules_clean_units():
    assert planner.clean_ok("is azraq dryng up", "Is Azraq drying up?")
    assert not planner.clean_ok("is azraq drying up", "Tell me everything about Jordan's water policy")
    assert not planner.clean_ok("is azraq drying up", "Is Azraq drying up in 2050?")
    assert planner.rules_clean("  is   azraq drying up ") == "Is azraq drying up?"
    assert planner.rules_clean("Is Azraq drying up?") == "Is Azraq drying up?"
    assert planner.rules_clean("هل إربد عم تسخن") == "هل إربد عم تسخن؟"
    assert planner.rules_clean("هل إربد عم تسخن?") == "هل إربد عم تسخن؟"


# ---- fallbacks -------------------------------------------------------------------------------------------------
def test_llm_failure_falls_back_to_rules_and_says_why(monkeypatch):
    fake_llm(monkeypatch, exc=TimeoutError("read timed out"))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert p.planner == "rules" and p.model is None and "TimeoutError" in p.fallback_reason
    assert p.place["name"] == "Azraq" and len(p.variables) >= 3


def test_invalid_llm_output_falls_back_to_rules(monkeypatch):
    fake_llm(monkeypatch, exc=ValueError("schema validation failed"))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert p.planner == "rules" and "ValueError" in p.fallback_reason


def test_llm_with_no_usable_variables_falls_back(monkeypatch):
    fake_llm(monkeypatch, lp(variables=[]))
    assert planner.plan_question("Is Azraq drying up?", use_cache=False).planner == "rules"


def test_no_key_means_rules_planner_and_the_llm_is_never_called(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert p.planner == "rules" and p.fallback_reason == "no LLM configured"


def test_the_api_key_never_appears_in_the_plan(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "SECRET-KEY-123")
    fake_llm(monkeypatch, exc=RuntimeError("401 bad key SECRET-KEY-123 rejected"))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert "SECRET-KEY-123" not in json.dumps(p.__dict__, default=str) and "<redacted>" in p.fallback_reason
    assert "SECRET-KEY-123" not in llm.redact("x SECRET-KEY-123 y")


# ---- rule-based planner ----------------------------------------------------------------------------------------
def test_rules_planner_english_drying():
    p = planner.rules_plan("Is Azraq drying up?")
    assert p.place["name"] == "Azraq" and p.language == "en" and p.planner == "rules"
    assert [v["variable"] for v in p.variables][:4] == ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS"]


def test_rules_planner_arabic_heat_question():
    p = planner.rules_plan("هل إربد عم تسخن؟")
    assert p.place["name"] == "Irbid" and p.language == "ar" and p.cleaned_question == "هل إربد عم تسخن؟"
    vs = [v["variable"] for v in p.variables]
    assert "T2M" in vs and "HOT_DAYS" in vs and "PRECTOTCORR" not in vs[:1]
    assert all(any("؀" <= c <= "ۿ" for c in v["reason"]) for v in p.variables)     # Arabic reasons
    assert all(any("؀" <= c <= "ۿ" for c in v["label"]) for v in p.variables)


@pytest.mark.parametrize("q", ["Is Azraq drying up?", "هل إربد عم تسخن؟", "Is Amman getting more rain?", "is the Dead Sea greener",
                               "how humid is Aqaba", "sunshine in Petra", "random words about Jerash"])
def test_every_plan_stays_inside_the_catalog(q):
    p = planner.rules_plan(q)
    assert p.variables and all(v["variable"] in VARIABLES for v in p.variables)
    assert len({v["variable"] for v in p.variables}) == len(p.variables)


# ---- cache -----------------------------------------------------------------------------------------------------
def test_plan_cache_skips_the_llm_second_time(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, "CACHE_ON", True)
    monkeypatch.setattr(planner, "PLAN_CACHE", tmp_path)
    calls = fake_llm(monkeypatch, lp())
    a = planner.plan_question("Is Azraq drying up?")
    b = planner.plan_question("Is Azraq drying up?")
    assert len(calls) == 1 and a == b and b.planner == "gemini"


def test_rules_fallback_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, "CACHE_ON", True)
    monkeypatch.setattr(planner, "PLAN_CACHE", tmp_path)
    fake_llm(monkeypatch, exc=TimeoutError("x"))
    planner.plan_question("Is Azraq drying up?")
    assert list(tmp_path.glob("*.json")) == []          # so a later call can upgrade to Gemini


# ---- end to end through the API --------------------------------------------------------------------------------
def test_plan_endpoint_returns_the_plan(monkeypatch):
    fake_llm(monkeypatch, lp())
    r = client.post("/plan", json={"question": "is azraq drying up"}).json()
    assert r["planner"] == "gemini" and r["cleaned_question"] == "Is Azraq drying up?"
    assert r["place"]["lat"] == 31.88 and [v["variable"] for v in r["variables"]] == ["PRECTOTCORR", "GWETROOT", "T2M", "HOT_DAYS"]


def test_case_uses_the_plans_variables_reasons_and_cleaned_question(monkeypatch):
    fake_llm(monkeypatch, lp(cleaned_question="Is Azraq drying up?"))
    c = client.post("/case", json={"question": "is azraq drying up"}).json()
    assert c["question"] == "is azraq drying up" and c["cleaned_question"] == "Is Azraq drying up?"
    assert [w["variable"] for w in c["witnesses"]] == ["PRECTOTCORR", "GWETROOT", "T2M", "HOT_DAYS"]
    assert c["witnesses"][0]["reason"] == "Rain refills the oasis."


def test_case_still_works_when_the_llm_fails(monkeypatch):
    fake_llm(monkeypatch, exc=ConnectionError("down"))
    r = client.post("/case", json={"question": "Is Azraq drying up?"})
    assert r.status_code == 200 and len(r.json()["witnesses"]) >= 4


def test_arabic_question_gives_an_arabic_case():
    c = client.post("/case", json={"question": "هل إربد عم تسخن؟"}).json()
    assert c["place"]["name"] == "Irbid" and c["place"]["name_ar"] == "إربد"
    assert c["cleaned_question"] == "هل إربد عم تسخن؟"
    w = c["witnesses"][0]
    assert any("؀" <= ch <= "ۿ" for ch in w["label"] + w["reason"] + w["headline"])
    assert any("؀" <= ch <= "ۿ" for ch in c["verdict"]["headline"])
    assert c["witnesses"][0]["verdict"] in ("CONFIRMED", "NOT PROVEN")        # stamps stay the math's English enum


def test_unknown_place_is_a_422():
    assert client.post("/case", json={"question": "Is Atlantis sinking?"}).status_code == 422


# ---- planning rules: broad -> 4-5 witnesses, drying -> T2M + HOT_DAYS, demo -> fixed set -----------------------------
def three(*ids):
    return lp(variables=[LLMVar(variable=v, reason="Because it helps.") for v in ids])


def test_broad_question_with_too_few_variables_is_topped_up_to_at_least_four(monkeypatch):
    fake_llm(monkeypatch, three("T2M", "PRECTOTCORR"))
    vs = [v["variable"] for v in planner.plan_question("Is Azraq changing?", use_cache=False).variables]
    assert 4 <= len(vs) <= 5 and vs[:2] == ["T2M", "PRECTOTCORR"] and len(set(vs)) == len(vs)
    assert all(v in VARIABLES for v in vs)


def test_every_added_variable_has_a_reason(monkeypatch):
    fake_llm(monkeypatch, three("PRECTOTCORR"))
    p = planner.plan_question("Is Azraq drying up?", use_cache=False)
    assert len(p.variables) >= 4 and all(v["reason"].strip() and v["label"] for v in p.variables)


def test_drying_questions_always_include_temperature_and_very_hot_days(monkeypatch):
    for q in ["Is Azraq drying up?", "Is the Dead Sea shrinking? water is disappearing", "هل الأزرق جاف؟", "Is Amman in drought?"]:
        for llm_vars in [("PRECTOTCORR", "GWETROOT", "NDVI"), ("GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN", "NDVI", "PRECTOTCORR"), ("NDVI",)]:
            fake_llm(monkeypatch, three(*llm_vars))
            vs = [v["variable"] for v in planner.plan_question(q, use_cache=False).variables]
            assert "T2M" in vs and "HOT_DAYS" in vs and 4 <= len(vs) <= 5, (q, llm_vars, vs)


def test_arabic_drying_question_gets_arabic_reasons_for_the_added_variables(monkeypatch):
    fake_llm(monkeypatch, three("PRECTOTCORR"))
    p = planner.plan_question("هل الأزرق جاف؟", use_cache=False)
    added = {v["variable"]: v for v in p.variables}
    assert "T2M" in added and "HOT_DAYS" in added
    assert all(any("؀" <= c <= "ۿ" for c in added[k]["reason"]) for k in ("T2M", "HOT_DAYS"))


def test_narrow_single_topic_question_may_stay_at_three(monkeypatch):
    fake_llm(monkeypatch, three("RH2M", "T2M", "PRECTOTCORR"))
    vs = [v["variable"] for v in planner.plan_question("How humid is Aqaba?", use_cache=False).variables]
    assert vs == ["RH2M", "T2M", "PRECTOTCORR"]            # narrow: not padded, not forced


def test_rules_planner_follows_the_same_rules():
    for q in ["Is Azraq drying up?", "هل الأزرق جاف؟", "Is Azraq changing?"]:
        vs = [v["variable"] for v in planner.rules_plan(q).variables]
        assert 4 <= len(vs) <= 5
        if planner.topic_info(q)[0]:
            assert "T2M" in vs and "HOT_DAYS" in vs


def test_shape_variables_unit():
    assert planner.shape_variables("Is Azraq drying up?", ["NDVI"])[:1] == ["T2M"]
    assert planner.shape_variables("Is Azraq drying up?", ["T2M", "HOT_DAYS", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "NDVI"]) ==         ["T2M", "HOT_DAYS", "PRECTOTCORR", "GWETROOT", "GWETTOP"]          # trimmed from the end, required kept
    assert planner.shape_variables("How humid is Aqaba?", ["RH2M"]) == ["RH2M"]


@pytest.mark.parametrize("q", ["run the demo case: Azraq", "Run the demo case: Azraq", "demo azraq", "شغّل الحالة التجريبية: الأزرق"])
def test_demo_case_is_fixed_and_never_touches_the_llm(monkeypatch, q):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("demo must not call the LLM")))
    p = planner.plan_question(q, use_cache=True)
    assert p.planner == "demo" and p.model is None and p.fallback_reason is None
    assert [v["variable"] for v in p.variables] == ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS", "NDVI"]
    assert p.place["name"] == "Azraq" and all(v["reason"].strip() for v in p.variables)
    assert p == planner.plan_question(q)                              # deterministic


def test_demo_without_a_place_defaults_to_azraq(monkeypatch):
    assert planner.plan_question("run the demo case", use_cache=False).place["name"] == "Azraq"


def test_demo_case_end_to_end_gives_all_five_witnesses_even_if_the_llm_is_down(monkeypatch):
    fake_llm(monkeypatch, exc=ConnectionError("LLM down"))
    c = client.post("/case", json={"question": "run the demo case: Azraq"}).json()
    assert [w["variable"] for w in c["witnesses"]] == ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS", "NDVI"]
    assert c["cleaned_question"] == "Run the demo case: Azraq" and c["place"]["name"] == "Azraq"
    assert client.post("/plan", json={"question": "run the demo case: Azraq"}).json()["planner"] == "demo"
