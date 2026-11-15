"""/chat scope: comparing the case's witnesses ("Which witness is the strongest?") and "What should I check next?" are IN scope and
answered from computed numbers only; genuinely out-of-scope questions (other places, forecasts, general knowledge) are still refused."""
import pytest
from fastapi.testclient import TestClient

from app import chat, llm
from app.case_builder import build_case_and_expert
from app.explain import numbers_ok
from app.main import app
from test_chat import PLACE, VARS, fake, req

client = TestClient(app)


@pytest.fixture(scope="module")
def ce():
    case, ex = build_case_and_expert("", variables=VARS, lat=31.88, lon=36.83, place="Azraq")
    return case, ex["variables"]


def ask(ce_, message, **kw):
    case, ex = ce_
    return chat.answer(case, ex, message, kw.get("history"))


def labels(case, order):
    return [w["label"] for w in order(case)]


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)


# ---- "Which witness is the strongest?" (rule-based path: no LLM) ---------------------------------------------------------------
STRONGEST = ["Which witness is the strongest?", "Which clue is most convincing?", "How do the witnesses compare?", "Rank the evidence",
             "Which one has the strongest evidence?", "Compare the p-values", "Which variable is the weakest?", "Which witness shows the biggest change?",
             "What is the strongest trend?", "Is rain the strongest evidence?"]


@pytest.mark.parametrize("msg", STRONGEST)
def test_comparing_witnesses_is_in_scope_and_answered_from_computed_numbers(no_llm, ce, msg):
    case, ex = ce
    d = ask(ce, msg)
    assert d["in_scope"] is True and d["source"] == "template" and not d["answer"].startswith("I don't know"), d["answer"]
    top, bot, big = chat.evidence_order(case)[0], chat.evidence_order(case)[-1], chat.size_order(case)[0]
    for w in (top, bot, big):
        assert w["label"] in d["answer"]
    assert f"p = {top['stats']['p']:.2g}" in d["answer"] and f"p = {bot['stats']['p']:.2g}" in d["answer"]
    assert f"{big['stats']['pct_change']:+.0f}%" in d["answer"]
    assert d["cited"] == [w["variable"] for w in chat.evidence_order(case)]


def test_the_ranking_is_right_for_azraq(no_llm, ce):
    case, _ = ce
    ev = chat.evidence_order(case)
    assert ev[0]["variable"] == "T2M" and ev[-1]["variable"] == "NDVI"                          # smallest p / largest p
    assert chat.size_order(case)[0]["variable"] == "HOT_DAYS"                                   # biggest relative change
    assert [w["stats"]["p"] for w in ev] == sorted(w["stats"]["p"] for w in ev)
    assert [abs(w["stats"]["pct_change"]) for w in chat.size_order(case)] == sorted((abs(w["stats"]["pct_change"]) for w in case["witnesses"]), reverse=True)
    d = ask(ce, "Which witness is the strongest?")["answer"]
    assert d.startswith("Strongest evidence: Temperature (p = ") and "Weakest: Vegetation (NDVI)" in d and "NOT PROVEN" in d
    assert "Biggest change relative to its own first-decade average: Very hot days" in d
    assert "different things" in d                                                               # evidence strength != size of change


def test_the_ranking_answer_says_which_witnesses_are_borderline(no_llm, ce):
    d = ask(ce, "Rank the evidence")["answer"]
    assert "Rainfall (p = 0.013, borderline)" in d


def test_arabic_ranking_question_gets_an_arabic_answer_with_arabic_labels(no_llm, ce):
    d = ask(ce, "أي شاهد هو الأقوى؟")
    assert d["language"] == "ar" and d["in_scope"] is True and d["answer"].startswith("أقوى دليل: درجة الحرارة")
    assert "الأضعف: الغطاء النباتي" in d["answer"] and "غير مثبت" in d["answer"] and "أكبر تغيّر" in d["answer"]
    assert not [w for w in __import__("re").findall(r"[A-Za-z]{3,}", d["answer"]) if w.lower() not in ("ndvi", "tau")]


def test_a_single_witness_case_has_nothing_to_compare_but_still_answers(no_llm):
    case, ex = build_case_and_expert("", variables=["T2M"], lat=31.88, lon=36.83, place="Azraq")
    d = chat.answer(case, ex["variables"], "Which witness is the strongest?")
    assert d["in_scope"] is True and "Strongest evidence: Temperature" in d["answer"] and "Weakest" not in d["answer"]


