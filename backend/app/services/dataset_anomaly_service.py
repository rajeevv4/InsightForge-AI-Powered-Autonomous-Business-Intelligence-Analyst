"""
Dataset Anomaly Service (uploaded datasets only)
================================================
Runs the SAME deterministic detectors used for Olist on any uploaded dataset's time series,
without changing the Olist code path (AnomalyService.detect_all is untouched):

  (a) rolling robust z-score (MAD)        -> AnomalyService.detect_rolling_zscore   (reused as-is)
  (b) STL residuals                        -> AnomalyService.detect_stl_residuals    (reused as-is)
  (c) IQR across dimension slices          -> AnomalyService.detect_iqr_dimension_slices(df=...) (reused as-is)
  (d) multivariate IsolationForest         -> detect_isolation_forest_generic (mirrors the Olist method:
      contamination=0.03, random_state=42, n_estimators=100, same cold start and severity rule, but
      over the dataset's own measures; only when the table has >= 3 measures)

Severity calibration (calibrate_items) reproduces AnomalyService.detect_all exactly:
  high   if (>= 2 methods and |dev| >= 8) or |dev| >= 12
  medium if (>= 2 methods and |dev| >= 2.5) or |dev| >= 4
  low    otherwise
(test_dataset_anomalies proves equivalence on the Olist fixture series.)

Known events: a generic, country-neutral catalog (GENERIC_EVENT_CATALOG), shown only as
"(candidate)". No revenue values are hardcoded anywhere.

Data path: the daily/weekly frame is built with one validated, sqlglot-quoted query through the
existing read-only dataset path. Days without rows are zero-filled for SUM/COUNT measures (no
activity is a real zero, e.g. an outage) and left empty for AVG/MIN/MAX.
"""

