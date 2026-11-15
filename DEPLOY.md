# Deploying Earth Trend Detective (one container, one URL)

The whole app ships as **one Docker image**: the FastAPI backend serves the API under `/api` and the built frontend at `/`.
The image also contains the curated demo cache (Azraq, Irbid, Dead Sea, the 143-point grid and their NASA images), so the
**demo works even if NASA services are down**. Only the AI partner needs an outside service (Gemini), and it falls back to
rule-based answers if the key is missing or the service fails.

## Environment variables (set on the platform, never in a file or the image)

| Variable | Required | Value |
|---|---|---|
| `LLM_PROVIDER` | for the AI partner | `gemini` |
| `LLM_API_KEY` | for the AI partner | your Gemini API key (mark it **secret**) |
| `LLM_MODEL` | no | overrides the default `gemini-3.5-flash-lite` |
| `PORT` | no | set automatically by Render / Railway (default 8000) |

No key? The app still runs: the planner is rule-based and `/chat` and the explanations use templates.

## 0. Before you push to GitHub

```bash
git ls-files | grep -E "(^|/)\.env$"      # must print NOTHING (the key file is git-ignored)
git status --short backend/seed_cache      # the curated demo cache must be committed
```

`.env` is git-ignored **and** docker-ignored, so the key can't reach GitHub or the image. If a key ever leaked, rotate it.

## 1. Try it locally first (optional but recommended)

```bash
docker build -t earth-trend-detective .
docker run --rm -p 8000:8000 --env-file .env earth-trend-detective     # .env is read at run time only
# open http://localhost:8000   ->   health: http://localhost:8000/api/health
```

## 2. Render (free web service from a GitHub repo)

1. Push the repository to GitHub.
2. Render dashboard → **New +** → **Web Service** → **Build and deploy from a Git repository** → pick the repo.
3. Settings:
   - **Language / Runtime:** `Docker` (Render finds `./Dockerfile`; leave *Root Directory* empty)
   - **Branch:** `main`
   - **Instance Type:** `Free`
4. **Environment Variables** → *Add*: `LLM_PROVIDER` = `gemini`, `LLM_API_KEY` = *(your key)*. Optional: `LLM_MODEL`.
5. **Advanced** → **Health Check Path:** `/api/health`
6. **Create Web Service.** The first build takes about 5–10 minutes. Your URL is `https://<service-name>.onrender.com`.

Free-tier things to know:
- An idle instance **sleeps after ~15 minutes**; the first request then takes ~30–60 s. Open the site once before a demo.
  (Optional: ping `/api/health` every 5–10 minutes with a free uptime monitor to keep it warm.)
- 512 MB RAM is enough; the filesystem is **ephemeral**, so places clicked live on the globe are re-fetched after a restart.
  The demo places ship inside the image and are unaffected.
- The deterministic demo is the question **`run the demo case: Azraq`** (5 fixed witnesses, never depends on the AI).

## 3. Railway (alternative)

1. Push the repository to GitHub.
2. Railway → **New Project** → **Deploy from GitHub repo** → pick the repo. Railway detects the `Dockerfile` and builds it.
3. Service → **Variables** → add `LLM_PROVIDER` = `gemini` and `LLM_API_KEY` = *(your key)*. Optional: `LLM_MODEL`.
   (`PORT` is injected by Railway; the container listens on it.)
4. Service → **Settings** → **Networking** → **Generate Domain**.
5. Service → **Settings** → **Deploy** → **Healthcheck Path:** `/api/health`.
6. No volume is needed (the demo cache is in the image).

## 4. Check the deployment

```bash
URL=https://<your-service-url>
curl $URL/api/health                                                    # {"ok":true}
curl -s -X POST $URL/api/case -H "Content-Type: application/json" \
     -d '{"question":"run the demo case: Azraq"}' | head -c 300         # real data, data_label.origin = "cache"
```
Then open `$URL` in a browser: run the demo case, click the globe on a demo place, and ask the partner a question.

## 5. Updating the demo cache

The committed `backend/seed_cache/` is what the image ships. To refresh it (needs internet):

```bash
cd backend
python prefetch.py --case all --ndvi-rounds 0     # POWER + NASA images for the three demo places
python prefetch.py --grid                         # the 143-point grid + per-cell tests
python tools/make_seed_cache.py --clean           # keep only the demo set, rebuild seed_cache/, delete throwaway files
git add seed_cache && git commit -m "Refresh demo cache"
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| 502 / "no open port" on Render | the container must listen on `$PORT`; the provided `CMD` does. Check the build finished. |
| Build runs out of memory | rebuild on a paid instance, or build the image locally and push it to a registry. |
| Chat says "no LLM configured" | `LLM_PROVIDER` / `LLM_API_KEY` not set on the platform (the app still works with templates). |
| Images show a chart instead of a satellite photo | the NASA Worldview service was down for a live place; it retries in the background. Demo places are always cached. |
| First request is slow | free instance waking up; see above. |
