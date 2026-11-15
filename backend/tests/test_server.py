"""Single-container deployment: API under /api + built frontend with SPA fallback, and the guarantees around the image
(no secrets baked in, the curated seed cache really contains what the demo needs)."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import grid, server
from app.config import CASES, LAST_FULL_YEAR, START_YEAR

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "backend" / "seed_cache"


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>Earth Trend Detective</title><div id=root>INDEX</div>", "utf-8")
    (d / "assets" / "index-AbC123.js").write_text("console.log('app')", "utf-8")
    (d / "favicon.svg").write_text("<svg/>", "utf-8")
    return d


@pytest.fixture
def client(dist):
    return TestClient(server.build_application(dist))


# ---- the frontend -----------------------------------------------------------------------------------------------------------
def test_root_serves_index_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "INDEX" in r.text and r.headers["cache-control"] == "no-cache"


def test_spa_routes_fall_back_to_index_html(client):
    for path in ("/case/azraq", "/where/map", "/a/b/c"):
        r = client.get(path)
        assert r.status_code == 200 and "INDEX" in r.text, path


def test_hashed_assets_are_served_and_cached_for_a_year(client):
    r = client.get("/assets/index-AbC123.js")
    assert r.status_code == 200 and "console.log" in r.text
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/favicon.svg").status_code == 200


def test_a_missing_file_is_a_real_404_not_index_html(client):
    for path in ("/assets/old-FFFF.js", "/missing.png", "/.env", "/robots.txt"):
        r = client.get(path)
        assert r.status_code == 404 and "INDEX" not in r.text, path


def test_path_traversal_cannot_leave_the_dist_folder(client):
    for path in ("/../../backend/app/config.py", "/%2e%2e/%2e%2e/backend/app/config.py", "/assets/..%2f..%2fapp%2fconfig.py"):
        r = client.get(path)
        assert "CACHE_DIR" not in r.text and "ROOT =" not in r.text, path


def test_default_dist_follows_the_env_var_and_the_repo_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    assert server.default_dist() == tmp_path
    monkeypatch.delenv("FRONTEND_DIST")
    assert server.default_dist() == REPO / "frontend" / "dist"        # same layout inside the image: /srv/frontend/dist


def test_without_a_frontend_build_the_api_still_works(tmp_path):
    c = TestClient(server.build_application(tmp_path / "nope"))
    assert c.get("/api/health").json() == {"ok": True}
    r = c.get("/")
    assert r.status_code == 200 and "frontend build not found" in r.json()["detail"]


# ---- the API under /api ---------------------------------------------------------------------------------------------------
def test_health_check_path_for_the_platform(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_api_routes_are_under_api_only(client):
    assert client.post("/case", json={"question": "run the demo case: Azraq"}).status_code != 200      # not at the root
    assert client.post("/api/case", json={"question": "run the demo case: Azraq"}).status_code == 200


def test_unknown_api_paths_are_json_404s_not_index_html(client):
    for path in ("/api/nope", "/api/", "/api/case/unknown"):
        r = client.get(path)
        assert r.status_code in (404, 405) and "INDEX" not in r.text, path


def test_demo_case_works_end_to_end_through_the_mount_with_images(client):
    r = client.post("/api/case", json={"question": "run the demo case: Azraq"})
    c = r.json()
    assert r.status_code == 200 and c["place"]["name"] == "Azraq" and c["data_label"]["origin"] == "cache"
    assert [w["variable"] for w in c["witnesses"]] == ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS", "NDVI"]
    for w in c["witnesses"]:
        assert w["images"] is not None, w["variable"]                       # every demo image ships in the cache
        url = w["images"]["before"]["url"]
        assert url.startswith("/api/images/")                               # the frontend's /api calls work unchanged
        ri = client.get(url)                                                # served by the mounted API
        assert ri.status_code == 200 and ri.headers["content-type"] == "image/jpeg"


def test_frontend_calls_work_unchanged_through_the_proxyless_mount(client):
    """The frontend calls /api/<endpoint>; in dev Vite strips /api. Here the mount does: same paths, same answers."""
    assert client.post("/api/plan", json={"question": "run the demo case: Azraq"}).json()["planner"] == "demo"
    assert client.get("/api/grid", params={"variable": "T2M"}).status_code == 200
    assert client.get("/api/twist", params={"case_id": "azraq"}).status_code == 200
    assert client.get("/api/lifetime", params={"place": "Azraq", "birth_year": 2005}).status_code == 200
    assert client.get("/api/game/round", params={"case_id": "azraq", "want": "CONFIRMED"}).status_code == 200
    body = {"case_id": "azraq", "message": "How much less rain is there?", "history": [], "place": {"name": "Azraq", "lat": 31.88, "lon": 36.83},
            "variables": ["T2M", "PRECTOTCORR"], "start": 1981, "end": 2025}
    r = client.post("/api/chat", json=body)
    assert r.status_code == 200 and set(r.json()) == {"reply", "source", "cited"}


# ---- the image: no secrets, curated cache ---------------------------------------------------------------------------------
def test_dockerfile_never_bakes_a_secret_in():
    txt = (REPO / "Dockerfile").read_text("utf-8")
    code = "\n".join(l for l in txt.splitlines() if not l.strip().startswith("#"))
    assert not re.search(r"^\s*(ENV|ARG)\s+LLM_API_KEY", code, re.M | re.I) and "LLM_API_KEY=" not in code
    assert not re.search(r"COPY\s+.*\.env", code) and not re.search(r"COPY\s+\.\s", code)             # no "COPY . ." sweeping everything in
    assert "USER app" in code and "--port ${PORT:-8000}" in code and "requirements-prod.txt" in code
    assert "VITE_USE_MOCK=false" in code and "COPY backend/seed_cache" in code and "FROM node" in code and "FROM python:3.12-slim" in code


def test_dockerignore_keeps_env_files_and_dev_junk_out_of_the_build_context():
    lines = {l.strip() for l in (REPO / ".dockerignore").read_text("utf-8").splitlines() if l.strip() and not l.startswith("#")}
    assert {".env", "**/.env", "**/.env.*", ".git", "frontend/node_modules", "backend/data", "backend/tests"} <= lines


def test_env_files_are_git_ignored():
    gi = (REPO / ".gitignore").read_text("utf-8")
    assert re.search(r"^\.env$", gi, re.M) and re.search(r"^\.env\.\*$", gi, re.M) and "backend/data/" in gi


def test_runtime_requirements_are_pinned_and_exclude_test_only_packages():
    req = (REPO / "backend" / "requirements-prod.txt").read_text("utf-8")
    pkgs = [l.split("==")[0].split("[")[0].lower() for l in req.splitlines() if l.strip() and not l.startswith("#")]
    assert all("==" in l for l in req.splitlines() if l.strip() and not l.startswith("#"))
    assert {"fastapi", "uvicorn", "pandas", "pyarrow", "scipy", "pymannkendall", "google-genai", "httpx"} <= set(pkgs)
    assert not ({"pytest", "statsmodels", "watchfiles"} & set(pkgs))


def test_the_app_does_not_import_packages_missing_from_the_runtime_requirements():
    imports = set()
    for f in (REPO / "backend" / "app").rglob("*.py"):
        imports |= set(re.findall(r"^(?:import|from)\s+([A-Za-z_][\w]*)", f.read_text("utf-8"), re.M))
    third_party = {"fastapi", "starlette", "pydantic", "uvicorn", "httpx", "numpy", "pandas", "pyarrow", "scipy", "pymannkendall",
                   "dotenv", "google", "statsmodels", "pytest", "watchfiles"}
    needed = imports & third_party
    assert not (needed & {"statsmodels", "pytest", "watchfiles"}), needed


def test_seed_cache_contains_everything_the_demo_needs():
    assert SEED.is_dir()
    for cid, c in CASES.items():
        la, lo = c["lat"], c["lon"]
        assert (SEED / f"power_monthly_{la:.2f}_{lo:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet").exists(), cid
        assert (SEED / f"power_daily_t2mmax_{la:.2f}_{lo:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet").exists(), cid
        assert len(list(SEED.glob(f"img_{cid}_*.jpg"))) >= 10, cid                                        # their NASA images
    assert (SEED / f"modis_ndvi_31.88_36.83_{LAST_FULL_YEAR}.parquet").exists()                          # Azraq NDVI (the 5th demo witness)
    assert all((SEED / (grid.point_key(*p) + ".parquet")).exists() for p in grid.points())              # the whole 143-point grid
    assert len(list((SEED / "grid_results").glob("*.json"))) == len(grid.GRID_VARIABLES)
    assert (SEED / "gibs_capabilities.xml").exists()                                                      # image planning offline


def test_seed_cache_has_no_throwaway_files_and_a_consistent_meta():
    names = {p.relative_to(SEED).as_posix() for p in SEED.rglob("*") if p.is_file()}
    assert not [n for n in names if n.startswith(("plans/", "explain/", "geocode/", "modis_chunks/")) or "img_custom_" in n]
    pts = {n for n in names if n.startswith(("power_monthly_", "power_daily_"))}
    allowed = {f"power_monthly_{c['lat']:.2f}_{c['lon']:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet" for c in CASES.values()}
    allowed |= {f"power_daily_t2mmax_{c['lat']:.2f}_{c['lon']:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet" for c in CASES.values()}
    allowed |= {grid.point_key(*p) + ".parquet" for p in grid.points()}
    assert pts == allowed, sorted(pts ^ allowed)[:5]                                                      # nothing but demo + grid (no Poland)
    assert not any("53.65_18.73" in n for n in names)
    meta = json.loads((SEED / "meta.json").read_text("utf-8"))
    stems = {Path(n).stem if n.endswith(".parquet") else Path(n).name for n in names}
    assert set(meta) <= stems | names, sorted(set(meta) - stems - names)[:5]                              # no entry for a removed file


def test_seed_cache_is_small_enough_for_a_free_tier_image():
    total = sum(p.stat().st_size for p in SEED.rglob("*") if p.is_file())
    assert total < 25e6, f"{total / 1e6:.1f} MB"


def test_seed_cache_holds_no_secrets():
    for p in SEED.rglob("*.json"):
        t = p.read_text("utf-8", errors="ignore")
        assert not re.search(r"AIza[0-9A-Za-z_\-]{20,}|LLM_API_KEY|api[_-]?key\s*[:=]", t, re.I), p.name
