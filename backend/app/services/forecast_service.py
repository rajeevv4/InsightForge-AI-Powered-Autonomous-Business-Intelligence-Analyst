"""
Forecast Service: baseline forecast with confidence bands (Olist demo + uploaded datasets)
=======================================================================================
Deterministic: statsmodels ETS with fixed settings and a fixed simulation seed; every note and
reason is a template. No LLM calls.

Method (all thresholds live in FORECAST_RULES)
---------------------------------------------
1. Monthly series. Missing months are zero (SUM/COUNT metrics). A partial last month (data ends
   before the month's last day) is dropped, then sparse leading months are dropped: history starts
   at the first 3 consecutive months at or above 5% of the median month. Each trim is listed in `notes`.
2. >= 12 clean months -> monthly model. Otherwise, with >= 90 days of daily data -> daily model,
   aggregated to months by simulation (fixed seed). Otherwise the forecast is refused.
3. ETSModel: additive error, additive damped trend (damping factor bounded to 0.8-0.9), additive seasonality only with >= 2 full
   seasons (24 months, or 14 days for the weekly cycle of the daily model). Lower bounds >= 0.
4. Backtest: refit without the last 3 months (daily model: last 28 days, scored on the 4 weekly
   totals because the output is monthly) and compare with a naive baseline (last value; daily
   model: same weekday of the last training week).
5. MAPE > 40% and not beating naive -> status "refused" with a reason and no forecast numbers.
   Also refused when MAPE > 100% even if it beats naive (on noise a naive baseline can be so bad
   that "beating" it means nothing), and when the first month's 80% band is wider than +/-35% of
   the expected value (the model itself says the series is mostly noise; a 3-month backtest
   alone cannot tell noise from signal). Otherwise reliability = Good (<= 10%), Fair (<= 25%) or Weak.
6. Optional "exclude flagged anomaly days": each day flagged by the existing detectors (rolling
   MAD z-score / STL, overall series) is replaced by the detector's expected value before training.

Data paths
----------
* Olist: the existing monthly view behind /api/analytics/revenue-trend (AnalyticsService) plus
  one indexed MAX(order_purchase_timestamp) lookup for partial-month detection. Delivered orders
  only, same definitions as the KPIs.
* Uploaded datasets: owner check via load_context (403 / 404); one sqlglot-quoted monthly query
  validated by SQLValidator(DatasetSQLContext) and run on the scoped read-only path; the daily
  frame (only when needed) and anomaly days come from DatasetAnomalyService (same path).
"""

import logging
import math
import threading
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import text

from backend.app.database import readonly_engine
from backend.app.fixture_guard import is_fixture_mode_allowed
from backend.app.schemas.forecast import (
    BacktestPoint,
    ForecastBacktest,
    ForecastHistoryPoint,
    ForecastMetricOption,
    ForecastPoint,
    ForecastResponse,
)

try:
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
    ETS_AVAILABLE = True
except Exception:  # pragma: no cover
    ETS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# All forecasting thresholds in one place.
# ---------------------------------------------------------------------------------------------
FORECAST_RULES: Dict[str, Any] = {
    "sparse_leading_pct": 5.0,      # leading months below this % of the median month are dropped
    "leading_run": 3,               # history starts at the first 3 consecutive non-sparse months
    "min_months": 12,               # >= 12 clean months -> monthly model
    "min_days": 90,                 # otherwise >= 90 days -> daily model
    "full_seasons": 2,              # seasonality only with >= 2 full seasons
    "monthly_season": 12,
    "daily_season": 7,
    "backtest_months": 3,
    "backtest_days": 28,
    "refuse_mape": 40.0,            # MAPE above this AND not beating naive -> refused
    "hard_refuse_mape": 100.0,      # MAPE above this -> refused even if it beats naive (off by more than its own size)
    "max_band_ratio": 0.35,         # 80% band half-width above 35% of the expected value -> refused (mostly noise)
    "good_mape": 10.0,
    "fair_mape": 25.0,
    "horizon_min": 1,
    "horizon_max": 6,
    "horizon_default": 3,
    "damping_bounds": (0.8, 0.9),   # conservative damping: a baseline should not extrapolate growth far
    "simulations": 1000,            # daily model: simulated paths summed per month
    "seed": 42,
    "cache_ttl_seconds": 600,
}
ANOMALY_METHODS_FOR_EXCLUSION = ("rolling_zscore", "stl_residual")


