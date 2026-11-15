# Earth Trend Detective: NASA Space Apps 2026 submission

Challenge: **"Be An Earth System Trend Detective!"**

## 1. Summary

**Earth Trend Detective** turns a trend analysis into a case file. You are the detective: you click anywhere on a 3D Earth, ask a question, or pick the variables yourself. NASA datasets are the *witnesses*: air temperature, rainfall, soil moisture, humidity, very hot days and vegetation greenness. The app pulls the data, removes the seasons, tests each series for a trend, and pins every clue to a cork evidence board with a rubber stamp, **CONFIRMED** or **NOT PROVEN**. The stamp comes from the statistics (a trend test at p < 0.05) and never from an AI. For each witness the board shows what is changing, where, by how much, and whether it could be chance.

For the Azraq demo case (1981–2025, NASA POWER) the board says: temperature +2.2 °C (CONFIRMED), very hot days +36 days per year (CONFIRMED), root-zone soil wetness −3% (CONFIRMED), rainfall −34% (CONFIRMED, borderline, p = 0.013).

## 2. How we address the challenge

| Challenge requirement | What delivers it |
|---|---|
| **Select variables** | Nine variables from a fixed catalog (temperature, max temperature, rainfall, root-zone and surface soil moisture, humidity, solar radiation, vegetation NDVI, very hot days). An AI planner picks them from a question, or the **"Pick the witnesses yourself"** panel lets you tick them, choose a place (gazetteer search, map click) and a period. The manual path works with no AI at all. |
| **Visualize change over time** | Each witness has a yearly anomaly chart (expert view), "before / now" NASA satellite photos, the **Where map** time slider (1981 to now, with play), and the **Since you were born** section. |
| **What is changing** | One polaroid per variable with a plain-language headline ("34% less rain since 1981") and the source. |
| **Where it is changing** | The **Where map**: one trend test in every 0.5° cell of a 143-point grid over 29–34° N, 34–40° E. You can also click anywhere on the globe to open a case at a new place. |
| **How much** | Sen's slope per decade, total change in real units, and % change versus the first decade, shown as the huge number on each polaroid. |
| **Is it significant** | Modified Mann-Kendall on de-seasonalised data, stamp at p < 0.05, p-value on hover, borderline cases flagged. On the map, Benjamini-Hochberg FDR correction is applied before a cell counts as significant; the rest are hatched. |
| **Opposite trends in one variable** | **The Twist** searches the grid for the strongest pair of significant trends of opposite sign. **Honest status:** for the Azraq demo case no such pair survives the FDR correction (`GET /twist` returns `found: false`), so the section is hidden rather than faked. In the Azraq-region grid, rainfall has cells of both signs, but none passes the multiple-test correction, and the map says so in a banner. |

## 3. Features

- **Globe: click anywhere.** A 3D Earth (NASA Blue Marble and Black Marble imagery, day/night terminator, drifting clouds). Drag to rotate, click a point and the camera flies in, an "investigating…" animation runs, then the evidence board opens for that place. Places with no cached data are fetched live from NASA POWER, so new places can take several seconds.
- **Evidence board.** Cork board with a polaroid per witness: NASA satellite photo (before/now), huge number, handwritten headline, source, stamp, red string for lagged correlation (labelled "correlation, not causation"), a country outline map with the place circled, and sticky-note hints. If a photo is missing or blank, the yearly chart is shown instead.
- **Verdict.** A theatre-style section with a stamp slam. The case-level stamp is a majority count of the witnesses' own math-decided verdicts, shown with the backend's headline and any borderline note.
- **Where map.** Dark MapLibre map, blue/orange cells coloured by meaning (warming, less rain, drier soil = orange), hatched = could be chance, plain-word legend with the value range, hover tooltip, witness switcher, time slider with play, click a cell to open a case there. Only shown inside the cached region.
- **Since you were born.** A Mad-Libs sentence ("I was born in 2005 in Azraq. Since then…") with editable inputs and three giant numbers, each with its own stamp, computed with the same test over the years since birth.
- **Manual witness picker.** Place + variables + period range slider, sent to `POST /case` with no question and no AI.
- **Real or noise? game.** Five rounds. Each shows an unlabeled real yearly anomaly series; you guess "real trend" or "just noise"; the stamp reveals the true test result. Every answer is a real test result, never simulated.
- **Case report.** One-click square PNG case card and a one-page PDF with the method, numbers, p-values and sources.
- **Ask your partner.** A slide-in chat panel (`POST /chat`) that answers questions about the current case only, from the computed numbers.
- **Honesty in the interface.** Cached, live and simulated data are labelled; every verdict is hoverable for its p-value. The interface is in English only.