# ---- "What should I check next?" ----------------------------------------------------------------------------------------------
NEXT = ["What should I check next?", "What should I look at next?", "Where should I dig deeper?", "What's the next step?",
        "What else should I investigate?", "What to check next?", "Where do I look next?"]


@pytest.mark.parametrize("msg", NEXT)
def test_what_to_check_next_is_in_scope_and_points_at_this_cases_weak_spots(no_llm, ce, msg):
    d = ask(ce, msg)
    a = d["answer"]
    assert d["in_scope"] is True and not a.startswith("I don't know"), a
    assert "Where map" in a and "Pick the witnesses yourself" in a                              # the two tools you named
    assert "Check Rainfall first: it only just passes the test (p = 0.013)" in a                # the borderline witness, with its p
    assert "Vegetation (NDVI) (p = 0.97) is not proven" in a                                    # the NOT PROVEN witness, with its p
    assert "Rainfall and Root-zone soil moisture moved together with a lag of 1 months (r = 0.58)" in a   # the chain link
    assert "correlation, not proof of cause" in a
    assert set(d["cited"]) == {"PRECTOTCORR", "NDVI", "GWETROOT"}


def test_next_steps_for_a_case_where_everything_is_confirmed(ce):
    case, ex = ce
    ws = [w for w in case["witnesses"] if w["variable"] in ("T2M", "HOT_DAYS")]
    exp = {w["variable"]: {**ex[w["variable"]], "borderline": False} for w in ws}
    loc = {**case, "witnesses": ws, "chain": []}
    text, cited = chat.next_steps_template(loc, exp, "en")
    assert text.startswith("Every witness is confirmed: use the Where map") and "Pick the witnesses yourself" in text
    assert set(cited) == {"T2M", "HOT_DAYS"}


def test_arabic_next_steps(no_llm, ce):
    d = ask(ce, "ماذا يجب أن أتحقق منه بعد ذلك؟")
    assert d["language"] == "ar" and d["in_scope"] is True, d["answer"]
    for must in ("خريطة «أين يتغيّر؟»", "«اختر الشهود بنفسك»", "الأمطار", "الغطاء النباتي", "غير مثبت"):
        assert must in d["answer"], must
    ar = ask(ce, "ماذا بعد؟")
    assert ar["in_scope"] is True and "خريطة" in ar["answer"]


def test_every_new_template_passes_the_same_number_and_verdict_and_ranking_guards(ce):
    case, ex = ce
    allowed = chat.allowed_for(chat.chat_context(case, ex))
    for lang in ("en", "ar"):
        loc = chat.localize(case, ex, lang)
        for text in (chat.ranking_template(loc, ex, lang), chat.next_steps_template(loc, ex, lang)[0]):
            assert numbers_ok(text, allowed)[0], text
            assert chat.verdicts_ok(text, case), text
            assert chat.ranking_ok(text, case), text


# ---- still refused (without an LLM) -------------------------------------------------------------------------------------------------
OUT_OF_SCOPE = ["Who is the strongest man in the world?", "Which country has the strongest economy?", "Which team is the strongest?",
                "What should I eat next?", "What should I check on my car?", "What is the biggest city in Jordan?",
                "Compare iPhone and Android", "Will it rain in Azraq tomorrow?", "What is the weather forecast for Amman?",
                "What about Irbid?",
                "من هو أقوى لاعب كرة قدم؟", "قارن بين الدولتين", "ماذا عن توقعات الطقس؟", "ما هي أكبر مدينة في العالم؟"]


@pytest.mark.parametrize("msg", OUT_OF_SCOPE)
def test_truly_out_of_scope_questions_are_still_refused(no_llm, ce, msg):
    d = ask(ce, msg)
    assert d["in_scope"] is False and ("I don't know" in d["answer"] or "لا أعرف" in d["answer"]) and d["cited"] == [], (msg, d["answer"])


def test_known_limitation_without_an_llm_a_question_using_the_cases_own_words_is_answered(no_llm, ce):
    """Documented limitation of the RULE-BASED fallback only: "Which witness did the police interview?" uses the phrase
    "which witness", which the rules cannot tell from the app's own "witnesses" (the app's word for variables). It gets the
    ranking answer. With an LLM configured the model decides scope (see the live check), so this only affects no-key mode."""
    assert ask(ce, "Which witness did the police interview?")["in_scope"] is True


