import numpy as np
import pandas as pd
import pymannkendall as mk
from statsmodels.stats.multitest import multipletests

from app import stats

IDX = pd.date_range("1981-01-01", periods=45 * 12, freq="MS")
YEARS = np.arange(len(IDX)) / 12.0


def season(amp=8.0):
    return amp * np.sin(2 * np.pi * (IDX.month - 1) / 12)


def series(slope_per_year=0.0, noise=0.5, seed=0, amp=8.0, phi=0.0):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, noise, len(IDX))
    if phi:
        for i in range(1, len(e)):
            e[i] += phi * e[i - 1]
    return pd.Series(10 + season(amp) + slope_per_year * YEARS + e, index=IDX)


def test_known_positive_trend_is_recovered():
    r = stats.trend(series(0.03))                       # +0.3 per decade, strong seasonality on top
    assert r.verdict == "CONFIRMED" and r.direction == "up"
    assert abs(r.sen_per_decade - 0.30) < 0.05
    assert abs(r.total_change - 0.03 * (YEARS[-1] - YEARS[0])) < 0.15
    assert r.p < 0.001 and r.tau > 0.3


def test_known_negative_trend_is_recovered():
    r = stats.trend(series(-0.02, seed=3))
    assert r.verdict == "CONFIRMED" and r.direction == "down"
    assert abs(r.sen_per_decade + 0.20) < 0.05


def test_series_with_no_trend_is_not_proven():
    # deterministic zero-trend series (seasonality + alternating +/-): no seed to cherry-pick.
    # The statistical "pure noise" behaviour is covered by the false-positive-rate tests below.
    s = pd.Series(10 + season() + 0.5 * (-1.0) ** np.arange(len(IDX)), index=IDX)
    r = stats.trend(s)
    assert r.verdict == "NOT PROVEN" and r.p >= 0.05
    assert abs(r.sen_per_decade) < 0.05


def test_median_slope_of_noise_is_zero():
    slopes = [stats.trend(series(0.0, seed=s)).sen_per_decade for s in range(400, 440)]
    assert abs(float(np.median(slopes))) < 0.02


def test_false_positive_rate_white_noise_is_near_nominal():
    fp = sum(stats.trend(series(0.0, seed=s)).verdict == "CONFIRMED" for s in range(100, 200))
    assert fp <= 12, f"false positive rate {fp}% far above the nominal 5%"


def test_false_positive_rate_autocorrelated_noise_is_controlled():
    # Hamed-Rao is there precisely for this: AR(1) noise must not produce a flood of fake trends
    fp = sum(stats.trend(series(0.0, noise=0.4, seed=s, phi=0.6)).verdict == "CONFIRMED" for s in range(300, 380))
    assert fp / 80 <= 0.15, f"autocorrelated false positive rate {fp / 80:.0%}"


def test_pure_seasonal_cycle_gives_zero_anomalies_and_no_trend():
    s = pd.Series(10 + season(), index=IDX)
    an = stats.deseasonalize(s)
    assert np.allclose(an, 0, atol=1e-9)
    assert (an.groupby(an.index.month).mean().abs() < 1e-9).all()


def test_seasonality_does_not_masquerade_as_trend_when_record_starts_mid_year():
    s = series(0.0, seed=5, noise=0.3).iloc[5:5 + 30 * 12 + 4]   # starts in June, ends mid-cycle
    assert stats.trend(s).verdict == "NOT PROVEN"


def test_sen_slope_matches_pymannkendall_on_the_annual_means():
    r = stats.trend(series(0.02, seed=7))
    ann = np.array([a["value"] for a in r.annual])
    theirs = mk.sens_slope(ann).slope * 10                # per year -> per decade
    assert abs(r.sen_per_decade - theirs) < 0.01


def test_total_change_and_slope_match_the_plotted_series_for_every_variable_shape():
    for sl, seed in [(0.03, 0), (-0.02, 3), (0.0, 5)]:
        r = stats.trend(series(sl, seed=seed))
        yrs = np.array([a["year"] for a in r.annual], dtype=float)
        v = np.array([a["value"] for a in r.annual])
        sen = float(stats.sps.theilslopes(v, yrs)[0])
        assert abs(r.sen_per_decade - sen * 10) < 1e-3
        assert abs(r.total_change - sen * (yrs[-1] - yrs[0] + 1)) < 5e-3


def test_zero_inflated_rain_magnitude_is_not_shrunk_toward_zero():
    # Azraq-like: ~35% of months have exactly zero rain (summer), wet season declines 0.4 mm/day over the record.
    rng = np.random.default_rng(21)
    wet = np.isin(IDX.month, [11, 12, 1, 2, 3, 4])
    decline = -0.4 * YEARS / YEARS[-1]
    rain = np.where(wet, np.clip(1.0 + decline + rng.normal(0, 0.25, len(IDX)), 0, None), 0.0)
    r = stats.trend(pd.Series(rain, index=IDX))
    true_per_decade = (-0.4 / YEARS[-1] * 10) * wet.mean()     # annual-mean rain falls by the wet-season share of it
    assert r.verdict == "CONFIRMED" and r.direction == "down"
    assert abs(r.sen_per_decade - true_per_decade) < 0.02, (r.sen_per_decade, true_per_decade)
    # and the monthly-anomaly Sen (what we no longer report) would have understated it
    an = stats.deseasonalize(pd.Series(rain, index=IDX))
    monthly_sen = stats.sps.theilslopes(an.to_numpy(), stats._t_years(an.index))[0] * 10
    assert abs(monthly_sen) < abs(r.sen_per_decade)


