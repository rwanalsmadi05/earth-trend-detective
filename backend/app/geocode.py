"""A readable place name for any point on Earth.

Order: (1) a built-in gazetteer place within 10 km (a click next to Azraq is "Azraq"; no network);
       (2) the on-disk cache (every new place is geocoded once);
       (3) OpenStreetMap Nominatim reverse geocoding, at most one request per second, with an identifying
           User-Agent that carries no personal data, and a short timeout;
       (4) the coordinates themselves, so a slow or failing geocoder never blocks a case.
Only the clicked coordinates are sent to Nominatim."""
import json
import threading
import time

from . import cache, gazetteer
from .http import get

URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "EarthTrendDetective/0.1 (NASA Space Apps 2026 project; non-commercial)"   # identifies the app, no personal data
MIN_INTERVAL_S = 1.1        # Nominatim usage policy: max 1 request per second
TIMEOUT_S = 6
GAZETTEER_KM = 10.0
LOCALITY_KEYS = ("city", "town", "village", "hamlet", "suburb", "city_district", "municipality", "county",
                 "state_district", "state", "region", "island", "archipelago")

_lock = threading.Lock()
_last_call = 0.0


def coords_label(lat: float, lon: float) -> str:
    return f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"


def _cache_file(lat: float, lon: float):
    return cache.CACHE_DIR / "geocode" / f"{lat:.2f}_{lon:.2f}.json"


def parse(js: dict, lat: float, lon: float) -> dict:
    """Nominatim reverse JSON -> {"name": "Locality, Country", "name_ar": ...}. The locality comes first, so UIs that
    show only the part before the first comma still get a readable place."""
    addr = js.get("address") or {}
    locality = next((addr[k] for k in LOCALITY_KEYS if addr.get(k)), None)
    country = addr.get("country")
    name = (f"{locality}, {country}" if locality and country else locality or country or js.get("name")
            or coords_label(lat, lon))
    details = js.get("namedetails") or {}
    return {"name": name, "name_ar": details.get("name:ar") or "", "source": "nominatim"}


def name_for(lat: float, lon: float) -> dict:
    """{"name", "name_ar", "source": "gazetteer"|"cache"|"nominatim"|"coordinates"}"""
    near = gazetteer.nearest_place(lat, lon, GAZETTEER_KM)
    if near:
        return {"name": near["name"], "name_ar": near["name_ar"], "source": "gazetteer"}
    f = _cache_file(lat, lon)
    if f.exists():
        try:
            return {**json.loads(f.read_text("utf-8")), "source": "cache"}
        except Exception:  # noqa: BLE001
            pass
    global _last_call
    try:
        with _lock:                                   # one request per second, even with parallel cases
            wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
            js = get(URL, {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1,
                           "namedetails": 1, "accept-language": "en"},
                     retries=1, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    except Exception:  # noqa: BLE001  (offline / rate-limited / slow): never block the case, and do not cache a failure
        return {"name": coords_label(lat, lon), "name_ar": "", "source": "coordinates"}
    res = parse(js, lat, lon) if not js.get("error") else {"name": coords_label(lat, lon), "name_ar": "", "source": "coordinates"}
    f.parent.mkdir(parents=True, exist_ok=True)       # "Unable to geocode" (open sea, poles) is a definitive answer: cache it too
    f.write_text(json.dumps({"name": res["name"], "name_ar": res["name_ar"]}, ensure_ascii=False), "utf-8")
    return res