# ---- the LLM path -----------------------------------------------------------------------------------------------------------------------
def test_the_models_instructions_and_context_make_these_questions_answerable(monkeypatch, ce):
    seen = fake(monkeypatch, True, "Temperature has the strongest evidence.")
    chat.answer(*ce, "Which witness is the strongest?")
    s, p = seen["system"], seen["prompt"]
    assert "IN SCOPE" in s and "COMPARING or RANKING" in s and "what to look at" in s.lower() and "OUT OF SCOPE" in s
    assert '"ranking_by_evidence"' in p and '"ranking_by_size"' in p and '"app_help"' in p and '"borderline_witnesses": ["Rainfall"]' in p
    assert '"not_proven_witnesses": ["Vegetation (NDVI)"]' in p and "Where map" in p and "Pick the witnesses yourself" in p
    first = p.split('"ranking_by_evidence": [')[1].split("}")[0]
    assert '"rank": 1' in first and '"variable": "T2M"' in first                                   # the context already ranks them


def test_a_correct_ranking_answer_from_the_model_is_used(monkeypatch, ce):
    txt = "Temperature has the strongest evidence (p = 3.18e-18), while very hot days show the biggest change (+42%)."
    fake(monkeypatch, True, txt)
    d = ask(ce, "Which witness is the strongest?")
    assert d["source"] == "gemini" and d["answer"] == txt and d["rejected"] == [] and set(d["cited"]) == {"T2M", "HOT_DAYS"}


@pytest.mark.parametrize("wrong", ["Rainfall has the strongest evidence.", "The strongest witness is vegetation.",
                                   "Very hot days is the weakest witness.", "Temperature shows the biggest change.",
                                   "Rainfall has the biggest relative change, with the strongest evidence being temperature."])
def test_a_wrong_superlative_claim_is_rejected_and_replaced_by_the_computed_ranking(monkeypatch, ce, wrong):
    fake(monkeypatch, True, wrong)
    d = ask(ce, "Which witness is the strongest?")
    assert d["source"] == "template" and d["rejected"] == ["contradicts the computed ranking"], (wrong, d["rejected"])
    assert d["answer"].startswith("Strongest evidence: Temperature") and d["in_scope"] is True


def test_correct_superlatives_in_several_phrasings_are_accepted(monkeypatch, ce):
    for ok in ("The strongest evidence is for temperature.", "Vegetation is the weakest witness; it is not proven.",
               "Very hot days show the biggest change.", "The evidence is strongest overall for the confirmed trends.",
               "Temperature is the most significant result."):
        fake(monkeypatch, True, ok)
        assert ask(ce, "Which is the strongest?")["source"] == "gemini", ok


def test_arabic_wrong_and_right_claims(monkeypatch, ce):
    fake(monkeypatch, True, "الأمطار هي أقوى دليل.")
    assert ask(ce, "أي شاهد هو الأقوى؟")["source"] == "template"
    fake(monkeypatch, True, "درجة الحرارة هي أقوى دليل، والأيام شديدة الحرارة هي أكبر تغيّر.")
    assert ask(ce, "أي شاهد هو الأقوى؟")["source"] == "gemini"


def test_ranking_guard_unit(ce):
    case, _ = ce
    assert chat.ranking_ok("Temperature is the strongest.", case) and not chat.ranking_ok("Vegetation is the strongest.", case)
    assert chat.ranking_ok("Vegetation is the weakest.", case) and not chat.ranking_ok("Temperature is the weakest.", case)
    assert chat.ranking_ok("Nothing here is ranked.", case) and chat.ranking_ok("The strongest thing is the method.", case)
    one = {**case, "witnesses": case["witnesses"][:1]}
    assert chat.ranking_ok("Rainfall is the weakest.", one)                                         # one witness: nothing to rank


def test_a_next_steps_answer_from_the_model_is_accepted_when_it_uses_computed_numbers(monkeypatch, ce):
    txt = ("Check rainfall first: it only just passes (p = 0.013). Vegetation is not proven (p = 0.97), so try another period in "
           "Pick the witnesses yourself, and use the Where map to see whether neighbouring places agree.")
    fake(monkeypatch, True, txt)
    d = ask(ce, "What should I check next?")
    assert d["source"] == "gemini" and d["answer"] == txt and {"PRECTOTCORR", "NDVI"} <= set(d["cited"])


