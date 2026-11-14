"""Which real NASA image each witness shows (early vs recent). Layer ids are validated against the GIBS
capabilities document (sources/gibs.py: covers()), nothing here is trusted blindly.

  variable            layer (from the capabilities document)                      window    month
  T2M                 MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day                 region    month closest to the annual-mean T2M (POWER climatology)
  T2M_MAX, HOT_DAYS   MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day                 region    hottest month by mean T2M_MAX (POWER climatology)
  PRECTOTCORR         MODIS_Terra_CorrectedReflectance_TrueColor (oasis window)    oasis   March (end of the wet season; design choice)
  GWETROOT            SMAP_L4_Analyzed_Root_Zone_Soil_Moisture (starts 2015)       region    March, early = 2016
  GWETTOP             SMAP_L4_Analyzed_Surface_Soil_Moisture   (starts 2015)       region    March, early = 2016
  NDVI                MODIS_Terra_L3_NDVI_Monthly                                  region    March (Apr-2025 is missing from the layer)
  RH2M, ALLSKY        true color, regional                                         region    hottest month
Data layers are drawn over a true-color base with a coastline overlay, so no-data/ocean pixels are not black.
"""
from dataclasses import dataclass
from .config import LAST_FULL_YEAR
from .sources import gibs

BASE = "MODIS_Terra_CorrectedReflectance_TrueColor"
LST = "MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day"
NDVI_L = "MODIS_Terra_L3_NDVI_Monthly"
SMAP_ROOT = "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture"
SMAP_TOP = "SMAP_L4_Analyzed_Surface_Soil_Moisture"
OVERLAY = "Coastlines_15m"

EARLY_YEAR = 2001            # first full MODIS year; SMAP starts 2015 so it uses 2016
REGION = (2.5, 3.0)          # half-height / half-width in degrees: a ~5 x 6 degree window around the place
OASIS = (0.5, 0.6)           # ~1 x 1.2 degree window: close enough to see the oasis, wide enough for 250 m MODIS to look sharp

# variable -> (data layer or None for plain true color, window, month rule, early_year)
SPECS = {
    "T2M": (LST, "region", "annual_mean_T2M", EARLY_YEAR),
    "T2M_MAX": (LST, "region", "hottest", EARLY_YEAR),
    "HOT_DAYS": (LST, "region", "hottest", EARLY_YEAR),
    "PRECTOTCORR": (None, "oasis", 3, EARLY_YEAR),
    "GWETROOT": (SMAP_ROOT, "region", 3, 2016),
    "GWETTOP": (SMAP_TOP, "region", 3, 2016),
    "NDVI": (NDVI_L, "region", 3, EARLY_YEAR),
    "RH2M": (None, "region", "hottest", EARLY_YEAR),
    "ALLSKY_SFC_SW_DWN": (None, "region", "hottest", EARLY_YEAR),
}


@dataclass
class ImagePlan:
    variable: str
    tag: str
    layers_before: list   # bottom -> top, for the early date
    layers_after: list
    bbox: tuple           # south, west, north, east
    before: str
    after: str
    data_layer: str


def _month(rule, clim):
    if isinstance(rule, int):
        return rule
    if rule == "hottest":
        return int(clim["T2M_MAX"].groupby(clim.index.month).mean().idxmax())
    m = clim["T2M"].groupby(clim.index.month).mean()
    return int((m - clim["T2M"].mean()).abs().idxmin())          # month closest to the annual mean


def _day(layer, year, month):
    per = gibs.layers()[layer]["ranges"][0][2] or "P1D"
    return f"{year}-{month:02d}-{'01' if per.endswith('M') else '15'}"


def plan(variable: str, lat: float, lon: float, clim) -> ImagePlan:
    """Build + validate the early/recent image plan. Raises ValueError if the capabilities document
    does not list a layer/date (never silently picks something else)."""
    layer, window, rule, early = SPECS[variable]
    month = _month(rule, clim)
    dlat, dlon = REGION if window == "region" else OASIS
    data = layer or BASE
    before, after = _day(data, early, month), _day(data, LAST_FULL_YEAR, month)

    def layers_for(day):
        if layer is None:                       # plain true color: the base IS the data and must be listed
            required = [BASE]
        else:                                   # data layer + overlay are required; the true-color backdrop is optional
            required = [layer] + ([OVERLAY] if window == "region" else [])
        for lyr in required:
            if not gibs.covers(lyr, day):
                raise ValueError(f"GIBS capabilities do not list {lyr} for {day}")
        backdrop = [BASE] if (layer is not None and gibs.covers(BASE, day)) else []
        return backdrop + required if layer is not None else required

    return ImagePlan(variable, f"{data}_m{month:02d}_{window}", layers_for(before), layers_for(after),
                     (lat - dlat, lon - dlon, lat + dlat, lon + dlon), before, after, data)