def test_leading_gap_like_solar_radiation_is_handled():
    s = series(0.02, seed=9)
    s.iloc[:36] = np.nan                                  # POWER solar has no data 1981-83
    r = stats.trend(s)
    assert r.first_year == 1984 and r.n == len(s) - 36
    assert abs(r.sen_per_decade - 0.2) < 0.06


def test_pct_change_is_relative_to_first_decade_baseline():
    s = pd.Series(100 + 0.5 * YEARS, index=IDX)            # exact line, no noise
    r = stats.trend(s)
    base = s[s.index.year < 1991].mean()
    assert abs(r.baseline - base) < 0.01
    assert abs(r.total_change - 0.5 * (YEARS[-1] - YEARS[0])) < 0.05
    assert abs(r.pct_change - r.total_change / base * 100) < 0.1


def test_annual_count_series_without_seasonality():
    years = np.arange(1981, 2026)
    s = pd.Series(80 + 1.0 * (years - 1981) + np.random.default_rng(2).normal(0, 5, len(years)), index=years)
    r = stats.trend(s, seasonal=False)
    assert r.verdict == "CONFIRMED" and abs(r.sen_per_decade - 10) < 2 and len(r.annual) == 45


def test_too_short_series_raises():
    try:
        stats.trend(series(0.1).iloc[:8])
    except stats.TooShort:
        return
    raise AssertionError("expected TooShort")


# ---- regressions for bugs found on real Azraq data ---------------------------------------------
def test_exact_line_vector_is_not_proven_with_a_reason_not_a_silent_tau0_p1():
    # exact line: Hamed-Rao -> NaN and trend-free pre-whitening -> tau=0, p=1 (finite but meaningless).
    # Rule: if no valid corrected test exists, verdict is NOT PROVEN with an explicit reason.
    tau, p, method, reason = stats.mann_kendall(0.5 * np.arange(45.0))
    assert method == "none" and p == 1.0 and reason and "undefined" in reason
    assert tau > 0.99                                # descriptive tau still reflects the exact trend


def test_noiseless_monthly_line_is_confirmed_with_finite_p():
    # on monthly data the anomalies of a perfect line are year-wise steps (not an exact line): testable
    r = stats.trend(pd.Series(100 + 0.5 * YEARS, index=IDX))
    assert r.verdict == "CONFIRMED" and r.reason is None and np.isfinite(r.p) and r.p > 0


def test_tiny_noise_around_a_strong_line_is_confirmed():
    rng = np.random.default_rng(11)
    r = stats.trend(pd.Series(100 + 0.5 * YEARS + rng.normal(0, 0.05, len(IDX)), index=IDX))
    assert r.verdict == "CONFIRMED" and r.reason is None and np.isfinite(r.p)


def test_strong_annual_count_trend_is_confirmed_like_azraq_hot_days():
    # real Azraq hot-days/yr (45 values): tau 0.49, plain MK p=1.8e-6, Hamed-Rao default lags gave NaN
    from app import cache
    h = cache.load_df("power_daily_t2mmax_31.88_36.83_1981_2025")
    if h is None:
        return
    counts = (h.T2M_MAX > 35).groupby(h.index.year).sum().astype(float)
    r = stats.trend(counts, seasonal=False)
    assert np.isfinite(r.p) and r.p < 0.001 and r.verdict == "CONFIRMED" and r.direction == "up"


def test_tiny_p_values_do_not_underflow_to_zero():
    r = stats.trend(series(0.5, noise=0.2, seed=1))          # enormous trend
    assert 0 < r.p < 1e-10


def test_nonfinite_stat_is_an_error_not_a_silent_zero():
    try:
        stats.sig(float("nan"))
    except ValueError:
        return
    raise AssertionError("sig() must not hide NaN")


def test_annual_means_of_anomalies_shape():
    r = stats.trend(series(0.03))
    assert [a["year"] for a in r.annual] == list(range(1981, 2026))
    assert abs(np.mean([a["value"] for a in r.annual])) < 0.2


# ---- Benjamini-Hochberg -------------------------------------------------------------------------
def test_bh_matches_statsmodels():
    rng = np.random.default_rng(0)
    p = np.concatenate([rng.uniform(0, 0.002, 15), rng.uniform(0, 1, 85)])
    rej, adj = stats.benjamini_hochberg(p, 0.05)
    s_rej, s_adj, *_ = multipletests(p, alpha=0.05, method="fdr_bh")
    assert (rej == s_rej).all() and np.allclose(adj, s_adj)