## 4. NASA data and resources used

| Resource | Used for | URL (as used in the code) |
|---|---|---|
| **NASA POWER, monthly point API** (no key) | Monthly T2M, T2M_MAX, PRECTOTCORR, GWETROOT, GWETTOP, RH2M, ALLSKY_SFC_SW_DWN, 1981 to the latest full year, community AG | `https://power.larc.nasa.gov/api/temporal/monthly/point` |
| **NASA POWER, daily point API** | Daily T2M_MAX, counted into "days per year above 35 °C" | `https://power.larc.nasa.gov/api/temporal/daily/point` |
| **MODIS MOD13Q1 NDVI via ORNL DAAC** | Vegetation greenness, band `250m_16_days_NDVI`, from February 2000 (demo places only) | `https://modis.ornl.gov/rst/api/v1/MOD13Q1` |
| **NASA GIBS / Worldview snapshot API** | The before/now satellite photos on the board. Layers requested: `MODIS_Terra_CorrectedReflectance_TrueColor`, `MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day`, `MODIS_Terra_L3_NDVI_Monthly`, `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture`, `SMAP_L4_Analyzed_Surface_Soil_Moisture`, with a `Coastlines_15m` overlay; layer names and dates are checked against the GIBS capabilities document | `https://wvs.earthdata.nasa.gov/api/v1/snapshot`, `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml` |
| **NASA Blue Marble** (day texture) | Globe surface. GIBS layer `BlueMarble_ShadedRelief_Bathymetry`, downloaded once at 4096×2048 | `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi` |
| **NASA Black Marble** (night lights) | City lights on the night side. NASA Earth Observatory "Earth at Night 2012" (`dnb_land_ocean_ice.2012.3600x1800.jpg`), resized | `https://assets.science.nasa.gov/dynamicimage/assets/science/esd/eo/images/imagerecords/79000/79765/dnb_land_ocean_ice.2012.3600x1800.jpg` |
| **MODIS land-water mask** | Ocean mask so the sun glint shows on water only. GIBS layer `MODIS_Terra_L3_Land_Water_Mask` | `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi` |
| **MODIS Terra cloud fraction** | Coverage for the cloud shells. GIBS layer `MODIS_Terra_Cloud_Fraction_Day`, composite of 2025-07-01, with orbit gaps filled and combined with procedural noise | `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi` |

The globe textures were prepared once and are shipped in `frontend/public/textures` (credits in `CREDITS.txt`). The globe displays NASA imagery with a visual cloud layer; it is decoration, not data used in any statistic.

## 5. Other data and tools

