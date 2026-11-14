"""NASA Worldview snapshots (GIBS). Layer names and valid dates are read from the GIBS capabilities document."""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from ..http import get
from .. import cache

WVS = "https://wvs.earthdata.nasa.gov/api/v1/snapshot"
CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml"
_NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
_LAYERS: dict | None = None


def _caps_path():
    p = cache.blob_path("gibs_capabilities.xml")
    if not p.exists():
        cache.save_blob("gibs_capabilities.xml", get(CAPS, binary=True), {"url": CAPS})
    return p


def layers() -> dict:
    """{layer id: {"formats": [...], "ranges": [(start, end, period)]}} parsed from the (cached) capabilities doc."""
    global _LAYERS
    if _LAYERS is None:
        out = {}
        for L in ET.parse(_caps_path()).getroot().iter("{http://www.opengis.net/wmts/1.0}Layer"):
            lid = L.find("ows:Identifier", _NS).text
            ranges = []
            for v in L.findall("w:Dimension/w:Value", _NS):
                a, b, per = (v.text.split("/") + [None])[:3]
                ranges.append((date.fromisoformat(a[:10]), date.fromisoformat(b[:10]), per))
            out[lid] = {"formats": [f.text for f in L.findall("w:Format", _NS)], "ranges": ranges}
        _LAYERS = out
    return _LAYERS


def find_layers(patterns=("TrueColor", "NDVI", "Land_Surface_Temp", "Soil_Moisture")):
    """{pattern: [layer ids]} for browsing the capabilities document."""
    ids = sorted(layers())
    return {pat: [i for i in ids if pat.lower() in i.lower()] for pat in patterns}


def covers(layer: str, day: str) -> bool:
    """True if the capabilities document lists `day` as a valid time for `layer` (inside a range AND on its period grid)."""
    info = layers().get(layer)
    if not info:
        return False
    if not info["ranges"]:          # static overlays (coastlines, borders) have no time dimension
        return True
    d = datetime.strptime(day, "%Y-%m-%d").date()
    for start, end, per in info["ranges"]:
        if not (start <= d <= end):
            continue
        m = re.fullmatch(r"P(\d+)([DM])", per or "P1D")
        n, unit = int(m.group(1)), m.group(2)
        if unit == "D":
            if (d - start).days % n == 0:
                return True
        elif d.day == start.day and ((d.year - start.year) * 12 + d.month - start.month) % n == 0:
            return True
    return False


def snapshot_url(bbox, day, layer_list, w=600, h=500):
    """Worldview snapshot URL. `layer_list` is bottom -> top (first layer is drawn first)."""
    if isinstance(layer_list, str):
        layer_list = [layer_list]
    s, we, n, e = bbox
    return (f"{WVS}?REQUEST=GetSnapshot&TIME={day}&BBOX={s:.4f},{we:.4f},{n:.4f},{e:.4f}&CRS=EPSG:4326"
            f"&LAYERS={','.join(layer_list)}&FORMAT=image/jpeg&WIDTH={w}&HEIGHT={h}")


def image_key(case_id: str, tag: str, day: str) -> str:
    return f"img_{case_id}_{tag}_{day}.jpg"


def snapshot(case_id, tag, bbox, day, layer_list, refresh=False):
    """Fetch + cache one snapshot. Refuses layers/dates the capabilities document does not list."""
    if isinstance(layer_list, str):
        layer_list = [layer_list]
    for lyr in layer_list:
        if not covers(lyr, day):
            raise ValueError(f"GIBS capabilities do not list {lyr} for {day}")
    p = cache.blob_path(image_key(case_id, tag, day))
    if p.exists() and not refresh:
        return p, "cached"
    url = snapshot_url(bbox, day, layer_list)
    data = get(url, binary=True)
    if len(data) < 5000 or data[:3] != b"\xff\xd8\xff":
        raise RuntimeError(f"snapshot is not a usable JPEG ({len(data)} bytes)")
    cache.save_blob(p.name, data, {"url": url, "layers": layer_list, "date": day})
    return p, "fresh"
