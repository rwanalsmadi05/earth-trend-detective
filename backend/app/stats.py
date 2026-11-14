"""Statistics core. Everything the UI calls a verdict comes from here, never from the LLM.

Method per series:
 1. remove seasonality  : subtract each calendar month's long-term mean (monthly anomalies)
 2. trend test          : Mann-Kendall with Hamed-Rao autocorrelation correction (pymannkendall), run on the
                          MONTHLY anomalies with the lag capped at 12 (one seasonal cycle); annual means are display-only
 3. how much            : Sen's slope (Theil-Sen) on the ANNUAL means (the plotted series), per decade, total over
                          the record and % vs first-decade baseline. Monthly Sen is not used for magnitude: on
                          zero-inflated variables (Azraq: 34% of months have no rain) the many near-zero dry-season
                          pairs drag the median toward 0 (rain: -0.006 vs -0.021 per decade on annual means)
 4. verdict             : CONFIRMED if p < 0.05 else NOT PROVEN
 5. grid maps           : Benjamini-Hochberg FDR across cells
 6. chain of evidence   : lagged cross-correlation of anomalies, lag 0-6 months (correlation only)
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy import stats as sps

ALPHA = 0.05
BORDERLINE_P = 0.01   # CONFIRMED verdicts with BORDERLINE_P <= p < ALPHA are flagged borderline
HR_MAX_LAG = 12       # Hamed-Rao lag cap (months)
MIN_N = 10        # minimum valid monthly values (or annual values for annual series)
MIN_ANNUAL = 8    # minimum plotted annual points needed for Sen's slope / total change


def _t_years(index: pd.Index) -> np.ndarray:
    """Time axis in decimal years. Monthly DatetimeIndex -> year + (month-1)/12; annual int index -> year."""
    if isinstance(index, pd.DatetimeIndex):
        return (index.year + (index.month - 1) / 12.0).to_numpy(dtype=float)
    return np.asarray(index, dtype=float)


def deseasonalize(s: pd.Series) -> pd.Series:
    """Monthly anomalies: value minus the long-term mean of its calendar month."""
    return s - s.groupby(s.index.month).transform("mean")


def sig(x: float, digits: int = 4) -> float:
    """Round to significant digits (keeps tiny p-values and slopes readable). Never hides NaN/inf."""
    if x is None or not np.isfinite(x):
        raise ValueError(f"non-finite statistic: {x}")
    return 0.0 if x == 0 else float(f"{x:.{digits}g}")


class TooShort(ValueError):
    """Series has too few valid values for a trend test."""


@dataclass
class TrendResult:
    n: int            # valid observations used (monthly anomalies; annual counts: years)
    n_tested: int     # values the trend test ran on (same as n)
    tau: float
    p: float
    sen_per_decade: float
    total_change: float
    pct_change: float
    baseline: float
    verdict: str
    direction: str
    method: str       # which test produced tau/p
    reason: str | None  # set when the test could not be computed (verdict is then NOT PROVEN)
    borderline: bool  # significant, but only just: BORDERLINE_P <= p < alpha
    first_year: int
    last_year: int
    annual: list      # [{"year": int, "value": float}] the exact series the test ran on


P_FLOOR = 1e-300  # float limit: for |z| > ~37 the true p underflows to 0; report the floor, never exactly 0

# Hamed-Rao first; if its corrected variance is invalid (NaN) fall back to trend-free pre-whitening.
# Yue-Wang was measured at ~44% false positives on noise (tools/fp_experiment.py), so it is NOT used.
# Hamed-Rao's default (n/3 lags) added noise on monthly anomalies (20% false positives at AR(1) phi=0.6);
# capping at 12 lags measured ~9% (tools/fp_experiment.py).
_TESTS = (("hamed-rao", mk.hamed_rao_modification_test),
          ("trend-free pre-whitening", mk.trend_free_pre_whitening_modification_test))


def mann_kendall(vals: np.ndarray):
    """Returns (tau, p, method, reason). If no test yields a finite result: p=1.0, reason says why."""
    notes = []
    i = np.arange(len(vals), dtype=float)
    slope, intercept = sps.theilslopes(vals, i)[:2]
    if np.std(vals - (slope * i + intercept)) <= 1e-9 * max(float(np.std(vals)), 1e-12):
        # exact line: autocorrelation-corrected tests are undefined (TFPW would return tau=0, p=1 -- a finite
        # but meaningless answer), so say so instead of reporting one.
        return float(mk.original_test(vals).Tau), 1.0, "none", (
            "no variability around the trend line, so the autocorrelation-corrected test is undefined. Not proven.")
    lag = max(1, min(HR_MAX_LAG, len(vals) // 4))
    for name, fn in _TESTS:
        try:
            r = fn(vals, lag=lag) if name == "hamed-rao" else fn(vals)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{name} raised {type(e).__name__}")
            continue
        if np.isfinite(r.z) and np.isfinite(r.Tau):
            return float(r.Tau), max(float(2 * sps.norm.sf(abs(r.z))), P_FLOOR), name, None
        notes.append(f"{name} gave a non-finite statistic")
    tau = float(mk.original_test(vals).Tau)  # descriptive only; no p-value is claimed
    return tau, 1.0, "none", "; ".join(notes) + ". Trend test could not be computed, so it is not proven."


def trend(raw: pd.Series, seasonal: bool = True, alpha: float = ALPHA) -> TrendResult:
    """Trend analysis of one series.
    Monthly series (DatetimeIndex, seasonal=True): de-seasonalise; the significance test (Mann-Kendall, Hamed-Rao,
    12-lag cap) runs on the MONTHLY anomalies. "How much" (Sen's slope, total change) comes from the annual means
    (years with >= 6 valid months) -- the same series that is plotted, so every number matches the chart.
    Annual series (int index, seasonal=False): test and slope both use the annual values."""
    raw = raw.astype(float)
    if seasonal:
        anom = deseasonalize(raw).dropna()
        g = anom.groupby(anom.index.year)
        m, c = g.mean(), g.count()
        annual = m[c >= 6]
    else:
        anom = (raw - raw.mean()).dropna()
        annual = anom
    if len(anom) < MIN_N or len(annual) < MIN_ANNUAL:
        raise TooShort(f"need >= {MIN_N} valid values and >= {MIN_ANNUAL} annual points, got {len(anom)} / {len(annual)}")
    vals = anom.to_numpy()
    years = np.asarray(annual.index, dtype=float)

    tau, p, method, reason = mann_kendall(vals)
    sen_per_year = float(sps.theilslopes(annual.to_numpy(), years)[0])
    total = sen_per_year * (years[-1] - years[0] + 1)  # change across the whole record (each year is a 1-year bin)

    valid = raw.dropna()
    tv = _t_years(valid.index)
    baseline = float(valid[tv < tv[0] + 10].mean())
    pct = total / baseline * 100.0 if abs(baseline) > 1e-9 else 0.0

    confirmed = reason is None and p < alpha
    return TrendResult(
        n=int(len(vals)), n_tested=int(len(vals)), tau=sig(tau, 3), p=sig(p), sen_per_decade=sig(sen_per_year * 10),
        total_change=sig(total), pct_change=sig(pct, 3), baseline=baseline,
        verdict="CONFIRMED" if confirmed else "NOT PROVEN",
        direction="up" if sen_per_year >= 0 else "down", method=method, reason=reason,
        borderline=bool(confirmed and p >= BORDERLINE_P),
        first_year=int(years[0]), last_year=int(years[-1]),
        annual=[{"year": int(y), "value": sig(v)} for y, v in zip(annual.index, annual.to_numpy())],
    )


def benjamini_hochberg(pvals, alpha: float = ALPHA):
    """BH FDR. NaN p-values are treated as untested (never rejected).
    Returns (reject: bool array, p_adjusted: float array)."""
    p = np.asarray(pvals, dtype=float)
    reject = np.zeros(p.shape, dtype=bool)
    adj = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return reject, adj
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / (np.arange(m) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]  # enforce monotonicity
    ranked = np.clip(ranked, 0, 1)
    a = np.empty(m)
    a[order] = ranked
    adj[ok] = a
    reject[ok] = a <= alpha
    return reject, adj


def lagged_xcorr(x: pd.Series, y: pd.Series, max_lag: int = 6):
    """Pearson r between x(t) and y(t+lag) for lag 0..max_lag (x leads y by `lag` months).
    Inputs are monthly anomaly series. Returns [(lag, r)]; lags with <24 overlapping points are skipped."""
    out = []
    for lag in range(max_lag + 1):
        yy = y.copy()
        yy.index = yy.index - pd.DateOffset(months=lag)  # y(t+lag) aligned onto t
        j = pd.concat([x, yy], axis=1, join="inner").dropna()
        if len(j) >= 24:
            out.append((lag, float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1])))
    return out


def chain_of_evidence(anoms: dict, min_abs_r: float = 0.3, max_edges: int = 3, max_lag: int = 6):
    """Which variable moved first? For every pair keep the strongest lagged correlation (either direction).
    This is CORRELATION, not causation. `anoms` maps variable id -> monthly anomaly series;
    at lag 0 the earlier key in dict order is reported as `from`."""
    keys = list(anoms)
    edges = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            cands = []
            for lag, r in lagged_xcorr(anoms[a], anoms[b], max_lag):
                cands.append((abs(r), a, b, lag, r))
            for lag, r in lagged_xcorr(anoms[b], anoms[a], max_lag):
                if lag > 0:
                    cands.append((abs(r), b, a, lag, r))
            if cands:
                _, f, t_, lag, r = max(cands, key=lambda c: (round(c[0], 6), -c[3]))
                if abs(r) >= min_abs_r:
                    edges.append({"from": f, "to": t_, "lag_months": int(lag), "r": round(r, 3)})
    edges.sort(key=lambda e: -abs(e["r"]))
    return edges[:max_edges]