class ForecastRefused(Exception):
    """Raised inside the core when no honest forecast is possible (carries the user-facing reason)."""


# =========================================================================== helpers (pure)
def month_label(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m")


def month_end(ts: pd.Timestamp) -> date:
    ts = pd.Timestamp(ts)
    return date(ts.year, ts.month, monthrange(ts.year, ts.month)[1])


def mape(actual: List[float], forecast: List[float]) -> Optional[float]:
    pairs = [(a, f) for a, f in zip(actual, forecast) if a not in (0, 0.0) and not math.isnan(a)]
    if not pairs:
        return None
    return round(float(np.mean([abs(a - f) / abs(a) for a, f in pairs]) * 100.0), 2)


def reliability_label(m: float) -> str:
    if m <= FORECAST_RULES["good_mape"]:
        return "Good"
    if m <= FORECAST_RULES["fair_mape"]:
        return "Fair"
    return "Weak"


def fill_months(monthly: pd.Series) -> pd.Series:
    """Month-start index, every month present (missing months = 0 for SUM/COUNT metrics)."""
    if monthly.empty:
        return monthly.astype(float)
    s = monthly.copy()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
    s = s.groupby(level=0).sum().astype(float)
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    return s.reindex(full, fill_value=0.0)


def trim_monthly(monthly: pd.Series, last_date: Optional[date]) -> Tuple[pd.Series, List[str]]:
    """Drop a partial last month, then sparse leading months. Returns (clean series, notes)."""
    notes: List[str] = []
    s = monthly.copy()
    if len(s) and last_date is not None:
        last_month = s.index[-1]
        if pd.Timestamp(last_date).to_period("M").to_timestamp() == last_month and last_date < month_end(last_month):
            notes.append(f"Dropped {month_label(last_month)}: partial month (data ends {last_date.isoformat()}).")
            s = s.iloc[:-1]
    if len(s):
        med = float(s.median())
        threshold = med * FORECAST_RULES["sparse_leading_pct"] / 100.0
        run = FORECAST_RULES["leading_run"]
        ok = [float(v) >= threshold for v in s.values]
        # The series starts at the first run of `run` consecutive non-sparse months, so an isolated
        # early month (e.g. one launch month followed by empty months) does not anchor the history.
        start = next((i for i in range(len(ok)) if all(ok[i:i + run]) and len(ok[i:i + run]) == run), None)
        if med > 0 and start:
            dropped = [month_label(m) for m in s.index[:start]]
            s = s.iloc[start:]
            notes.append(f"Dropped sparse leading month(s) {', '.join(dropped)}: before the first {run} consecutive "
                         f"months at or above {FORECAST_RULES['sparse_leading_pct']:.0f}% of the median month.")
    return s, notes


def apply_adjustments_monthly(monthly: pd.Series, deltas: Dict[date, float]) -> pd.Series:
    """Subtract (observed - expected) of each flagged day from its month."""
    if not deltas:
        return monthly
    s = monthly.copy()
    for d, delta in deltas.items():
        m = pd.Timestamp(d).to_period("M").to_timestamp()
        if m in s.index:
            s.loc[m] = s.loc[m] - delta
    return s.clip(lower=0.0)


def _fit_ets(y: pd.Series, season: int):
    seasonal = len(y) >= FORECAST_RULES["full_seasons"] * season
    model = ETSModel(y.astype(float), error="add", trend="add", damped_trend=True,
                     seasonal="add" if seasonal else None, seasonal_periods=season if seasonal else None,
                     bounds={"damping_trend": FORECAST_RULES["damping_bounds"]})
    return model.fit(disp=False), seasonal


def _model_name(kind: str, seasonal: bool, season: int) -> str:
    base = "ETS (additive error, additive damped trend"
    base += f", additive {'yearly' if season == 12 else 'weekly'} seasonality)" if seasonal else ", no seasonality)"
    return base + (" on monthly data" if kind == "monthly" else " on daily data, summed to months by simulation")


# =========================================================================== models
def monthly_model(y: pd.Series, horizon: int) -> Tuple[List[ForecastPoint], str]:
    res, seasonal = _fit_ets(y, FORECAST_RULES["monthly_season"])
    pred = res.get_prediction(start=len(y), end=len(y) + horizon - 1)
    f80, f95 = pred.summary_frame(alpha=0.2), pred.summary_frame(alpha=0.05)
    months = pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    points = []
    for i, m in enumerate(months):
        points.append(_ordered_point(month_label(m), f80["mean"].iloc[i], f80["pi_lower"].iloc[i], f80["pi_upper"].iloc[i],
                                     f95["pi_lower"].iloc[i], f95["pi_upper"].iloc[i]))
    return points, _model_name("monthly", seasonal, FORECAST_RULES["monthly_season"])


def daily_model(y: pd.Series, horizon: int) -> Tuple[List[ForecastPoint], str]:
    res, seasonal = _fit_ets(y, FORECAST_RULES["daily_season"])
    start = y.index[-1] + pd.Timedelta(days=1)
    # Training always ends on a month end, so `start` is the 1st of the first forecast month.
    end = pd.Timestamp(month_end(start + pd.DateOffset(months=horizon - 1)))
    days = pd.date_range(start, end, freq="D")
    point = np.asarray(res.forecast(len(days)), dtype=float)
    sims = np.asarray(res.simulate(nsimulations=len(days), repetitions=FORECAST_RULES["simulations"], anchor="end",
                                   random_state=FORECAST_RULES["seed"]), dtype=float).reshape(len(days), -1)
    sims = np.clip(sims, 0.0, None)
    months = days.to_period("M")
    points = []
    for m in months.unique():
        mask = np.asarray(months == m)
        totals = sims[mask].sum(axis=0)
        q = np.percentile(totals, [2.5, 10, 90, 97.5])
        points.append(_ordered_point(str(m), float(np.clip(point[mask], 0, None).sum()), q[1], q[2], q[0], q[3]))
    return points[:horizon], _model_name("daily", seasonal, FORECAST_RULES["daily_season"])


def _ordered_point(period: str, expected: float, lo80: float, hi80: float, lo95: float, hi95: float) -> ForecastPoint:
    """Clip at 0 and guarantee lower_95 <= lower_80 <= expected <= upper_80 <= upper_95."""
    lo80, hi80, lo95, hi95, expected = (max(0.0, float(v)) for v in (lo80, hi80, lo95, hi95, expected))
    lo95 = min(lo95, lo80)
    hi95 = max(hi95, hi80)
    expected = min(max(expected, lo80), hi80)
    r = lambda v: round(v, 2)  # noqa: E731
    return ForecastPoint(period=period, expected=r(expected), lower_80=r(lo80), upper_80=r(hi80), lower_95=r(lo95), upper_95=r(hi95))


def backtest_monthly(y: pd.Series) -> ForecastBacktest:
    k = FORECAST_RULES["backtest_months"]
    train, test = y.iloc[:-k], y.iloc[-k:]
    res, _ = _fit_ets(train, FORECAST_RULES["monthly_season"])
    fc = np.clip(np.asarray(res.forecast(k), dtype=float), 0, None)
    naive = [float(train.iloc[-1])] * k
    m, nm = mape(list(test.values), list(fc)), mape(list(test.values), naive)
    return ForecastBacktest(
        holdout=f"last {k} months ({month_label(test.index[0])} to {month_label(test.index[-1])})",
        mape=m, naive_mape=nm, naive_method="last observed month repeated",
        beats_naive=_beats(m, nm),
        points=[BacktestPoint(period=month_label(p), actual=round(float(a), 2), forecast=round(float(f), 2), naive=round(n, 2))
                for p, a, f, n in zip(test.index, test.values, fc, naive)],
    )


def backtest_daily(y: pd.Series) -> ForecastBacktest:
    k = FORECAST_RULES["backtest_days"]
    train, test = y.iloc[:-k], y.iloc[-k:]
    res, _ = _fit_ets(train, FORECAST_RULES["daily_season"])
    fc = np.clip(np.asarray(res.forecast(k), dtype=float), 0, None)
    last_week = train.iloc[-7:].values.astype(float)
    naive = np.array([last_week[i % 7] for i in range(k)])
    weeks = [slice(i, i + 7) for i in range(0, k, 7)]
    a_w = [float(test.values[w].sum()) for w in weeks]
    f_w = [float(fc[w].sum()) for w in weeks]
    n_w = [float(naive[w].sum()) for w in weeks]
    m, nm = mape(a_w, f_w), mape(a_w, n_w)
    return ForecastBacktest(
        holdout=f"last {k} days ({test.index[0].date()} to {test.index[-1].date()}), scored on weekly totals",
        mape=m, naive_mape=nm, naive_method="same weekday of the last training week",
        beats_naive=_beats(m, nm),
        points=[BacktestPoint(period=f"week of {test.index[w.start].date()}", actual=round(a, 2), forecast=round(f, 2), naive=round(n, 2))
                for w, a, f, n in zip(weeks, a_w, f_w, n_w)],
    )


def _beats(m: Optional[float], nm: Optional[float]) -> bool:
    return m is not None and (nm is None or m < nm)


# =========================================================================== core
def run_forecast(resp: ForecastResponse, monthly_raw: pd.Series, last_date: Optional[date], horizon: int,
                 deltas: Dict[date, float], daily_loader: Optional[Callable[[], pd.Series]] = None) -> ForecastResponse:
    """Fills history / forecast / backtest / reliability (or status=refused + reason)."""
    if not ETS_AVAILABLE:
        return refuse(resp, "The forecasting library (statsmodels ETS) is not available on the server.")
    monthly = fill_months(monthly_raw)
    if monthly.empty or float(monthly.abs().sum()) == 0.0:
        return refuse(resp, "This metric has no non-zero values to forecast.")
    raw_monthly = monthly.copy()
    adjusted = apply_adjustments_monthly(monthly, deltas)
    clean, notes = trim_monthly(adjusted, last_date)
    resp.notes += notes
    if resp.exclude_anomalies and "exclude_anomalies" in resp.section_errors:
        resp.notes.append("Anomaly days could NOT be excluded (the detector was unavailable), so the model was trained on raw values.")
    elif resp.exclude_anomalies:
        resp.notes.append(f"{resp.excluded_days} flagged anomaly day(s) replaced by the detector's expected value before training."
                          if resp.excluded_days else "No anomaly days were flagged for this metric, so nothing was excluded.")
    resp.history = [ForecastHistoryPoint(period=month_label(m), value=round(float(v), 2),
                                         raw_value=(round(float(raw_monthly.loc[m]), 2) if abs(raw_monthly.loc[m] - v) > 0.005 else None))
                    for m, v in clean.items()]
    try:
        if len(clean) >= FORECAST_RULES["min_months"]:
            resp.model_kind = "monthly"
            resp.training_window = f"{month_label(clean.index[0])} to {month_label(clean.index[-1])} ({len(clean)} months)"
            bt = backtest_monthly(clean)
            points, resp.model = monthly_model(clean, horizon)
        else:
            daily = daily_loader() if daily_loader is not None else None
            if daily is None or daily.empty or len(clean) == 0:
                return refuse(resp, f"Needs at least {FORECAST_RULES['min_months']} clean months or "
                                    f"{FORECAST_RULES['min_days']} days of data (found {len(clean)} clean month(s)).")
            daily = daily.copy()
            daily.index = pd.to_datetime(daily.index)
            for d, delta in deltas.items():
                ts = pd.Timestamp(d)
                if ts in daily.index:
                    daily.loc[ts] = max(0.0, float(daily.loc[ts]) - delta)
            start, stop = clean.index[0], pd.Timestamp(month_end(clean.index[-1]))
            daily = daily[(daily.index >= start) & (daily.index <= stop)]
            if len(daily) < FORECAST_RULES["min_days"]:
                return refuse(resp, f"Needs at least {FORECAST_RULES['min_months']} clean months or "
                                    f"{FORECAST_RULES['min_days']} days of data (found {len(clean)} clean month(s), "
                                    f"{len(daily)} day(s)).")
            resp.model_kind = "daily"
            resp.training_window = f"{daily.index[0].date()} to {daily.index[-1].date()} ({len(daily)} days)"
            bt = backtest_daily(daily)
            points, resp.model = daily_model(daily, horizon)
    except ForecastRefused as e:
        return refuse(resp, str(e))
    except Exception as e:
        logger.warning(f"Forecast model failed: {e}")
        return refuse(resp, "The forecasting model could not be fitted to this series (it may be constant or too irregular).")

    resp.backtest = bt
    if bt.mape is None:
        return refuse(resp, "The backtest period has only zero values, so accuracy cannot be measured.")
    if bt.mape > FORECAST_RULES["refuse_mape"] and not bt.beats_naive:
        return refuse(resp, f"Backtest error is too high: MAPE {bt.mape:.1f}% (limit {FORECAST_RULES['refuse_mape']:.0f}%) "
                            f"and it does not beat the naive baseline ({bt.naive_mape:.1f}%). "
                            f"This series is too irregular for an honest forecast.", keep_backtest=True)
    if bt.mape > FORECAST_RULES["hard_refuse_mape"]:
        return refuse(resp, f"Backtest error is too high: MAPE {bt.mape:.1f}% is above {FORECAST_RULES['hard_refuse_mape']:.0f}% "
                            f"(the forecast was off by more than the values themselves). This series is too irregular "
                            f"for an honest forecast.", keep_backtest=True)
    first = points[0] if points else None
    if first is not None:
        half = (first.upper_80 - first.lower_80) / 2.0
        if first.expected <= 0 or half / first.expected > FORECAST_RULES["max_band_ratio"]:
            pct = (half / first.expected * 100.0) if first.expected > 0 else float("inf")
            return refuse(resp, f"Too uncertain to be useful: the 80% range for {first.period} is "
                                f"{'+/-' + format(pct, '.0f') + '%' if math.isfinite(pct) else 'unbounded'} of the expected value "
                                f"(limit {FORECAST_RULES['max_band_ratio'] * 100:.0f}%). The series is mostly noise.",
                          keep_backtest=True)
    resp.status = "ok"
    resp.reliability = reliability_label(bt.mape)
    resp.forecast = points
    return resp


def refuse(resp: ForecastResponse, reason: str, keep_backtest: bool = False) -> ForecastResponse:
    resp.status = "refused"
    resp.reason = reason
    resp.forecast = []
    resp.reliability = None
    if not keep_backtest:
        resp.backtest = None
    else:  # the error figures explain the refusal; no forecast numbers are returned
        resp.backtest = resp.backtest.model_copy(update={"points": []}) if resp.backtest else None
    return resp


def clamp_horizon(h: Optional[int]) -> int:
    try:
        h = int(h if h is not None else FORECAST_RULES["horizon_default"])
    except (TypeError, ValueError):
        h = FORECAST_RULES["horizon_default"]
    return max(FORECAST_RULES["horizon_min"], min(FORECAST_RULES["horizon_max"], h))


def _retry_once(fn: Callable[[], Any]) -> Any:
    """One retry for a cold remote DB that hits the statement timeout once."""
    try:
        return fn()
    except Exception as e:
        if "timed out" in str(e) or "statement timeout" in str(e):
            return fn()
        raise


def anomaly_deltas(items) -> Dict[date, float]:
    """day -> observed - expected for flagged overall-series days (z-score preferred over STL)."""
    out: Dict[date, Tuple[int, float]] = {}
    for a in items:
        if a.dimension != "overall" or a.method not in ANOMALY_METHODS_FOR_EXCLUSION:
            continue
        try:
            d = date.fromisoformat(str(a.period)[:10])
        except ValueError:
            continue
        rank = ANOMALY_METHODS_FOR_EXCLUSION.index(a.method)
        if d not in out or rank < out[d][0]:
            out[d] = (rank, float(a.observed) - float(a.expected))
    return {d: v for d, (_r, v) in out.items()}


# =========================================================================== Olist
OLIST_FORECAST_METRICS = {
    "gross_revenue": {"label": "Gross revenue", "aggregation": "SUM", "column": "gross_revenue"},
    "order_count": {"label": "Delivered orders", "aggregation": "COUNT", "column": "total_orders"},
}
_OLIST_CACHE: Dict[Tuple, Tuple[float, ForecastResponse]] = {}
_OLIST_LOCK = threading.Lock()


class OlistForecastService:

    @staticmethod
    def _last_date() -> Optional[date]:
        if is_fixture_mode_allowed():
            return None
        sql = text("SELECT MAX(order_purchase_timestamp) AS last_ts FROM insightforge.orders WHERE order_status = 'delivered'")
        for attempt in range(2):  # one retry: a cold remote DB can hit the statement timeout once
            try:
                with readonly_engine.connect() as conn:
                    v = conn.execute(sql).scalar()
                return v.date() if v is not None else None
            except Exception as e:
                if attempt == 0 and "statement timeout" in str(e):
                    continue
                raise
        return None

    @classmethod
    def clear_cache(cls) -> None:
        with _OLIST_LOCK:
            _OLIST_CACHE.clear()

    @classmethod
    def forecast(cls, metric: Optional[str] = None, horizon: Optional[int] = None, exclude_anomalies: bool = False) -> ForecastResponse:
        from backend.app.services.dataset_file_parser import FileValidationError
        metric = metric or "gross_revenue"
        if metric not in OLIST_FORECAST_METRICS:
            raise FileValidationError(f"Unknown metric '{metric}'. Use one of: {', '.join(OLIST_FORECAST_METRICS)}.", status_code=400)
        h = clamp_horizon(horizon)
        key = (metric, h, bool(exclude_anomalies))
        with _OLIST_LOCK:
            hit = _OLIST_CACHE.get(key)
        if hit and time.time() - hit[0] < FORECAST_RULES["cache_ttl_seconds"]:
            return hit[1].model_copy(update={"cached": True})
        resp = cls._compute(metric, h, bool(exclude_anomalies))
        if not resp.section_errors and not (resp.status == "refused" and "unavailable" in (resp.reason or "")):
            with _OLIST_LOCK:  # degraded results (a timed-out input) are not cached, so the next call retries
                _OLIST_CACHE[key] = (time.time(), resp)
        return resp

    @classmethod
    def _compute(cls, metric: str, horizon: int, exclude: bool) -> ForecastResponse:
        from backend.app.services.analytics_service import AnalyticsService
        from backend.app.services.anomaly_service import AnomalyService
        from backend.app.services.dataset_workspace_service import run_tasks

        cfg = OLIST_FORECAST_METRICS[metric]
        resp = ForecastResponse(
            dataset_id="olist-demo", dataset_name="Olist E-Commerce (demo)", metric=metric, metric_label=cfg["label"],
            metrics=[ForecastMetricOption(key=k, label=v["label"], aggregation=v["aggregation"]) for k, v in OLIST_FORECAST_METRICS.items()],
            currency="R$" if metric == "gross_revenue" else None, horizon=horizon, exclude_anomalies=exclude,
            status="refused", generated_at=datetime.now(timezone.utc),
        )
        tasks: Dict[str, Callable[[], Any]] = {
            "monthly": AnalyticsService.fetch_revenue_trend,
            "last_date": cls._last_date,
        }
        if exclude:
            tasks["anomalies"] = lambda: _retry_once(lambda: AnomalyService.detect_all(grain="daily", metric=metric))
        results = run_tasks(tasks)
        ok, rows = results["monthly"]
        if not ok:
            return refuse(resp, f"Monthly series unavailable: {rows}")
        monthly = pd.Series({pd.Timestamp(str(r["month"])[:10]): float(r.get(cfg["column"]) or 0.0) for r in rows})
        ok_ld, last_date = results["last_date"]
        if not ok_ld:
            last_date = None
            resp.notes.append("Could not read the last data date; the last month was not checked for completeness.")
        deltas: Dict[date, float] = {}
        if exclude:
            ok_a, det = results["anomalies"]
            if ok_a:
                deltas = anomaly_deltas(det.anomalies)
            else:
                resp.section_errors["exclude_anomalies"] = f"anomaly detector unavailable: {det}"
        resp.excluded_days = len(deltas)
        return run_forecast(resp, monthly, last_date, horizon, deltas)


# =========================================================================== uploaded datasets
class DatasetForecastService:

    @classmethod
    def forecast(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str] = None,
                 horizon: Optional[int] = None, exclude_anomalies: bool = False) -> ForecastResponse:
        from backend.app.services.dataset_workspace_service import WorkspaceCache
        h = clamp_horizon(horizon)
        return WorkspaceCache.get_or_compute("forecast", dataset_id, owner_token, (metric or "", h, bool(exclude_anomalies)),
                                             lambda: cls._compute(dataset_id, owner_token, metric, h, bool(exclude_anomalies)))

    @classmethod
    def _compute(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str], horizon: int,
                 exclude: bool) -> ForecastResponse:
        from backend.app.services.dataset_anomaly_service import DatasetAnomalyService
        from backend.app.services.dataset_dashboard_service import TIME_TYPE_MARKERS, DatasetDashboardService, measure_expr, quote_ident
        from backend.app.services.dataset_file_parser import FileValidationError
        from backend.app.services.dataset_workspace_service import load_context, metric_key, run_tasks

        wc = load_context(dataset_id, owner_token)  # owner check: 403 / 404
        resp = ForecastResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, currency=None, horizon=horizon,
                                exclude_anomalies=exclude, status="refused", generated_at=datetime.now(timezone.utc))
        if wc.model is None:
            return refuse(resp, wc.model_error or "The semantic model is unavailable.")
        additive = [m for m in wc.measures if m.column is None or m.aggregation.upper() in ("SUM", "COUNT")]
        label_of = lambda m: m.name if m.column is not None else f"{m.table.replace('_', ' ').title()} Rows"  # noqa: E731
        timed = [m for m in additive if DatasetDashboardService._time_column(wc.profile, wc.model, m.table) is not None]
        resp.metrics = [ForecastMetricOption(key=metric_key(m), label=label_of(m),
                                             aggregation=("COUNT" if m.column is None else m.aggregation.upper())) for m in timed]
        by_key = {metric_key(m): m for m in additive}
        if metric:
            chosen = by_key.get(metric)
            if chosen is None:
                raise FileValidationError(f"Unknown or non-additive metric '{metric}'. Forecasts support SUM and COUNT measures.", status_code=400)
        else:
            chosen = wc.primary if (wc.primary is not None and wc.primary in timed) else (timed[0] if timed else (additive[0] if additive else None))
        if chosen is None:
            return refuse(resp, "This dataset has no SUM or COUNT measure to forecast.")
        resp.metric, resp.metric_label = metric_key(chosen), label_of(chosen)
        tc = DatasetDashboardService._time_column(wc.profile, wc.model, chosen.table)
        if tc is None:
            return refuse(resp, f"Table '{chosen.table}' has no date/time column, so there is no time series to forecast.")
        cand, colp = tc
        t = quote_ident(cand.column)
        tv = t if any(k in colp.pg_type.upper() for k in TIME_TYPE_MARKERS) else f"NULLIF({t}, '')::timestamp"
        sql = (f"SELECT CAST(DATE_TRUNC('month', {tv}) AS DATE) AS period, {measure_expr(chosen)} AS value, MAX({tv}) AS last_ts "
               f"FROM {quote_ident(wc.profile.schema_name)}.{quote_ident(chosen.table)} WHERE {t} IS NOT NULL GROUP BY 1 ORDER BY 1")
        tasks: Dict[str, Callable[[], Any]] = {"monthly": lambda: DatasetDashboardService._run(sql, wc.ctx, wc.profile.schema_name)}
        if exclude:
            tasks["anomalies"] = lambda: DatasetAnomalyService.get_anomalies(dataset_id, owner_token, metric=metric_key(chosen), grain="daily")
        results = run_tasks(tasks)
        ok, rows = results["monthly"]
        if not ok:
            return refuse(resp, f"Monthly series unavailable: {rows}")
        if not rows:
            return refuse(resp, "No dated rows to forecast.")
        monthly = pd.Series({pd.Timestamp(str(r["period"])[:10]): float(r.get("value") or 0.0) for r in rows})
        last_ts = max((pd.Timestamp(str(r["last_ts"])) for r in rows if r.get("last_ts")), default=None)
        deltas: Dict[date, float] = {}
        if exclude:
            ok_a, det = results["anomalies"]
            if ok_a:
                deltas = anomaly_deltas(det.anomalies)
            else:
                resp.section_errors["exclude_anomalies"] = f"anomaly detector unavailable: {det}"
        resp.excluded_days = len(deltas)

        def daily_loader() -> pd.Series:
            df, cols, _ = DatasetAnomalyService.build_frame(wc, chosen, "daily")
            if df.empty:
                return pd.Series(dtype=float)
            target = DatasetAnomalyService._target_alias(chosen, cols)
            if len(df) >= 500:
                resp.notes.append("Only the first 500 days were read (query row cap).")
            return pd.Series(pd.to_numeric(df[target], errors="coerce").fillna(0.0).values, index=pd.to_datetime(df["period_date"]))

        return run_forecast(resp, monthly, last_ts.date() if last_ts is not None else None, horizon, deltas, daily_loader)
