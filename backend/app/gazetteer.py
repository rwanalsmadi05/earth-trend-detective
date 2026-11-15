"""Built-in gazetteer (English, Arabic, lat, lon). Nominatim fallback only if a place is missing."""
import re
from .http import get

PLACES = [
    ("Azraq", "الأزرق", 31.88, 36.83), ("Amman", "عمان", 31.95, 35.93), ("Irbid", "إربد", 32.55, 35.85),
    ("Zarqa", "الزرقاء", 32.07, 36.09), ("Aqaba", "العقبة", 29.53, 35.01), ("Madaba", "مادبا", 31.72, 35.79),
    ("Karak", "الكرك", 31.18, 35.70), ("Tafilah", "الطفيلة", 30.84, 35.60), ("Maan", "معان", 30.19, 35.73),
    ("Jerash", "جرش", 32.27, 35.90), ("Ajloun", "عجلون", 32.33, 35.75), ("Mafraq", "المفرق", 32.34, 36.20),
    ("Salt", "السلط", 32.04, 35.73), ("Petra", "البتراء", 30.33, 35.44), ("Wadi Rum", "وادي رم", 29.57, 35.42),
    ("Dead Sea", "البحر الميت", 31.50, 35.47), ("Jordan Valley", "غور الأردن", 32.00, 35.55),
    ("Ramtha", "الرمثا", 32.56, 36.01), ("Jerusalem", "القدس", 31.77, 35.21), ("Damascus", "دمشق", 33.51, 36.29),
    ("Baghdad", "بغداد", 33.31, 44.37), ("Cairo", "القاهرة", 30.04, 31.24), ("Riyadh", "الرياض", 24.71, 46.68),
    ("Beirut", "بيروت", 33.89, 35.50),
]


_AR_DIAC = re.compile(r"[ً-ْـ]")


def norm(text: str) -> str:
    """Lower-case + Arabic normalisation (diacritics, alef/yaa/taa-marbuta variants) so إربد == اربد, الأزرق ~ ازرق."""
    t = _AR_DIAC.sub("", text.lower())
    return t.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


def lookup(query: str, nominatim: bool = True):
    """Place from a name or a whole question. Built-in list first; Nominatim only if allowed and nothing matched."""
    q = norm(query.strip())
    for en, ar, lat, lon in PLACES:
        if q in (en.lower(), norm(ar)):
            return {"name": en, "name_ar": ar, "lat": lat, "lon": lon, "source": "gazetteer"}
    for en, ar, lat, lon in sorted(PLACES, key=lambda p: -len(p[0])):   # a known name inside a question
        if re.search(rf"(?<![a-z]){re.escape(en.lower())}(?![a-z])", q) or norm(ar) in q:
            return {"name": en, "name_ar": ar, "lat": lat, "lon": lon, "source": "gazetteer"}
    if nominatim:
        try:
            res = get("https://nominatim.openstreetmap.org/search", {"q": query, "format": "json", "limit": 1})
            if res:
                return {"name": res[0]["display_name"], "name_ar": None, "lat": float(res[0]["lat"]),
                        "lon": float(res[0]["lon"]), "source": "nominatim"}
        except Exception:
            pass
    return None


def nearest_place(lat: float, lon: float, max_km: float = 10.0):
    """The built-in place closest to a point, if within max_km (so a click next to Azraq is simply 'Azraq')."""
    import math
    best, bd = None, 1e9
    for en, ar, la, lo in PLACES:
        d = 111.0 * math.hypot(la - lat, (lo - lon) * math.cos(math.radians((la + lat) / 2)))
        if d < bd:
            best, bd = {"name": en, "name_ar": ar, "lat": la, "lon": lo, "source": "gazetteer", "km": round(d, 1)}, d
    return best if best and bd <= max_km else None
