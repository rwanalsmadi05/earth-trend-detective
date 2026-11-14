"""NASA POWER monthly + daily point data (no auth)."""
import numpy as np
import pandas as pd
from ..http import get
from ..config import POWER_PARAMS, START_YEAR, LAST_FULL_YEAR
from .. import cache

MONTHLY = "https://power.larc.nasa.gov/api/temporal/monthly/point"
DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"


def monthly_url(lat, lon, start=START_YEAR, end=LAST_FULL_YEAR):
    return (f"{MONTHLY}?parameters={','.join(POWER_PARAMS)}&community=AG&latitude={lat}&longitude={lon}"
            f"&start={start}&end={end}&format=JSON")


def _fetch_monthly(lat, lon, start, end) -> pd.DataFrame:
    js = get(MONTHLY, {"parameters": ",".join(POWER_PARAMS), "community": "AG", "latitude": lat,
                       "longitude": lon, "start": start, "end": end, "format": "JSON"})
    data = js["properties"]["parameter"]
    rows = {}
    for p, series in data.items():
        for ym, v in series.items():
            if ym.endswith("13"):  # annual "13th month"
                continue
            rows.setdefault(ym, {})[p] = np.nan if v == -999 else v  # fill value
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index = pd.to_datetime(df.index, format="%Y%m")
    df.index.name = "date"
    return df.astype(float)


def monthly(lat, lon, start=START_YEAR, end=LAST_FULL_YEAR, refresh=False):
    """Returns (DataFrame, status, cache_key)."""
    key = f"power_monthly_{lat:.2f}_{lon:.2f}_{start}_{end}"
    df, st = cache.cached_df(key, lambda: _fetch_monthly(lat, lon, start, end), refresh,
                             {"url": monthly_url(lat, lon, start, end)})
    return df, st, key


def _fetch_daily(lat, lon, start, end) -> pd.DataFrame:
    js = get(DAILY, {"parameters": "T2M_MAX", "community": "AG", "latitude": lat, "longitude": lon,
                     "start": f"{start}0101", "end": f"{end}1231", "format": "JSON"})
    s = pd.Series(js["properties"]["parameter"]["T2M_MAX"])
    s.index = pd.to_datetime(s.index, format="%Y%m%d")
    return s.where(s != -999).rename("T2M_MAX").to_frame()


def hot_days_per_year(lat, lon, threshold=35.0, start=START_YEAR, end=LAST_FULL_YEAR, refresh=False):
    key = f"power_daily_t2mmax_{lat:.2f}_{lon:.2f}_{start}_{end}"
    df, st = cache.cached_df(key, lambda: _fetch_daily(lat, lon, start, end), refresh,
                             {"url": f"{DAILY}?parameters=T2M_MAX&latitude={lat}&longitude={lon}"})
    counts = (df["T2M_MAX"] > threshold).groupby(df.index.year).sum().astype(int)
    return counts.rename("hot_days"), st
