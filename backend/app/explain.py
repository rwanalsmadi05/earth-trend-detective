"""AI partner, part 2: explain computed results + give hints.  (CLAUDE.md section 5, rules 2 and 3)

The LLM only *words* results. Two guards run on everything it writes, in code:
  numbers_ok()    every number in the text must be one of the numbers we computed (rounded the way the text rounds it)
  verdict_ok()    the text must not contradict the math-decided verdict (e.g. call a NOT PROVEN witness "confirmed")
Text that fails either guard is thrown away and replaced by a template built from the same numbers, so the
user never sees an invented number or verdict. Hints must contain no numbers and no verdict words at all."""
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel

from . import i18n, llm
from .config import CACHE_DIR

CACHE_ON = True
EXPLAIN_CACHE = CACHE_DIR / "explain"
METHOD_CONSTANTS = {0.05, 0.01, 35.0}      # significance level, borderline level, the hot-day threshold: methodology, not data

VarId = Literal["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN", "NDVI", "HOT_DAYS"]


class LLMWitnessText(BaseModel):
    variable: VarId
    text: str


class LLMHint(BaseModel):
    after: VarId
    text: str


class LLMExplain(BaseModel):
    summary: str
    witnesses: list[LLMWitnessText]
    hints: list[LLMHint] = []


# ---- guards --------------------------------------------------------------------------------------------------
_NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")


def _collect(obj, out: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out)


def allowed_numbers(context: dict) -> set:
    s = set(METHOD_CONSTANTS)
    _collect(context, s)
    return s


def numbers_ok(text: str, allowed: set) -> tuple[bool, list]:
    """Every number in `text` must equal an allowed computed value after the same rounding (decimals or significant
    digits). Returns (ok, offending numbers)."""
    bad = []
    for tok in _NUM.findall(i18n.ascii_digits(text)):
        t = tok.replace(",", ".")
        x = abs(float(t))
        mant = re.split(r"[eE]", t)[0]
        dec = len(mant.split(".")[1]) if "." in mant else 0
        sigd = len(mant.replace(".", "").lstrip("0")) or 1
        if not any(abs(round(a, dec) - x) < 1e-12 or (a != 0 and abs(float(f"{a:.{sigd}g}") - x) <= 1e-12 * max(1.0, x))
                   for a in allowed):
            bad.append(tok)
    return (not bad), bad


_NEG_EN = r"(?:not|no|isn't|aren't|n't|cannot|can't|without)\s+(?:\w+\s+){0,2}"
_POS_EN = re.compile(r"confirm|significan|proven|proves|proof|real trend", re.I)
_NEG_STRIP_EN = re.compile(_NEG_EN + r"(?:confirm\w*|significan\w*|proven|prov\w*|clear)", re.I)
_OPP_EN = re.compile(r"not proven|no clear|could be chance|no significant|not significant|isn't significant|unproven", re.I)
_POS_AR = re.compile(r"مؤكد|مثبت|دال|دلالة|مؤكَّد|حقيقي")
_NEG_STRIP_AR = re.compile(r"(?:غير|ليس|لا)\s+(?:\w+\s+){0,2}(?:مؤكد\w*|مثبت\w*|دال\w*|دلالة|حقيقي)")
_OPP_AR = re.compile(r"غير مثبت|لا يوجد تغي|صدفة|غير دال|ليس.{0,15}دلالة")


def verdict_ok(text: str, verdict: str) -> bool:
    """Reject text that claims the opposite of the computed verdict."""
    if verdict == "NOT PROVEN":   # must not claim significance / confirmation (negated phrasing is fine)
        t = _NEG_STRIP_AR.sub(" ", _NEG_STRIP_EN.sub(" ", text))
        return not (_POS_EN.search(t) or _POS_AR.search(t))
    return not (_OPP_EN.search(text) or _OPP_AR.search(text))   # CONFIRMED must not say "not proven"/"chance"


def hint_ok(text: str, allowed: set) -> bool:
    """Hints may not reveal verdicts and carry no numbers."""
    t = text.strip()
    return bool(t) and len(t) <= 220 and not _NUM.search(i18n.ascii_digits(t)) and not (
        _POS_EN.search(t) or _POS_AR.search(t) or _OPP_EN.search(t) or _OPP_AR.search(t) or re.search(r"not proven", t, re.I))


# ---- context + templates ---------------------------------------------------------------------------------------
def build_context(case: dict, expert: dict) -> dict:
    ws = []
    for w in case["witnesses"]:
        st, ex = w["stats"], expert[w["variable"]]
        ws.append({"variable": w["variable"], "label": w["label"], "unit": w["unit"], "verdict": w["verdict"],
                   "borderline": ex["borderline"], "direction": w["direction"], "headline": w["headline"],
                   "since_year": w["start_year"], "total_change": st["total_change"], "pct_change": st["pct_change"],
                   "sen_per_decade": st["sen_per_decade"], "p": st["p"], "tau": st["tau"], "n_months": st["n"]})
    return {"place": case["place"]["name"], "period_start": case["period"]["start"], "period_end": case["period"]["end"],
            "witnesses_confirmed": case["verdict"]["confirmed"], "witnesses_total": case["verdict"]["total"],
            "case_headline": case["verdict"]["headline"], "witnesses": ws,
            "chain": [{"leader": c["from"], "follower": c["to"], "lag_months": c["lag_months"], "r": c["r"]} for c in case["chain"]]}


