# One container, one URL: the FastAPI backend serves the API under /api and the built frontend at /.
# Build context = the repository root:   docker build -t earth-trend-detective .
#
# SECRETS: nothing secret is ever copied or baked in. LLM_PROVIDER / LLM_API_KEY (and optionally LLM_MODEL) are read
# from the container's ENVIRONMENT at runtime. Without them the app still works (rule-based planner and template text).

# ---- stage 1: build the frontend ------------------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# real backend, not the built-in mock data (also overrides any stray frontend/.env.local)
ENV VITE_USE_MOCK=false
RUN npm run build

# ---- stage 2: slim Python runtime --------------------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv/backend

COPY backend/requirements-prod.txt ./
RUN pip install -r requirements-prod.txt

COPY backend/app ./app
# the curated demo cache (3 demo places, the 143-point grid, their NASA images): the demo works with NASA services down
COPY backend/seed_cache ./data/cache
COPY --from=web /web/dist /srv/frontend/dist

# run as a non-root user; data/cache must stay writable (places clicked live are cached there until the instance restarts)
RUN useradd --create-home --uid 10001 app && chown -R app:app /srv/backend/data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.getenv('PORT','8000'), timeout=4)"

# Render / Railway / Fly inject $PORT; default 8000
CMD ["sh", "-c", "exec uvicorn app.server:application --host 0.0.0.0 --port ${PORT:-8000}"]
