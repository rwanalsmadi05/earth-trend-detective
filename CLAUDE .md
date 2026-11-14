# Build: Earth Trend Detective (NASA Space Apps 2026)

You are a senior full-stack engineer and a world-class product designer. Build a complete, working, demo-ready web app for the NASA Space Apps 2026 challenge **"Be An Earth System Trend Detective!"**. The result must feel cinematic and "wow", but every number must come from real NASA data and real statistics.

---

## 1. The challenge (must be fully satisfied)

> Create a tool that can select variables measured by Earth science missions or produced by Earth science models, visualize how they change over time, and determine **what** is changing, **where** it is changing, **how much** it is changing, and whether these changes are statistically **significant**. Note: one variable can trend one way in one region and the opposite way in another, even when the same process drives both.

Map every feature you build to one of these: *select variables · visualize change over time · what · where · how much · significant · opposite trends*.

---

## 2. Concept

The user is a **detective**. They ask a question about a place in plain language (English or Arabic), for example *"Is Azraq drying up?"* or *"هل إربد عم تسخن؟"*. The app opens a **case**, an AI partner picks the right NASA variables as **witnesses**, the app pulls the data automatically, runs the statistics, pins every clue to a realistic **evidence board**, and stamps each clue **CONFIRMED** or **NOT PROVEN**. The stamp comes from the math, never from the AI.

Default demo case: **Azraq, Jordan (31.88° N, 36.83° E), 1981 → latest full year.**

---

## 3. Data: fetched automatically, no manual steps

Build a Python data layer that fetches, caches and serves everything. No API keys required for the core.

### 3.1 NASA POWER (main source, monthly from 1981, no auth)
- Endpoint: `https://power.larc.nasa.gov/api/temporal/monthly/point`
- Params: `parameters=T2M,T2M_MAX,PRECTOTCORR,GWETROOT,GWETTOP,RH2M,ALLSKY_SFC_SW_DWN&community=AG&latitude=..&longitude=..&start=1981&end=<last full year>&format=JSON`
- Daily endpoint (`/api/temporal/daily/point`) for counts such as "days per year with T2M_MAX > 35 °C".
- Drop POWER's annual "13th month" values and the fill value `-999`.

### 3.2 MODIS NDVI (vegetation, from 2000, no auth)
- ORNL DAAC MODIS Web Service: `https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset?latitude=..&longitude=..&band=250m_16_days_NDVI&startDate=A2000049&endDate=A<yyyyddd>&kmAboveBelow=1&kmLeftRight=1`
- Request in date chunks (the service limits dates per call), apply the scale factor 0.0001, mask invalid values, aggregate to monthly means.
- Clearly label in the UI that NDVI starts in 2000.

### 3.3 Real satellite photos for the evidence board (no auth)
- NASA Worldview snapshot API (GIBS): `https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&TIME=<date>&BBOX=<s>,<w>,<n>,<e>&CRS=EPSG:4326&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor&FORMAT=image/jpeg&WIDTH=600&HEIGHT=500`
- Fetch a true-color image of the case area for an early and a recent date. Look up valid GIBS layer names (true color, NDVI, land surface temperature) from the GIBS capabilities document instead of guessing.

### 3.4 Gridded "where" map
- Build a grid over a bounding box around the case location (default 29–34° N, 34–40° E, 0.5° or 1° steps) and fetch POWER monthly series per grid point. Cache everything to disk (Parquet or SQLite) so the second run is instant.

### 3.5 Offline demo mode (critical for hackathon Wi-Fi)
- A script `python prefetch.py --case azraq` that downloads and caches all data, images and results for 3 demo cases (Azraq, Irbid, Dead Sea region).
- If the network fails, the app silently serves the cache. Show a small "cached data · fetched <date>" label.

### 3.6 Place names
- Ship a small built-in gazetteer of Jordan and regional places (name in English + Arabic + lat/lon). Fall back to OpenStreetMap Nominatim only if a place is missing. The user can also click the globe or map to pick a point.

---

## 4. Statistics (the scientific core; must be correct and explainable)