def test_bh_is_stricter_than_raw_threshold_and_ignores_nan():
    p = np.array([0.001, 0.04, 0.045, 0.2, np.nan, 0.9])
    rej, adj = stats.benjamini_hochberg(p, 0.05)
    assert rej[0] and not rej[1] and not rej[2] and not rej[4]
    assert np.isnan(adj[4])
    assert (p[np.isfinite(p)] < 0.05).sum() > rej.sum()      # raw 0.05 would have kept 3, BH keeps fewer


# ---- chain of evidence --------------------------------------------------------------------------
def test_lagged_xcorr_recovers_known_lag():
    rng = np.random.default_rng(4)
    x = pd.Series(rng.normal(size=len(IDX)), index=IDX)
    y = x.shift(3) + rng.normal(0, 0.1, len(IDX))          # y follows x by 3 months
    lag, r = max(stats.lagged_xcorr(x, y), key=lambda t: abs(t[1]))
    assert lag == 3 and r > 0.9


def test_chain_orders_leader_first_and_reports_sign():
    rng = np.random.default_rng(5)
    x = pd.Series(rng.normal(size=len(IDX)), index=IDX)
    y = -x.shift(2) + rng.normal(0, 0.2, len(IDX))
    edges = stats.chain_of_evidence({"T2M": x, "GWETROOT": y})
    assert edges[0]["from"] == "T2M" and edges[0]["to"] == "GWETROOT"
    assert edges[0]["lag_months"] == 2 and edges[0]["r"] < -0.8
    # reversed dict order must still name the leader as `from`
    edges2 = stats.chain_of_evidence({"GWETROOT": y, "T2M": x})
    assert edges2[0]["from"] == "T2M"


def test_chain_drops_unrelated_pairs():
    rng = np.random.default_rng(6)
    a = pd.Series(rng.normal(size=len(IDX)), index=IDX)
    b = pd.Series(rng.normal(size=len(IDX)), index=IDX)
    assert stats.chain_of_evidence({"T2M": a, "RH2M": b}, min_abs_r=0.3) == []


def test_failed_test_is_not_proven_with_a_reason_never_a_zero_p(monkeypatch):
    class Bad:
        z = float("nan"); Tau = float("nan"); p = float("nan")
    monkeypatch.setattr(stats, "_TESTS", (("hamed-rao", lambda v: Bad()), ("trend-free pre-whitening", lambda v: Bad())))
    r = stats.trend(series(0.03))
    assert r.verdict == "NOT PROVEN" and r.method == "none" and r.reason and "not proven" in r.reason
    assert r.p == 1.0                       # "no evidence", not a fake 0.0 that looks like certainty


def test_hamed_rao_nan_falls_back_to_pre_whitening(monkeypatch):
    class Bad:
        z = float("nan"); Tau = float("nan"); p = float("nan")
    monkeypatch.setattr(stats, "_TESTS", (("hamed-rao", lambda v: Bad()), _ORIG[1]))
    r = stats.trend(series(0.03))
    assert r.method == "trend-free pre-whitening" and r.verdict == "CONFIRMED"


_ORIG = stats._TESTS


def test_test_runs_on_monthly_anomalies_but_plots_annual_means():
    r = stats.trend(series(0.03))
    assert r.n == r.n_tested == 540            # the test sees every monthly anomaly
    assert len(r.annual) == 45                 # the plotted series is the annual mean


def test_hamed_rao_lag_is_capped_at_12(monkeypatch):
    seen = {}
    real = stats._TESTS[0][1]

    def spy(v, lag=None):
        seen["lag"] = lag
        return real(v, lag=lag)
    monkeypatch.setattr(stats, "_TESTS", (("hamed-rao", spy), stats._TESTS[1]))
    stats.trend(series(0.03))
    assert seen["lag"] == 12


# ---- borderline flag ----------------------------------------------------------------------------
def _find_series_with_p(lo, hi):
    for sl in np.arange(0.0030, 0.0120, 0.0002):
        for seed in range(40):
            r = stats.trend(series(float(sl), noise=0.5, seed=seed))
            if lo <= r.p < hi:
                return r
    raise AssertionError(f"no synthetic series found with {lo} <= p < {hi}")


def test_borderline_flag_set_exactly_when_0_01_le_p_lt_0_05():
    b = _find_series_with_p(0.012, 0.045)
    assert b.verdict == "CONFIRMED" and b.borderline and 0.01 <= b.p < 0.05
    strong = stats.trend(series(0.03))
    assert strong.verdict == "CONFIRMED" and not strong.borderline and strong.p < 0.01
    none = _find_series_with_p(0.2, 1.01)
    assert none.verdict == "NOT PROVEN" and not none.borderline


def test_borderline_boundaries():
    # flag logic at the exact edges, independent of any data
    assert stats.BORDERLINE_P == 0.01 and stats.ALPHA == 0.05