import logging
import uuid
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from backend.app.schemas.anomaly import AnomalyItem, AnomalyTimeSeriesPoint
from backend.app.schemas.dataset_semantic import MeasureDefinition
from backend.app.schemas.dataset_workspace import WorkspaceAnomalyResponse, WorkspaceAnomalyScanResponse
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.dataset_dashboard_service import (
    TIME_TYPE_MARKERS,
    DatasetDashboardService,
    measure_expr,
    quote_ident,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import (
    WorkspaceCache,
    WorkspaceContext,
    _now,
    load_context,
    metric_key,
    metric_options,
)

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic, country-neutral known-event catalog. Matches are labels only, always
# marked "(candidate)" - they never change detection or severity.
# To add an event: append {"name", "rule", ...}. Rules:
#   "fixed":        month + day, optional "days_before"/"days_after" window
#   "black_friday": day after the 4th Thursday of November (+ "days_after")
#   "cyber_monday": the Monday after Black Friday
# ---------------------------------------------------------------------------
GENERIC_EVENT_CATALOG: List[Dict[str, Any]] = [
    {"name": "New Year", "rule": "fixed", "month": 1, "day": 1, "days_before": 1, "days_after": 0},
    {"name": "Black Friday", "rule": "black_friday", "days_after": 2},
    {"name": "Cyber Monday", "rule": "cyber_monday"},
    {"name": "Christmas", "rule": "fixed", "month": 12, "day": 25, "days_before": 1, "days_after": 1},
]

DETECTION_GRAINS = {"daily": "day", "weekly": "week"}
ADDITIVE_AGGS = {"SUM", "COUNT"}
MIN_POINTS = 30           # same minimum Quick Insights used
MAX_IF_FEATURES = 6       # IsolationForest uses the first N measures of the table
MAX_IQR_DIMENSIONS = 3


def _black_friday(year: int) -> date:
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(days=21 + 1)


def event_dates(year: int) -> Dict[date, str]:
    out: Dict[date, str] = {}
    for ev in GENERIC_EVENT_CATALOG:
        if ev["rule"] == "fixed":
            center = date(year, ev["month"], ev["day"])
            start, end = center - timedelta(days=ev.get("days_before", 0)), center + timedelta(days=ev.get("days_after", 0))
        elif ev["rule"] == "black_friday":
            start = _black_friday(year)
            end = start + timedelta(days=ev.get("days_after", 0))
        elif ev["rule"] == "cyber_monday":
            start = end = _black_friday(year) + timedelta(days=3)
        else:
            continue
        d = start
        while d <= end:
            out.setdefault(d, f"{ev['name']} {d.year if not (ev['rule'] == 'fixed' and ev['month'] == 1 and d.month == 12) else d.year + 1} (candidate)")
            d += timedelta(days=1)
    return out


def generic_event_label(period: str, grain: str = "daily") -> Optional[str]:
    try:
        start = date.fromisoformat(str(period)[:10])
    except ValueError:
        return None
    days = [start + timedelta(days=i) for i in range(7 if grain == "weekly" else 1)]
    for d in days:
        for y in (d.year - 1, d.year, d.year + 1):
            label = event_dates(y).get(d)
            if label:
                return label
    return None


def relabel(items: List[AnomalyItem], grain: str) -> List[AnomalyItem]:
    """Replace Olist catalog labels with the generic catalog (candidates only)."""
    out = []
    for it in items:
        label = generic_event_label(it.period, grain)
        out.append(it.model_copy(update={"known_event_candidate": label, "classification": label or "statistical_outlier"}))
    return out


def detect_isolation_forest_generic(df: pd.DataFrame, feature_cols: List[str], primary_col: str,
                                    confirmed_periods: Optional[set] = None, metric_label: str = "multivariate_daily",
                                    contamination: float = 0.03) -> List[AnomalyItem]:
    """Mirror of AnomalyService.detect_isolation_forest over arbitrary feature columns."""
    if not SKLEARN_AVAILABLE or len(df) < 20 or len(feature_cols) < 3:
        return []
    X = df[feature_cols].copy().astype(float)
    X = X.fillna(X.median())
    anomalies: List[AnomalyItem] = []
    try:
        iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        preds = iso.fit_predict(X)
        scores = -iso.score_samples(X)
        median_val = float(df[primary_col].median())
        cold_cutoff, period_dates = None, None
        date_col = "period_date" if "period_date" in df.columns else "period"
        if len(df) >= 90:
            try:
                period_dates = pd.to_datetime(df[date_col])
                cold_cutoff = period_dates.min() + pd.Timedelta(days=AnomalyService.COLD_START_DAYS)
            except Exception:
                cold_cutoff, period_dates = None, None
        for i in range(len(df)):
            if cold_cutoff is not None and period_dates is not None and period_dates.iloc[i] < cold_cutoff:
                continue
            if preds[i] == -1:
                score = float(scores[i])
                obs = float(df[primary_col].iloc[i]) if pd.notna(df[primary_col].iloc[i]) else median_val
                period_str = str(df["period"].iloc[i])
                is_confirmed = confirmed_periods is not None and period_str in confirmed_periods
                severity = ("high" if score > 0.65 else "medium") if is_confirmed else "low"
                anomalies.append(AnomalyItem(
                    metric=metric_label, dimension="overall", period=period_str,
                    observed=round(obs, 2), expected=round(median_val, 2), deviation_score=round(score, 3),
                    severity=severity, direction="spike" if obs >= median_val else "drop",
                    method="isolation_forest", known_event_candidate=None, classification="statistical_outlier",
                ))
    except Exception as e:
        logger.debug(f"Generic IsolationForest failed: {e}")
    return anomalies


def calibrate_items(time_series_items: List[AnomalyItem]) -> List[AnomalyItem]:
    """Exact reproduction of the severity calibration in AnomalyService.detect_all."""
    period_methods: Dict[str, set] = {}
    period_max_dev: Dict[str, float] = {}
    for a in time_series_items:
        period_methods.setdefault(a.period, set()).add(a.method)
        if abs(a.deviation_score) > abs(period_max_dev.get(a.period, 0.0)):
            period_max_dev[a.period] = a.deviation_score
    calibrated, seen = [], set()
    for item in time_series_items:
        key = (item.metric, item.dimension, item.period)
        if key in seen:
            continue
        seen.add(key)
        m_count = len(period_methods[item.period])
        dev_mag = abs(period_max_dev[item.period])
        if (m_count >= 2 and dev_mag >= 8.0) or (dev_mag >= 12.0):
            sev = "high"
        elif (m_count >= 2 and dev_mag >= 2.5) or (dev_mag >= 4.0):
            sev = "medium"
        else:
            sev = "low"
        calibrated.append(item.model_copy(update={
            "severity": sev,
            "classification": item.known_event_candidate or "statistical_outlier",
        }))
    return calibrated


def series_is_degenerate(series: pd.Series) -> bool:
    """True when the median absolute deviation of the whole series is 0 (e.g. daily sign-ups that are
    mostly 0 or 1). A robust z-score is meaningless there: every non-typical value looks infinite."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return True
    return float((s - s.median()).abs().median()) == 0.0


def run_detectors(df: pd.DataFrame, target_col: str, grain: str, if_features: List[str],
                  metric_label: str, ratio_metric: bool = False) -> Tuple[List[AnomalyItem], List[str]]:
    """Detectors (a), (b), (d) on one frame, then the shared calibration. Returns (items, methods_run).

    ratio_metric=True (AVG/MIN/MAX measures) applies the Olist small-sample rule: periods with fewer
    than AnomalyService.DEFAULT_MIN_ORDERS rows are ignored by (a) and (b), exactly as the Olist
    detectors do for their ratio metrics (aov, on_time_delivery_rate, avg_review_score).
    """
    methods = ["rolling_zscore"]
    if series_is_degenerate(df[target_col]):
        return [], []
    z = AnomalyService.detect_rolling_zscore(df, metric=target_col, window=14, threshold=2.5)
    stl = AnomalyService.detect_stl_residuals(df, metric=target_col, period=7 if grain == "daily" else 4, threshold=2.5)
    methods.append("stl_residual")
    if ratio_metric and "row_count" in df.columns:
        small = set(df.loc[df["row_count"] < AnomalyService.DEFAULT_MIN_ORDERS, "period"].astype(str))
        z = [a for a in z if a.period not in small]
        stl = [a for a in stl if a.period not in small]
    confirmed = {a.period for a in (z + stl)}
    iso: List[AnomalyItem] = []
    if grain == "daily" and len(if_features) >= 3:
        iso = detect_isolation_forest_generic(df, if_features, target_col, confirmed_periods=confirmed)
        methods.append("isolation_forest")
    items = [it.model_copy(update={"metric": metric_label}) if it.method != "isolation_forest" else it for it in (z + stl + iso)]
    return calibrate_items(relabel(items, grain)), methods


class DatasetAnomalyService:

    # ------------------------------------------------------------------ frame
    @classmethod
    def build_frame(cls, wc: WorkspaceContext, metric: MeasureDefinition, grain: str) -> Tuple[pd.DataFrame, Dict[str, MeasureDefinition], str]:
        """One validated query: period + every valid measure of the metric's table (+ row count)."""
        tc = DatasetDashboardService._time_column(wc.profile, wc.model, metric.table)
        if tc is None:
            raise FileValidationError(f"Table '{metric.table}' has no date/time column; anomaly detection needs a time series.", status_code=400)
        cand, col = tc
        t = quote_ident(cand.column)
        t_value = t if any(k in col.pg_type.upper() for k in TIME_TYPE_MARKERS) else f"NULLIF({t}, '')::timestamp"
        period_expr = f"CAST(DATE_TRUNC('{DETECTION_GRAINS[grain]}', {t_value}) AS DATE)"
        table_measures = [m for m in wc.measures if m.table == metric.table and m.column is not None]
        if metric.column is not None and all(metric_key(m) != metric_key(metric) for m in table_measures):
            table_measures.insert(0, metric)
        cols: Dict[str, MeasureDefinition] = {f"m{i}": m for i, m in enumerate(table_measures)}
        parts = [f"{period_expr}::text AS period", f"{period_expr} AS period_date", "COUNT(*) AS row_count"]
        parts += [f"{measure_expr(m)} AS {quote_ident(alias)}" for alias, m in cols.items()]
        raw_sql = (f"SELECT {', '.join(parts)} FROM {quote_ident(wc.profile.schema_name)}.{quote_ident(metric.table)} "
                   f"WHERE {t} IS NOT NULL GROUP BY 1, 2 ORDER BY 1")
        rows = DatasetDashboardService._run(raw_sql, wc.ctx, wc.profile.schema_name)
        df = pd.DataFrame(rows)
        if df.empty:
            return df, cols, cand.column
        df["period_date"] = pd.to_datetime(df["period_date"])
        # zero-fill missing periods for additive measures (no rows == no activity)
        freq = "D" if grain == "daily" else "W-MON"
        full = pd.date_range(df["period_date"].min(), df["period_date"].max(), freq=freq)
        df = df.set_index("period_date").reindex(full)
        df.index.name = "period_date"
        df = df.reset_index()
        df["period"] = df["period_date"].dt.strftime("%Y-%m-%d")
        df["row_count"] = pd.to_numeric(df["row_count"], errors="coerce").fillna(0.0)
        for alias, m in cols.items():
            df[alias] = pd.to_numeric(df[alias], errors="coerce")
            if m.aggregation.upper() in ADDITIVE_AGGS:
                df[alias] = df[alias].fillna(0.0)
        return df, cols, cand.column

    @staticmethod
    def _target_alias(metric: MeasureDefinition, cols: Dict[str, MeasureDefinition]) -> str:
        if metric.column is None:
            return "row_count"
        return next(a for a, m in cols.items() if metric_key(m) == metric_key(metric))

    # ------------------------------------------------------------------ list endpoint
    @classmethod
    def get_anomalies(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str] = None,
                      grain: str = "daily", severity: Optional[str] = None) -> WorkspaceAnomalyResponse:
        if grain not in DETECTION_GRAINS:
            raise FileValidationError("grain must be 'daily' or 'weekly'.", status_code=400)
        if severity and severity.lower() not in ("high", "medium", "low"):
            raise FileValidationError("severity must be high, medium or low.", status_code=400)
        full = WorkspaceCache.get_or_compute("anomalies", dataset_id, owner_token, (metric or "", grain),
                                             lambda: cls._compute(dataset_id, owner_token, metric, grain))
        if not severity:
            return full
        keep = [a for a in full.anomalies if a.severity == severity.lower()]
        keep_periods = {a.period for a in keep if a.dimension == "overall"}
        ts = [p if p.period in keep_periods or not p.is_anomaly
              else p.model_copy(update={"is_anomaly": False, "severity": None, "direction": None}) for p in full.time_series]
        return full.model_copy(update={"anomalies": keep, "total_anomalies": len(keep), "time_series": ts})

    @classmethod
    def _compute(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str], grain: str) -> WorkspaceAnomalyResponse:
        wc = load_context(dataset_id, owner_token)
        resp = WorkspaceAnomalyResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, grain=grain, generated_at=_now())
        if wc.model is None:
            resp.section_errors["anomalies"] = wc.model_error or "semantic model unavailable"
            return resp
        resp.metrics = [m for m in metric_options(wc.measures)
                        if DatasetDashboardService._time_column(wc.profile, wc.model, m.table) is not None]
        by_key = {metric_key(m): m for m in wc.measures}
        chosen = by_key.get(metric) if metric else wc.primary
        if metric and chosen is None:
            raise FileValidationError(f"Unknown metric '{metric}'.", status_code=400)
        if chosen is None:
            resp.section_errors["anomalies"] = "no measure in this dataset"
            return resp
        resp.metric = metric_key(chosen)
        try:
            df, cols, _tcol = cls.build_frame(wc, chosen, grain)
        except FileValidationError as e:
            resp.section_errors["anomalies"] = e.message
            return resp
        except Exception as e:
            resp.section_errors["anomalies"] = str(e).splitlines()[0][:160]
            return resp
        if len(df) < MIN_POINTS:
            resp.notes.append(f"Needs at least {MIN_POINTS} {grain} points for detection (found {len(df)}).")
            resp.time_series = cls._time_series(df, cls._target_alias(chosen, cols) if not df.empty else None, [])
            return resp
        if len(df) >= 500:
            resp.notes.append("Only the first 500 periods were analysed (query row cap).")
        target = cls._target_alias(chosen, cols)
        if_features = list(cols)[:MAX_IF_FEATURES]
        ratio = chosen.column is not None and chosen.aggregation.upper() not in ADDITIVE_AGGS
        items, methods = run_detectors(df, target, grain, if_features, metric_label=resp.metric, ratio_metric=ratio)
        if not methods:
            resp.notes.append(f"This {grain} series is too sparse for robust z-score detection (median absolute deviation is 0, "
                              f"e.g. most periods have the same value). Try the weekly grain.")
        if ratio:
            small = int((df["row_count"] < AnomalyService.DEFAULT_MIN_ORDERS).sum())
            if small:
                resp.notes.append(f"{small} of {len(df)} {grain} periods have fewer than {AnomalyService.DEFAULT_MIN_ORDERS} rows; "
                                  f"averages there are too noisy and were not tested (same rule as the Olist ratio metrics).")
        if grain == "daily" and len(if_features) < 3:
            resp.notes.append(f"IsolationForest skipped: table '{chosen.table}' has {len(if_features)} measure(s), needs at least 3.")
        resp.methods_run = methods
        # (c) IQR across dimension slices of this metric (safe joins only)
        try:
            resp.slice_outliers = cls._iqr_slices(wc, chosen)
            resp.methods_run.append("iqr_dimension")
        except Exception as e:
            resp.notes.append(f"Slice outliers skipped: {str(e).splitlines()[0][:120]}")
        items.sort(key=lambda x: abs(x.deviation_score), reverse=True)
        resp.anomalies = items
        resp.total_anomalies = len(items)
        resp.time_series = cls._time_series(df, target, items)
        return resp

    @staticmethod
    def _time_series(df: pd.DataFrame, target: Optional[str], items: List[AnomalyItem]) -> List[AnomalyTimeSeriesPoint]:
        if df.empty or target is None:
            return []
        series = pd.to_numeric(df[target], errors="coerce")
        baseline = series.rolling(window=14, min_periods=3, center=True).median().fillna(series.median())
        amap = {a.period: a for a in items if a.dimension == "overall"}
        out = []
        for i in range(len(df)):
            p = str(df["period"].iloc[i])
            obs = series.iloc[i]
            hit = amap.get(p)
            out.append(AnomalyTimeSeriesPoint(
                period=p, observed=round(float(obs), 2) if pd.notna(obs) else 0.0,
                expected=round(float(baseline.iloc[i]), 2) if pd.notna(baseline.iloc[i]) else 0.0,
                is_anomaly=hit is not None, severity=hit.severity if hit else None,
                direction=hit.direction if hit else None, known_event=generic_event_label(p),
            ))
        return out

    @classmethod
    def _iqr_slices(cls, wc: WorkspaceContext, metric: MeasureDefinition) -> List[AnomalyItem]:
        planned, _ = DatasetDashboardService.plan_breakdowns(wc.profile, wc.model, metric, max_breakdowns=MAX_IQR_DIMENSIONS)
        out: List[AnomalyItem] = []
        for d, rel in planned:
            b = DatasetDashboardService.build_breakdown(wc.profile, metric, d, rel, wc.ctx, top_n=500)
            slice_df = pd.DataFrame([(i.label, i.value) for i in b.items if i.value is not None], columns=["dim_name", "total_revenue"])
            if len(slice_df) < 4:
                continue
            found = AnomalyService.detect_iqr_dimension_slices(df=slice_df, metric=metric_key(metric))
            out.extend(a.model_copy(update={"dimension": f"{d.column}:{a.dimension.split(':', 1)[1]}", "period": "All time"}) for a in found)
        return out

    # ------------------------------------------------------------------ scan
    @classmethod
    def scan(cls, dataset_id: str, owner_token: Optional[str], grain: str = "daily") -> WorkspaceAnomalyScanResponse:
        if grain not in DETECTION_GRAINS:
            raise FileValidationError("grain must be 'daily' or 'weekly'.", status_code=400)
        wc = load_context(dataset_id, owner_token)
        if wc.model is None or wc.primary is None:
            raise FileValidationError("No measures available to scan in this dataset.", status_code=400)
        keys = [metric_key(m) for m in wc.measures
                if DatasetDashboardService._time_column(wc.profile, wc.model, m.table) is not None]
        all_items: List[AnomalyItem] = []
        slices: List[AnomalyItem] = []
        for k in keys:
            r = cls.get_anomalies(dataset_id, owner_token, metric=k, grain=grain)
            all_items.extend(r.anomalies)
            if not slices:
                slices = r.slice_outliers
        # per-metric calibration is kept (same choice as the fixed Olist scan); dedupe only
        seen, deduped = set(), []
        for a in sorted(all_items, key=lambda x: abs(x.deviation_score), reverse=True):
            k = (a.metric, a.dimension, a.period)
            if k not in seen:
                seen.add(k)
                deduped.append(a)
        return WorkspaceAnomalyScanResponse(
            dataset_id=wc.profile.id, scan_id=str(uuid.uuid4())[:8], status="completed",
            anomalies_detected=len(deduped), high_severity_count=sum(1 for a in deduped if a.severity == "high"),
            scanned_metrics=keys, anomalies=deduped, slice_outliers=slices,
        )

    # ------------------------------------------------------------------ Quick Insights
    @classmethod
    def quick_insights_items(cls, dataset_id: str, owner_token: Optional[str]) -> List[Dict[str, Any]]:
        """Items in the shape the Quick Insights table renders (period, metric, actual_value, ...)."""
        r = cls.get_anomalies(dataset_id, owner_token, grain="daily")
        label = next((m.label for m in r.metrics if m.key == r.metric), r.metric)
        out = []
        for a in r.anomalies:
            if a.dimension != "overall" or a.method == "isolation_forest":
                continue
            dev_pct = ((a.observed - a.expected) / a.expected * 100.0) if a.expected else 0.0
            out.append({
                "period": a.period, "metric": label, "actual_value": a.observed, "expected_value": a.expected,
                "deviation_pct": round(dev_pct, 1), "severity": a.severity, "label": a.known_event_candidate or a.classification,
                "direction": a.direction,
            })
        return out
