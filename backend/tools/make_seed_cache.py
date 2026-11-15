"""Curate the demo cache.

Keeps ONLY what the demo needs, so the deployed app works even when NASA services are down:
  - the three demo places (config.CASES: Azraq, Irbid, Dead Sea): POWER monthly + daily, NDVI if cached, and their NASA images
  - the whole POWER grid (29-34 N, 34-40 E, 0.5 deg) and its precomputed per-cell tests (grid_results/)
  - the GIBS capabilities document (image planning works offline)
  - meta.json, pruned to the kept entries
Everything else is throwaway: test points (Poland, Nairobi, ...), clicked-on-the-globe places, cached plans/explanations,
geocoder answers, per-chunk NDVI downloads.

  python tools/make_seed_cache.py            # dry run: report what is kept / would be removed from data/cache
  python tools/make_seed_cache.py --clean    # also delete the throwaway files from data/cache
Always (re)builds backend/seed_cache/ (the committed copy that the Docker image ships as its data/cache)."""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grid  # noqa: E402
from app.config import CACHE_DIR, CASES, LAST_FULL_YEAR, START_YEAR  # noqa: E402

SEED = CACHE_DIR.parents[1] / "seed_cache"


def keep_set():
    keep, problems = set(), []
    for cid, c in CASES.items():
        la, lo = c["lat"], c["lon"]
        for name in (f"power_monthly_{la:.2f}_{lo:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet",
                     f"power_daily_t2mmax_{la:.2f}_{lo:.2f}_{START_YEAR}_{LAST_FULL_YEAR}.parquet"):
            (keep.add(name) if (CACHE_DIR / name).exists() else problems.append(f"{cid}: missing {name}"))
        ndvi = f"modis_ndvi_{la:.2f}_{lo:.2f}_{LAST_FULL_YEAR}.parquet"
        if (CACHE_DIR / ndvi).exists():
            keep.add(ndvi)
        imgs = sorted(p.name for p in CACHE_DIR.glob(f"img_{cid}_*.jpg"))
        keep.update(imgs)
        if not imgs:
            problems.append(f"{cid}: no images cached (run: python prefetch.py --case {cid} --ndvi-rounds 0)")
    for p in grid.points():
        name = grid.point_key(*p) + ".parquet"
        (keep.add(name) if (CACHE_DIR / name).exists() else problems.append(f"grid point {p} missing"))
    keep.update(f"grid_results/{f.name}" for f in (CACHE_DIR / "grid_results").glob("*.json"))
    if (CACHE_DIR / "gibs_capabilities.xml").exists():
        keep.add("gibs_capabilities.xml")
    return keep, problems


def all_files():
    return {p.relative_to(CACHE_DIR).as_posix() for p in CACHE_DIR.rglob("*") if p.is_file() and p.name != "meta.json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="delete the throwaway files from data/cache")
    a = ap.parse_args()
    keep, problems = keep_set()
    everything = all_files()
    drop = sorted(everything - keep)
    size = lambda names: sum((CACHE_DIR / n).stat().st_size for n in names) / 1e6  # noqa: E731
    print(f"data/cache: {len(everything)} files, {size(everything):.1f} MB")
    print(f"  keep : {len(keep)} files, {size(keep):.1f} MB")
    print(f"  drop : {len(drop)} files, {size(drop):.1f} MB")
    kinds = {}
    for n in drop:
        k = n.split("/")[0] if "/" in n else n.split("_")[0] + "_" + n.split("_")[1] if n.count("_") > 1 else n
        kinds[k] = kinds.get(k, 0) + 1
    print("  dropped by kind:", dict(sorted(kinds.items())))
    for p in problems:
        print("  PROBLEM:", p)

    meta = json.loads((CACHE_DIR / "meta.json").read_text("utf-8")) if (CACHE_DIR / "meta.json").exists() else {}
    stems = {Path(n).stem if n.endswith(".parquet") else Path(n).name for n in keep}
    pruned = {k: v for k, v in meta.items() if k in stems or k in keep}
    print(f"  meta.json: {len(meta)} entries -> {len(pruned)}")

    if SEED.exists():
        shutil.rmtree(SEED)
    for n in keep:
        dst = SEED / n
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CACHE_DIR / n, dst)
    (SEED / "meta.json").write_text(json.dumps(pruned, indent=2), "utf-8")
    print(f"seed_cache rebuilt: {SEED} ({sum(1 for _ in SEED.rglob('*') if _.is_file())} files)")

    if a.clean:
        for n in drop:
            (CACHE_DIR / n).unlink()
        for d in sorted((p for p in CACHE_DIR.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
        (CACHE_DIR / "meta.json").write_text(json.dumps(pruned, indent=2), "utf-8")
        print(f"data/cache cleaned: removed {len(drop)} throwaway files")
    else:
        print("(dry run: data/cache not touched; add --clean to delete the throwaway files)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
