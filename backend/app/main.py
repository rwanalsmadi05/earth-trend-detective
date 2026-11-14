"""FastAPI app. Run: uvicorn app.main:app --port 8000 --reload   (frontend dev proxy forwards /api/* here)."""
import re
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import cache, game as game_mod, grid, i18n, lifetime as lifetime_mod, planner
from . import explain as explain_mod
from .case_builder import PlaceNotFound, build_case_and_expert
from .models import (CaseRequest, CaseResponse, ExpertResponse, ExplainResponse, GameRound, GridResponse, LifetimeResponse,
                     PlanResponse, TwistResponse)
from .variables import VARIABLES

app = FastAPI(title="Earth Trend Detective")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True}


def _run(req: CaseRequest):
    try:
        manual = req.variables is not None or (req.lat is not None and req.lon is not None)
        plan = None if manual else planner.plan_question(req.question)   # Gemini, or the rule-based fallback
        return build_case_and_expert(req.question, req.variables, req.lat, req.lon, req.place, req.start, req.end, plan=plan)
    except PlaceNotFound as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001  (network down and nothing cached)
        raise HTTPException(503, f"data unavailable: {e}")


@app.post("/plan", response_model=PlanResponse)
def post_plan(req: CaseRequest):
    """What the AI partner decided: cleaned question, place (gazetteer), catalog variables with reasons."""
    try:
        return asdict(planner.plan_question(req.question))
    except PlaceNotFound as e:
        raise HTTPException(422, str(e))


@app.post("/case", response_model=CaseResponse)
def post_case(req: CaseRequest):
    return _run(req)[0]


@app.post("/case/expert", response_model=ExpertResponse)
def post_case_expert(req: CaseRequest):
    """Expert-drawer data kept off /case so that /case matches frontend types.ts exactly:
    which test method was used per variable, why a test failed (if it did), n, tau, p, Sen's slope, borderline."""
    return _run(req)[1]


@app.post("/case/explain", response_model=ExplainResponse)
def post_case_explain(req: CaseRequest):
    """Plain-language explanation of the computed results. Numbers and verdicts are guarded in code (explain.py)."""
    case, expert = _run(req)
    return explain_mod.explain(case, expert["variables"], i18n.detect_language(req.question))


@app.get("/grid", response_model=GridResponse)
def get_grid(variable: str, bbox: str | None = None):
    """The Where map: one trend test per grid cell, Benjamini-Hochberg FDR-corrected. bbox = west,south,east,north."""
    if variable not in grid.GRID_VARIABLES:
        raise HTTPException(422, f"variable {variable!r} is not available on the grid (POWER monthly variables only: "
                                 f"{', '.join(grid.GRID_VARIABLES)})")
    box = None
    if bbox:
        try:
            w, s, e, n = (float(x) for x in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox must be four numbers: west,south,east,north")
        if not (w < e and s < n):
            raise HTTPException(422, "bbox must satisfy west < east and south < north")
        box = (w, s, e, n)
    try:
        return grid.grid_response(variable, box)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/twist", response_model=TwistResponse, response_model_exclude_none=True)
def get_twist(case_id: str):
    """The Twist: same variable, significant (FDR) trends of opposite sign; `found: false` when there is none."""
    try:
        res = grid.twist(case_id)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if res is None:
        raise HTTPException(404, f"unknown case_id {case_id!r}")
    return res


@app.get("/lifetime", response_model=LifetimeResponse)
def get_lifetime(place: str, birth_year: int):
    """'Since you were born': three giant numbers (temperature, rainfall, very hot days) with their own verdicts."""
    try:
        return lifetime_mod.lifetime(place, birth_year)
    except PlaceNotFound as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001  (network down and nothing cached)
        raise HTTPException(503, f"data unavailable: {e}")


@app.get("/game/round", response_model=GameRound, response_model_exclude_none=True)
def get_game_round(case_id: str, want: str | None = None, exclude: str = ""):
    """One 'Real or noise?' round: a real series with its real verdict. want = CONFIRMED | NOT PROVEN (optional);
    exclude = comma-separated variable ids already used. 404 if no real series matches."""
    if want is not None and want not in ("CONFIRMED", "NOT PROVEN"):
        raise HTTPException(422, "want must be CONFIRMED or NOT PROVEN")
    skip = [x.strip() for x in exclude.split(",") if x.strip()]
    bad = [x for x in skip if x not in VARIABLES]
    if bad:
        raise HTTPException(422, f"unknown variable id(s) in exclude: {', '.join(bad)}")
    try:
        return game_mod.game_round(case_id, want, skip)
    except KeyError:
        raise HTTPException(404, f"unknown case_id {case_id!r}")
    except game_mod.NoRound as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001  (network down and nothing cached)
        raise HTTPException(503, f"data unavailable: {e}")


@app.get("/images/{name}")
def image(name: str):
    if not re.fullmatch(r"img_[A-Za-z0-9_.\-]+\.jpg", name):
        raise HTTPException(404)
    p = cache.blob_path(name)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")