def test_a_next_steps_answer_with_an_invented_number_is_replaced(monkeypatch, ce):
    fake(monkeypatch, True, "Check rainfall (p = 0.0004) on the Where map.")
    d = ask(ce, "What should I check next?")
    assert d["source"] == "template" and "0.0004" not in d["answer"] and "Check Rainfall first" in d["answer"]


def test_a_model_that_still_refuses_an_out_of_scope_question_is_respected(monkeypatch, ce):
    fake(monkeypatch, False, "Paris")
    d = ask(ce, "What is the capital of France?")
    assert d["in_scope"] is False and d["answer"].startswith("I don't know that.") and "Paris" not in d["answer"]


# ---- through the endpoint, with the frontend's request shape -------------------------------------------------------------------------------
def test_endpoint_answers_both_new_question_types(monkeypatch):
    fake(monkeypatch, True, "Temperature has the strongest evidence (p = 3.18e-18).")
    r = client.post("/chat", json=req("Which witness is the strongest?"))
    assert r.status_code == 200 and r.json()["source"] == "llm" and r.json()["cited"] == ["T2M"]
    monkeypatch.setattr(llm, "available", lambda: False)
    r = client.post("/chat", json=req("What should I check next?"))
    d = r.json()
    assert r.status_code == 200 and d["source"] == "template" and "Where map" in d["reply"] and "PRECTOTCORR" in d["cited"]
    r = client.post("/chat", json=req("Who is the strongest man in the world?"))
    assert r.json()["reply"].startswith("I don't know that.") and r.json()["cited"] == []


# ---- regressions found while writing the tests above -----------------------------------------------------------------------------------
def test_an_order_phrase_is_not_a_superlative_claim(ce):
    case, _ = ce
    assert chat.ranking_ok("Ordered from strongest to weakest: temperature, very hot days, soil moisture, rainfall, vegetation.", case)
    assert chat.ranking_ok("Evidence, weakest to strongest: vegetation, rainfall, soil moisture, very hot days, temperature.", case)
    assert chat.ranking_ok("مرتبة من الأقوى إلى الأضعف: درجة الحرارة، الأيام شديدة الحرارة، الغطاء النباتي.", case)
    assert not chat.ranking_ok("Rainfall is the strongest, ordered from strongest to weakest.", case)           # a real claim is still checked


@pytest.mark.parametrize("msg", ["Will it rain in Azraq tomorrow?", "Will it keep getting hotter?", "Is it going to be drier by 2050?",
                                 "What is the rain forecast?", "Is there less rain next year?", "هل ستمطر غداً؟", "كيف سيكون الطقس؟"])
def test_forecast_questions_are_refused_even_when_they_name_a_variable(no_llm, ce, msg):
    d = ask(ce, msg)
    assert d["in_scope"] is False and ("I don't know" in d["answer"] or "لا أعرف" in d["answer"]) and d["cited"] == [], (msg, d["answer"])


@pytest.mark.parametrize("msg", ["Is it getting hotter in Irbid?", "How much less rain in Amman?", "Is Aqaba drying up?", "هل إربد عم تسخن؟"])
def test_questions_about_another_place_are_refused(no_llm, ce, msg):
    d = ask(ce, msg)
    assert d["in_scope"] is False and d["cited"] == [], (msg, d["answer"])


@pytest.mark.parametrize("msg", ["Is it getting hotter in Azraq?", "How much less rain is there in Azraq?", "هل الأزرق أصبح أسخن؟"])
def test_questions_naming_the_cases_own_place_are_answered(no_llm, ce, msg):
    d = ask(ce, msg)
    assert d["in_scope"] is True and d["cited"], (msg, d["answer"])


def test_a_live_place_case_is_not_confused_with_the_gazetteer(no_llm):
    case, ex = build_case_and_expert("", variables=["T2M"], lat=31.88, lon=36.83, place="Azraq, Jordan")        # name with a country
    assert chat.answer(case, ex["variables"], "Is it getting hotter in Azraq?")["in_scope"] is True
    assert chat.answer(case, ex["variables"], "Is it getting hotter in Irbid?")["in_scope"] is False
