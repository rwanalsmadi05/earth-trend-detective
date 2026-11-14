"""python prefetch.py --case azraq   (or --case all): download and cache everything for a case.

MODIS NDVI (ORNL service) is slow and flaky, so it is fetched chunk by chunk with resume.
--ndvi-rounds N re-runs the NDVI step up to N times (60 s apart) until every chunk is cached."""
import argparse
import time
from app.config import CASES, LAST_FULL_YEAR
from app import image_specs
from app.sources import power, modis, gibs


def run(case_id: str, ndvi_rounds: int = 1):
    c = CASES[case_id]
    lat, lon = c["lat"], c["lon"]
    print(f"\n=== {c['name']} ({lat}, {lon})  1981-{LAST_FULL_YEAR} ===", flush=True)
    m, st, _ = power.monthly(lat, lon)
    print(f"POWER monthly  [{st}] {m.shape}  {m.index.min():%Y-%m}..{m.index.max():%Y-%m}", flush=True)
    h, st = power.hot_days_per_year(lat, lon)
    print(f"POWER daily    [{st}] hot-days series: {len(h)} years", flush=True)
    # one real NASA image pair per witness (layer names + dates validated against the GIBS capabilities document)
    done = {}
    for vid in image_specs.SPECS:
        try:
            pl = image_specs.plan(vid, lat, lon, m)
        except Exception as e:  # noqa: BLE001
            print(f"GIBS images {vid:18s} FAILED to plan: {e}", flush=True)
            continue
        for day, lyrs in ((pl.before, pl.layers_before), (pl.after, pl.layers_after)):
            key = (pl.tag, day)
            if key in done:
                print(f"GIBS image  {vid:18s} {day} shares {done[key]}", flush=True)
                continue
            try:
                p, st = gibs.snapshot(case_id, pl.tag, pl.bbox, day, lyrs)
                done[key] = p.name
                print(f"GIBS image  {vid:18s} {day} [{st}] {p.name} {p.stat().st_size // 1024} KB", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"GIBS image  {vid:18s} {day} FAILED: {str(e)[:100]}", flush=True)
    for r in range(1, ndvi_rounds + 1):
        try:
            n, st, _ = modis.monthly_ndvi(lat, lon)
            print(f"MODIS NDVI     [{st}] {n.dropna().shape[0]} months", flush=True)
            break
        except Exception as e:
            print(f"MODIS NDVI     round {r}/{ndvi_rounds} incomplete: {str(e)[:120]}", flush=True)
            if r < ndvi_rounds:
                time.sleep(60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="azraq")
    ap.add_argument("--ndvi-rounds", type=int, default=1)
    ap.add_argument("--grid", action="store_true", help="prefetch the POWER grid (29-34 N, 34-40 E, 0.5 deg) for the Where map")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.grid:
        from app import grid
        grid.prefetch_points(a.workers)
        grid.compute_all(refresh=True)      # per-cell tests + BH-FDR for every variable, cached
        raise SystemExit(0)
    for cid in (CASES if a.case == "all" else [a.case]):
        run(cid, a.ndvi_rounds)
