from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:  # secrets live in backend/.env or the project-root .env (both git-ignored); never printed or logged
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")
except ImportError:  # python-dotenv is optional; real environment variables still work
    pass
CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR = 1981
LAST_FULL_YEAR = date.today().year - 1

# POWER monthly parameters fetched per point (the variable catalog lives in variables.py).
POWER_PARAMS = ["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN"]

# Demo cases. bbox = (south, west, north, east) for the satellite photos.
CASES = {
    "azraq": {"name": "Azraq", "name_ar": "الأزرق", "lat": 31.88, "lon": 36.83, "bbox": (31.4, 36.3, 32.4, 37.4)},
    "irbid": {"name": "Irbid", "name_ar": "إربد", "lat": 32.55, "lon": 35.85, "bbox": (32.2, 35.5, 32.9, 36.2)},
    "deadsea": {"name": "Dead Sea", "name_ar": "البحر الميت", "lat": 31.50, "lon": 35.47, "bbox": (31.0, 35.1, 32.0, 35.9)},
}
# Default "where" grid (29-34 N, 34-40 E)
GRID_BBOX = (29.0, 34.0, 34.0, 40.0)
GRID_STEP = 0.5