- **Natural Earth** 1:50m admin-0 country outlines (public domain, `naturalearthdata.com`), bundled as `frontend/public/data/countries.json` for the case map.
- **OpenStreetMap Nominatim** (`https://nominatim.openstreetmap.org`) for naming places that are not in our built-in gazetteer (backend and the picker's search).
- **Esri "World Dark Gray Base" basemap tiles** (`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer`) under the Where map and the picker map.
- **Backend:** Python, FastAPI, pandas, NumPy, SciPy, `pymannkendall`, httpx, pyarrow (Parquet cache), `google-genai`; pytest for tests.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Framer Motion, react-globe.gl on three.js, MapLibre GL, html-to-image and jsPDF (the PNG and PDF exports). Fonts from Google Fonts (Unbounded, Inter, JetBrains Mono, Special Elite, Caveat).
- **Deployment:** one Docker image, FastAPI serves the API under `/api` and the built frontend at `/`, with a curated demo cache baked in (Azraq, Irbid, Dead Sea, the 143-point grid, their NASA images) so the demo works even if NASA services are slow or down (see `DEPLOY.md`).

## 6. Method

All verdicts come from `backend/app/stats.py`.

1. **Monthly anomalies.** For every series, each calendar month's long-term mean is subtracted, so seasons do not look like trends.
2. **Trend test.** Mann-Kendall with the **Hamed-Rao autocorrelation correction, lag capped at 12 months**, run on the monthly anomalies (via `pymannkendall`). If the Hamed-Rao variance is invalid, trend-free pre-whitening is used instead. Annual-count variables (very hot days) are tested on the annual values. **CONFIRMED** if p < 0.05, otherwise **NOT PROVEN**; CONFIRMED with 0.01 ≤ p < 0.05 is flagged **borderline**.
3. **How much.** Sen's slope on the **annual means** (years with at least 6 valid months): per decade, total change over the record, and % change versus the first ten years' mean.
4. **Maps.** The same test runs in every grid cell, then **Benjamini-Hochberg FDR** correction across all tested cells of a variable (α = 0.05) before a cell is called significant.
5. **Chain of evidence.** Lagged cross-correlation of the monthly anomalies at lags 0–6 months (|r| ≥ 0.3, at most three links). It shows what moved first; it is correlation, not causation.
6. **False-positive check on synthetic noise** (`backend/tools/fp_experiment.py`, 100 seeds per setting, trendless AR(1) noise, nominal rate 5%). The implemented test gives **6% / 9% / 15%** false positives at autocorrelation φ = 0 / 0.6 / 0.9, with 83% power to detect a 0.01-per-year trend at φ = 0.6. The same experiment measured 11% / 20% / 32% for Hamed-Rao with default lags and 44% for the Yue-Wang variant, which is why we cap the lag at 12 and do not use Yue-Wang.
7. **Tests.** 383 automated backend tests cover the statistics, the API, the AI guards, the game, live places and the single-container server. All 383 pass at the time of writing. The image-retry tests use a fake timer the test fires on command (no wall-clock assumptions), and we checked they fail when the retry logic is deliberately broken.

**Real results, not hand-picked.** In the cached Azraq grid, temperature is significant in 143 of 143 cells after FDR; rainfall in **0 of 143** cells; root-zone soil wetness in 7 of 135. The map says so in a banner instead of colouring noise.

## 7. Limitations

- **NASA POWER is a ~0.5° reanalysis (MERRA-2), not station data.** A cell averages a wide area that can include uplands, and rainfall can read higher than a local station.
- **Rainfall at Azraq is borderline** (p = 0.013, inside the 0.01 to 0.05 band that we flag as borderline). We mark it as such on the board and in the verdict.
- **Soil moisture is a model index** (a soil-wetness index from MERRA-2 via POWER), not a satellite measurement.
- **NDVI starts in 2000** and is only available for the demo places.
- **Correlation is not causation.** The red string and the chat only describe what moved first.
- **The Where map is only available inside the cached region** (29–34° N, 34–40° E). Outside it, the map is hidden instead of computing a slow live grid.
- **The Twist is hidden** because no opposite-sign pair survives the FDR correction in our data.
- **New places** are fetched live and can be slow; satellite photos for new places may be missing, in which case a chart is shown.
- The interface is English only.

## 8. AI usage disclosure

- **Claude Code (Anthropic)** was used to write and test the code in this repository (frontend and backend) under our direction.
- **Google Gemini** (`gemini-3.5-flash-lite`, with `gemini-3.1-flash-lite` as fallback, via the `google-genai` library) runs inside the app for exactly three jobs: choosing variables for a question from the fixed catalog, wording explanations and hints, and answering questions in the chat. It receives the computed numbers as context. In code, every number in its text must match a computed number, a sentence may not contradict a witness's math-decided verdict, hints may contain no numbers or verdict words, and out-of-scope questions get a fixed "I don't know". Text that fails a guard is replaced by a template built from the same numbers. Without an API key the app still works with a rule-based planner and template text.
- **Verdicts and stamps come only from the statistics.** The AI never decides significance.
- **No AI-generated images.** Every picture is NASA imagery or a NASA-derived texture.

## 9. Links and team

- Demo: [DEMO URL]
- Code: [GITHUB REPO]
- Video: [VIDEO]

**Team:**
- Rwan Ahmed Mohammad Alsmadi
- Bashar Rami Mukbel
- Nabeel Nizar Nabeel Maaiah
- Raghad Mohammad Abu Al-Haija
