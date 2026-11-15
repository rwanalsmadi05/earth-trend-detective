"""Production entry point: ONE process, ONE URL.

  /api/...   the whole API (the frontend's own calls, unchanged: its dev proxy strips /api, here the mount does;
             image URLs the API returns are /api/images/...)
  /...       the built frontend (frontend/dist) with a single-page-app fallback: any route-like path that is not a
             file returns index.html so client-side routes survive a reload

Run:  uvicorn app.server:application --host 0.0.0.0 --port $PORT"""
import os
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from .config import ROOT
from .main import app as api


def default_dist() -> Path:
    """FRONTEND_DIST if set, else <repo>/frontend/dist (the same layout inside the Docker image)."""
    return Path(os.getenv("FRONTEND_DIST") or ROOT.parent / "frontend" / "dist")


class SPAStaticFiles(StaticFiles):
    """Static files + SPA fallback. Hashed build assets are cached for a year, index.html never, and a missing *file*
    (a path with an extension, e.g. /assets/old.js) is a real 404, not index.html."""

    async def get_response(self, path, scope):
        path = path.replace("\\", "/")          # Starlette passes OS-style paths (backslashes on Windows)
        try:
            resp = await super().get_response(path, scope)
            missing = resp.status_code == 404
        except StarletteHTTPException as e:
            if e.status_code != 404:
                raise
            resp, missing = None, True
        if missing:
            if "." in Path(path).name:
                raise StarletteHTTPException(404)
            resp = await super().get_response("index.html", scope)
            path = "index.html"
        if path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path in ("", ".", "index.html"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp


def build_application(dist: Path | None = None) -> FastAPI:
    root = FastAPI(title="Earth Trend Detective", docs_url=None, redoc_url=None, openapi_url=None)
    root.mount("/api", api)
    dist = Path(dist) if dist else default_dist()
    if (dist / "index.html").exists():
        root.mount("/", SPAStaticFiles(directory=dist, html=True), name="frontend")
    else:
        @root.get("/")
        def no_frontend():
            return {"detail": f"frontend build not found at {dist}; the API is available under /api"}
    return root


application = build_application()
