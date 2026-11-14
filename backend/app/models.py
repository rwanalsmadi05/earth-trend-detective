"""Pydantic mirror of frontend/src/api/types.ts (POST /case). Keep field names and literals identical."""
from typing import Literal
from pydantic import BaseModel

VariableId = Literal["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M",
                     "ALLSKY_SFC_SW_DWN", "NDVI", "HOT_DAYS"]
Verdict = Literal["CONFIRMED", "NOT PROVEN"]


class SatImage(BaseModel):
    date: str
    url: str
    bbox: list[float]           # [west, south, east, north]; every image is centred on the case place


class Images(BaseModel):
    before: SatImage
    after: SatImage


class Stats(BaseModel):
    n: int
    tau: float
    p: float
    sen_per_decade: float
    total_change: float
    pct_change: float


class SeriesPoint(BaseModel):
    year: int
    value: float


class Witness(BaseModel):
    variable: VariableId
    label: str
    unit: str
    reason: str
    source: str
    source_url: str
    start_year: int
    images: Images
    stats: Stats
    verdict: Verdict
    headline: str
    direction: Literal["up", "down"]
    series: list[SeriesPoint]


class Place(BaseModel):
    name: str
    name_ar: str
    lat: float
    lon: float


class Period(BaseModel):
    start: int
    end: int


class Hint(BaseModel):
    after: VariableId
    text: str


class CaseVerdict(BaseModel):
    confirmed: int
    total: int
    headline: str


class DataLabel(BaseModel):
    origin: Literal["live", "cache", "mock"]
    fetched: str


class CaseResponse(BaseModel):
    case_id: str
    question: str
    cleaned_question: str       # the planner's tidied, correctly spelled question
    place: Place
    period: Period
    witnesses: list[Witness]
    chain: list[dict]  # serialised with key "from" (reserved word in Python); see case_builder
    hints: list[Hint]
    verdict: CaseVerdict
    data_label: DataLabel


class CaseRequest(BaseModel):
    question: str = ""
    variables: list[VariableId] | None = None   # manual "pick the witnesses yourself" selection (no LLM)
    lat: float | None = None
    lon: float | None = None
    place: str | None = None
    start: int | None = None
    end: int | None = None


class ExpertItem(BaseModel):
    method: str                 # which Mann-Kendall variant produced tau / p
    reason: str | None          # why the test could not be computed (verdict is then NOT PROVEN)
    n_months: int | None        # valid monthly observations (None for annual counts)
    n_tested: int               # values the test ran on (monthly anomalies; annual counts for hot days)
    borderline: bool            # CONFIRMED but only just: 0.01 <= p < 0.05
    test_on: str
    baseline: float
    tau: float
    p: float
    sen_per_decade: float


class ExpertResponse(BaseModel):
    case_id: str
    variables: dict[str, ExpertItem]


class PlanVariable(BaseModel):
    variable: VariableId
    label: str
    reason: str


class PlanResponse(BaseModel):
    question: str
    cleaned_question: str
    language: Literal["en", "ar"]
    place: dict
    period: Period
    variables: list[PlanVariable]
    planner: Literal["gemini", "rules", "demo"]
    model: str | None
    fallback_reason: str | None


class ExplainResponse(BaseModel):
    language: Literal["en", "ar"]
    source: Literal["gemini", "template"]
    model: str | None
    fallback_reason: str | None
    summary: str
    witnesses: dict[str, str]
    hints: list[Hint]
    rejected: list[str]


# ---- step 6: GET /grid, GET /twist, GET /lifetime (mirror frontend/src/api/types.ts) -------------------------------
class DataLabel2(BaseModel):
    origin: Literal["live", "cache", "mock"]
    fetched: str


class GridCell(BaseModel):
    lat: float
    lon: float
    value: float
    q: float
    significant: bool
    verdict: Verdict
    series: list[float]


class GridWords(BaseModel):
    up: str
    down: str


class GridResponse(BaseModel):
    variable: VariableId
    label: str
    display_unit: str
    words: GridWords
    bbox: tuple[float, float, float, float]      # west, south, east, north
    step: float
    years: list[int]
    cells: list[GridCell]
    fdr: Literal["benjamini-hochberg"]
    data_label: DataLabel2


class TwistSide(BaseModel):
    name: str
    lat: float
    lon: float
    value: float
    display_unit: str
    p: float
    verdict: Verdict


class TwistResponse(BaseModel):
    found: bool
    variable: VariableId | None = None
    label: str | None = None
    words: GridWords | None = None
    a: TwistSide | None = None
    b: TwistSide | None = None
    sentence: str | None = None
    data_label: DataLabel2 | None = None


class LifetimePlace(BaseModel):
    name: str
    lat: float
    lon: float


class LifetimeItem(BaseModel):
    variable: VariableId
    label: str
    value: float
    display_unit: str
    headline: str
    direction: Literal["up", "down"]
    verdict: Verdict
    p: float
    source: str


class LifetimeResponse(BaseModel):
    place: LifetimePlace
    birth_year: int
    end_year: int
    years: int
    items: list[LifetimeItem]
    data_label: DataLabel2