For every variable series:
1. **Remove seasonality**: monthly anomalies (subtract each calendar month's long-term mean) or STL decomposition.
2. **Trend test**: Mann-Kendall with autocorrelation correction (Hamed–Rao modified MK, e.g. the `pymannkendall` library). Output tau, p-value.
3. **How much**: Sen's slope, reported per decade and as total change over the period, in real units, plus percent change vs the 1981–1990 baseline.
4. **Verdict**: `CONFIRMED` if p < 0.05, otherwise `NOT PROVEN`. Show the p-value on hover for experts.
5. **Grid maps**: run the same test per grid cell and apply **Benjamini–Hochberg FDR** correction before colouring a cell as significant.
6. **Opposite trends**: find cells or regions where the same variable has significant trends in opposite directions and surface the strongest pair as "The Twist".
7. **Chain of evidence**: lagged cross-correlation between anomaly series (lag 0–6 months) to show which variable moved first (e.g. temperature → soil moisture → NDVI). Label it as correlation, not causation.
8. **Unit tests** for the statistics on synthetic series with a known trend and with pure noise.

---

## 5. AI partner (LLM): rules

- Use tool/function calling with a strict JSON schema. The LLM may only:
  1. Parse the question → `{place, lat, lon, period, variables[], reason_per_variable}` choosing **only** from a fixed variable catalog (temperature, max temperature, rainfall, root-zone soil moisture, surface soil moisture, humidity, solar radiation, NDVI, hot days count).
  2. Explain computed results in simple language (English or Arabic, matching the user).
  3. Give **hints** on the evidence board ("Notice the plants dropped after the soil did…") without revealing verdicts the user hasn't seen.
- The LLM receives the computed numbers as context and must **never** invent numbers or decide significance. If a number isn't in the context, it says it doesn't know.
- Make the model provider configurable via an environment variable.

---

## 6. Features (in priority order)

1. **Open a case**: one input, plain language, English/Arabic. Shows a short "case opening" animation and the partner's reasoning for each chosen variable.
2. **Evidence board** (the signature screen, see design below): one pinned clue per variable with real satellite image, big plain-language result ("[−18]% less rain than in the 1980s"), source, and the stamp.
3. **Where map**: interactive dark map with the grid trend layer (blue = rising, orange = falling, faded = not significant), a time slider from 1981 to now with a play button, and a click-to-open-case on any cell.
4. **The Twist**: same cause, opposite effects: two glowing circles showing the strongest opposite-trend pair.
5. **Verdict**: the case-level verdict ("3 of 4 witnesses confirm: Azraq is getting drier") with a dramatic stamp animation.
6. **Since you were born**: Mad-Libs sentence "I was born in [2005] in [Irbid]. Since then…" → 3 giant numbers computed from the user's birth year to the latest year, each with its own stamp.
7. **Real or noise?** mini game: shows a real anomaly series without labels; the user guesses "real trend" or "just noise"; the stamp reveals the true MK result. Uses real cached series, mixing confirmed and not-proven ones.
8. **Case report**: export a shareable PNG card and a one-page PDF with the method, numbers, p-values and data sources.
9. **Expert drawer**: for judges, a toggle that reveals the raw series chart, anomalies, tau, p, Sen's slope, n, and the data URLs used.

---

## 7. Design: cinematic, realistic, "wow"

**Mood**: a detective's investigation room at night meets a NASA mission control. Dark, warm lamp light, real textures, purposeful motion.

**Palette**: night `#05070B`, paper `#F4F1EA`, heat orange `#FF8A3D`, cool blue `#7CC8FF`, stamp red `#C8261E`. Blue = rising, orange = falling (colour-blind safe; never rely on red/green).

**Type**: Unbounded (display), Inter (body), JetBrains Mono (HUD labels, numbers), Special Elite (typewriter on case files), Caveat (handwriting on notes and polaroids). Add an Arabic font (e.g. IBM Plex Sans Arabic) and full RTL support.

**Hero**: full-screen space scene with a **realistic 3D Earth** (three.js / react-globe.gl with NASA Blue Marble day texture + night-lights texture, atmosphere glow, slowly drifting clouds), twinkling stars, occasional shooting stars, drifting nebula light. A pulsing target lens locks onto the case location with coordinates in a HUD. Headline: **"THE EARTH IS LEAVING CLUES."** revealed line by line with a blur-to-sharp animation. A glassy search pill. A data ticker scrolling at the bottom. When a case opens, the camera flies smoothly to the location.

**Evidence board**: a real-looking cork board in a dark wood frame, lit by a hanging lamp with a warm light cone and a subtle flicker, vignette at the edges. On it: a lined case card in typewriter font; a paper map of the region with the place circled in red marker; one **polaroid per variable** showing the real satellite snapshot (before/after for vegetation), a handwritten caption and a rubber stamp; **red string** between pins drawn with natural sag (SVG), following the chain of evidence; sticky notes with the AI partner's hints in handwriting; a magnifying glass, a coffee ring and a torn verdict strip as details. Clues pin themselves one by one with a small drop-and-bounce; the string draws itself between them. Hovering a polaroid lifts it with a deeper shadow; clicking opens the detail with the expert chart.

**Verdict section**: theatre-dark with a spotlight beam from above, floating dust particles, and a huge **CONFIRMED** stamp that slams down with a shock wave.

**Motion**: Framer Motion + GSAP ScrollTrigger for scroll-driven chapters, a soft cursor spotlight, and lifting cards on hover. Respect `prefers-reduced-motion`.

**Honesty in the UI**: every number shows its source on hover; anything simulated or cached is labelled.

**Responsive**: works on a phone (board becomes a swipeable stack of polaroids).

---

## 8. Tech stack

- **Frontend**: React + Vite + TypeScript, Tailwind, Framer Motion, GSAP, three.js / react-globe.gl, MapLibre GL (dark basemap) or deck.gl for the grid layer, html-to-image for the PNG card.
- **Backend**: Python FastAPI, pandas, numpy, pymannkendall, statsmodels (STL), scipy, httpx with retries, Parquet/SQLite cache.
- **Endpoints**: `POST /case` (question → plan + results), `GET /series`, `GET /grid`, `GET /twist`, `GET /lifetime`, `GET /game/round`, `GET /report`.
- One command to run everything locally (`docker compose up` or a `make dev`), plus a README with setup, data sources and method.

---

## 9. Build order (we have about 24 hours)

1. Data layer + cache + `prefetch.py` for Azraq → working series for 4 variables.
2. Statistics module + unit tests → verdicts for Azraq.
3. `POST /case` with the LLM planner (fixed catalog) → end-to-end JSON.
4. Hero + evidence board with real data and stamps (this is the demo).
5. Verdict section + Since you were born.
6. Where map with grid + The Twist.
7. Real or noise game, case report export, expert drawer.
8. Polish motion, RTL/Arabic, phone layout.

After each step, the app must still run.

---

## 10. Acceptance checklist

- [ ] Typing "Is Azraq drying up?" opens a full case with real NASA data, no manual steps.
- [ ] Every variable shows what / where / how much / significant, with units and source.
- [ ] Seasonality removed, modified MK + Sen's slope + FDR on maps, all unit-tested.
- [ ] The LLM never produces a number or a verdict on its own.
- [ ] Opposite-trend pair is found from data, not hard-coded.
- [ ] Works offline from the cache for the 3 demo cases.
- [ ] English and Arabic both work, including RTL.
- [ ] Loads in under 3 seconds from cache; animations stay smooth.
- [ ] README explains data sources, method and limitations (POWER is model/reanalysis-based at ~0.5° resolution; NDVI starts in 2000; correlation is not causation).

---

## 11. Also required

- **Manual variable selection**: next to the AI planner, add a "Pick the witnesses yourself" panel where the user ticks variables from the catalog, chooses the period and the place on the map. The challenge says the tool must let users *select variables*, so this must work without the LLM.
- **Optional extra witness, GRACE / GRACE-FO groundwater** (terrestrial water storage, 2002 → now). Very relevant to Azraq's aquifer. Needs a free NASA Earthdata login: read the token from an environment variable, and if it's missing, hide this variable instead of failing.
- **Keys and config**: `.env.example` with `LLM_PROVIDER`, `LLM_API_KEY`, `EARTHDATA_TOKEN` (optional). The core data works with no keys; only the AI partner needs `LLM_API_KEY`. If no LLM key is set, the app falls back to manual selection and template explanations.
- **Public deployment**: judges need a live link. Make the frontend deployable as a static build (e.g. Vercel or Netlify) and the backend as one container (e.g. Render, Railway or Fly.io), serving the prefetched cache so the live demo never depends on NASA APIs being fast.
- **Submission support**: generate a `SUBMISSION.md` with a project summary, the list of NASA data and resources used with links, the tools and AI models used (Space Apps asks teams to disclose AI use), and the method and limitations.

Start by printing the project structure, then build step 1.