def template_explanation(case: dict, expert: dict, lang: str) -> dict:
    ar = lang == "ar"
    texts = {}
    for w in case["witnesses"]:
        ex, p = expert[w["variable"]], w["stats"]["p"]
        if ar:
            v = i18n.VERDICT_AR[w["verdict"]]
            texts[w["variable"]] = f"{w['label']}: {w['headline']}. الحكم: {v} (p = {p:.2g}{'؛ حدّيّ' if ex['borderline'] else ''})."
        else:
            texts[w["variable"]] = (f"{w['label']}: {w['headline']}. Verdict: {w['verdict']} "
                                    f"(p = {p:.2g}{'; borderline' if ex['borderline'] else ''}).")
    labels = {w["variable"]: w["label"] for w in case["witnesses"]}
    chain = ""
    if case["chain"]:
        c = case["chain"][0]
        chain = (f" {labels[c['from']]} و{labels[c['to']]} يتحركان معاً بفارق {c['lag_months']} شهر (r = {c['r']:.2f})؛ هذا ارتباط وليس دليلاً على السبب."
                 if ar else
                 f" {labels[c['from']]} and {labels[c['to']]} moved together with a lag of {c['lag_months']} months "
                 f"(r = {c['r']:.2f}); that is correlation, not proof of cause.")
    return {"summary": case["verdict"]["headline"] + "." + chain, "witnesses": texts, "hints": []}


_SYSTEM = """You are the AI partner of an Earth-science detective app. You explain RESULTS THAT WERE ALREADY COMPUTED.
Rules, all mandatory:
1. Use ONLY numbers that appear in the JSON context. Never invent, estimate, convert or round-to-a-new-value any number.
   If something is not in the context, say you do not know. Do not mention years or decades that are not in the context.
2. You never decide significance. The `verdict` field is final: CONFIRMED means the trend test passed, NOT PROVEN means it
   did not (the change may be chance). Never say the opposite. If `borderline` is true, say the evidence is only just strong enough.
3. Chain links are correlations, not causes: say so.
4. Write in the user's language ({lang}), plain words for a curious teenager. summary: 2-3 sentences. One text per witness: 1-2 sentences.
5. hints (max 2): short detective nudges tied to a witness (`after`), phrased as questions or observations, with NO numbers and
   NO verdict words (never say confirmed, significant, proven, or not proven)."""


def _cache_path(ctx: dict, lang: str):
    return EXPLAIN_CACHE / (hashlib.sha256((lang + json.dumps(ctx, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()[:24] + ".json")


def explain(case: dict, expert: dict, lang: str, use_cache: bool = True) -> dict:
    """{language, source, model, fallback_reason, summary, witnesses{var: text}, hints[], rejected[]}"""
    ctx = build_context(case, expert)
    tpl = template_explanation(case, expert, lang)
    base = {"language": lang, "source": "template", "model": None, "fallback_reason": None, "rejected": [], **tpl}
    p = _cache_path(ctx, lang)
    if use_cache and CACHE_ON and p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            pass
    if not llm.available():
        base["fallback_reason"] = "no LLM configured"
        return base
    try:
        out, model = llm.generate_json(_SYSTEM.format(lang="Arabic" if lang == "ar" else "English"),
                                       "Computed results (JSON):\n" + json.dumps(ctx, ensure_ascii=False), LLMExplain)
    except Exception as e:  # noqa: BLE001
        base["fallback_reason"] = llm.redact(f"{type(e).__name__}: {str(e)[:140]}")
        return base

    allowed, verdicts = allowed_numbers(ctx), {w["variable"]: w["verdict"] for w in case["witnesses"]}
    rejected, result = [], dict(base, source="gemini", model=model)

    def vet(label, text, verdict=None):
        ok, bad = numbers_ok(text, allowed)
        if not ok:
            rejected.append(f"{label}: number(s) not in computed data: {', '.join(bad)}")
        elif verdict and not verdict_ok(text, verdict):
            rejected.append(f"{label}: contradicts the computed verdict ({verdict})")
        else:
            return True
        return False

    summary = out.summary.strip()
    if vet("summary", summary):
        result["summary"] = summary
    got = {w.variable: w.text.strip() for w in out.witnesses if w.variable in verdicts}
    for vid, text in got.items():
        if vet(vid, text, verdicts[vid]):
            result["witnesses"][vid] = text
    hints = []
    for h in out.hints[:2]:
        if h.after in verdicts and hint_ok(h.text, allowed):
            hints.append({"after": h.after, "text": h.text.strip()})
        else:
            rejected.append(f"hint after {h.after}: dropped (number/verdict word or unknown witness)")
    result["hints"], result["rejected"] = hints, rejected
    if len(rejected) >= 1 + len(verdicts):   # everything was rejected: be honest about it
        result["source"] = "template"
    if CACHE_ON:
        EXPLAIN_CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, ensure_ascii=False), "utf-8")
    return result
