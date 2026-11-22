"""
Report Service: one-click report (Olist demo + uploaded datasets)
================================================================
Builds the report by calling the EXISTING services directly (not over HTTP), so every number is the
same one the other pages show:

  section        Olist demo                                      uploaded dataset
  -------------  ----------------------------------------------  ------------------------------------------
  header         DataQualityService row counts + trend months    stored profile + overview trend months
  kpis           AnalyticsService.fetch_canonical_kpis (Overview) DatasetWorkspaceService.get_overview (Overview)
  trend          AnalyticsService.fetch_revenue_trend            overview.trend
  breakdowns     AnalyticsService categories / states / payments overview.breakdowns (with "all groups total")
  anomalies      AnomalyService.detect_all + Feature 1 explain   DatasetAnomalyService + Feature 1 explain
  forecast       Feature 2 (OlistForecastService, 3 months)      Feature 2 (DatasetForecastService, 3 months)
  data_quality   DataQualityService.fetch_audit_summary          DatasetWorkspaceQuality.get_data_quality

Independent sections run in parallel within REPORT_BUDGET_SECONDS; a section that fails or runs out
of time becomes null with a reason in section_errors ("Section unavailable: <reason>"). Every summary
sentence, caveat and methodology line is a fixed template filled with computed values. No LLM.
Uploaded datasets: the owner check (403 / 404) runs before anything else and before any cache hit.
"""

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.schemas.report import (
    ReportAnomaly,
    ReportBreakdown,
    ReportBreakdownItem,
    ReportDQRow,
    ReportForecast,
    ReportForecastPoint,
    ReportKPI,
    ReportResponse,
    ReportTrend,
    ReportTrendPoint,
)

logger = logging.getLogger(__name__)

REPORT_BUDGET_SECONDS = 45.0
REPORT_CACHE_TTL_SECONDS = 120          # "cached briefly": a second click / the PDF download reuses it
REPORT_MAX_WORKERS = 6
REPORT_TOP_ANOMALIES = 5
REPORT_EXPLAIN_WORKERS = 2              # explanations run 4 queries each; keep remote DB load modest
REPORT_BREAKDOWN_ITEMS = 8
REPORT_MAX_BREAKDOWNS = 4
REPORT_FORECAST_HORIZON = 3

SECTIONS = ("header", "summary", "kpis", "trend", "breakdowns", "anomalies", "forecast", "data_quality")

METHODOLOGY = [
    "All numbers are computed by SQL aggregates and deterministic statistics; no AI model writes any number or sentence in this report.",
    "KPI tiles, the monthly trend and the breakdowns come from the same services as the Overview and Analytics pages.",
    "Anomalies: rolling robust z-score (median / MAD, 14-period window), STL residuals and IsolationForest, with one shared severity calibration.",
    "Anomaly drivers: the change is split by group against the trailing 14-period mix, scaled to the detector's expected value (waterfall reconciles exactly).",
    "Forecast: statsmodels ETS (additive error, damped trend), backtested on the last 3 months against a naive baseline; noisy or short series are refused.",
    "Data quality: key uniqueness, foreign-key orphans, negative values, future dates, missing values and join safety checks.",
]


# =========================================================================== formatting
def fmt_value(v: Optional[float], currency: Optional[str] = None, avg: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    whole = float(v).is_integer()
    decimals = 2 if (currency or avg or not whole) else 0
    body = f"{abs(v):,.{decimals}f}"
    sign = "-" if v < 0 else ""
    return f"{sign}{currency} {body}" if currency else f"{sign}{body}"


def pct_change(new: float, old: float) -> Optional[float]:
    return None if not old else (new - old) / abs(old) * 100.0


def status_word(s: str) -> str:
    w = (s or "").strip().split(" ", 1)[0].upper()
    return w if w in ("PASS", "WARN", "FAIL") else "WARN"


def _short(e: Any, limit: int = 160) -> str:
    msg = str(e).splitlines()[0] if str(e) else type(e).__name__
    return msg[:limit]


# =========================================================================== cache
_CACHE: Dict[str, Tuple[str, float, ReportResponse]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str, owner_hash: str) -> Optional[ReportResponse]:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit and hit[0] == owner_hash and time.time() - hit[1] < REPORT_CACHE_TTL_SECONDS:
        return hit[2].model_copy(update={"cached": True})
    return None


def _cache_put(key: str, owner_hash: str, value: ReportResponse) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (owner_hash, time.time(), value)


def clear_report_cache(dataset_id: Optional[str] = None) -> None:
    with _CACHE_LOCK:
        if dataset_id is None:
            _CACHE.clear()
        else:
            _CACHE.pop(dataset_id, None)


# =========================================================================== runner
def run_sections(tasks: Dict[str, Callable[[], Any]], budget: float) -> Dict[str, Tuple[bool, Any]]:
    """Run section builders in parallel; anything unfinished at the deadline is reported as timed out."""
    results: Dict[str, Tuple[bool, Any]] = {}
    pool = ThreadPoolExecutor(max_workers=REPORT_MAX_WORKERS)
    futures = {name: pool.submit(fn) for name, fn in tasks.items()}
    wait(list(futures.values()), timeout=budget)
    for name, fut in futures.items():
        if not fut.done():
            fut.cancel()
            results[name] = (False, f"timed out after the {budget:.0f} s report budget")
            continue
        try:
            results[name] = (True, fut.result())
        except Exception as e:
            logger.warning(f"Report section '{name}' failed: {_short(e)}")
            results[name] = (False, friendly_reason(e))
    pool.shutdown(wait=False, cancel_futures=True)
    return results


def friendly_reason(e: Any) -> str:
    """Short, user-facing reason (no driver / SQL internals)."""
    msg = str(getattr(e, "message", None) or getattr(e, "detail", None) or e)
    low = msg.lower()
    if "timed out" in low or "statement timeout" in low or "querycanceled" in low:
        return "the database query timed out; generate the report again in a minute"
    if "unavailable" in low and "database" in low:
        return "the database is unavailable"
    return _short(msg)


def explain_top(items: List[Any], explain: Callable[[Any], Any], deadline: float) -> List[Tuple[Any, str]]:
    """Feature 1 driver sentence for each anomaly (bounded concurrency, bounded by the report deadline)."""
    out: List[Tuple[Any, str]] = []
    pool = ThreadPoolExecutor(max_workers=REPORT_EXPLAIN_WORKERS)
    futures = [(a, pool.submit(explain, a)) for a in items]
    wait([f for _a, f in futures], timeout=max(1.0, deadline - time.time()))
    for a, f in futures:
        if not f.done():
            out.append((a, "Drivers unavailable: timed out within the report budget."))
            continue
        try:
            exp = f.result()
            if exp.top_drivers:
                out.append((a, exp.top_drivers[0].sentence))
            else:
                reason = exp.section_errors.get("dimensions") or "no dimension could be analysed"
                out.append((a, f"Drivers unavailable: {reason}."))
        except Exception as e:
            out.append((a, f"Drivers unavailable: {friendly_reason(e)}."))
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def top_anomalies(items: List[Any], n: int = REPORT_TOP_ANOMALIES) -> List[Any]:
    """Largest |deviation| first, one row per period, overall series only."""
    seen, out = set(), []
    for a in sorted(items, key=lambda x: (-abs(x.deviation_score), x.period)):
        if a.dimension != "overall" or a.period in seen:
            continue
        seen.add(a.period)
        out.append(a)
        if len(out) >= n:
            break
    return out


def forecast_section(fc: Any, currency: Optional[str]) -> ReportForecast:
    cur = currency if fc.currency else None
    return ReportForecast(
        metric_label=fc.metric_label or fc.metric or "metric", status=fc.status, reliability=fc.reliability, reason=fc.reason,
        model=fc.model, training_window=fc.training_window,
        mape=fc.backtest.mape if fc.backtest else None, naive_mape=fc.backtest.naive_mape if fc.backtest else None,
        points=[ReportForecastPoint(period=p.period, expected=p.expected, lower_80=p.lower_80, upper_80=p.upper_80,
                                    expected_display=fmt_value(p.expected, cur),
                                    range_display=f"{fmt_value(p.lower_80, cur)} to {fmt_value(p.upper_80, cur)}")
                for p in fc.forecast],
        disclaimer=fc.disclaimer,
    )


def breakdown_from_groups(title: str, groups: List[Tuple[str, float]], currency: Optional[str], total_label: str) -> ReportBreakdown:
    groups = sorted(groups, key=lambda g: -(g[1] or 0.0))
    total = sum(v or 0.0 for _l, v in groups)
    top, rest = groups[:REPORT_BREAKDOWN_ITEMS], groups[REPORT_BREAKDOWN_ITEMS:]
    return ReportBreakdown(
        title=title,
        items=[ReportBreakdownItem(label=str(l), value=v, display=fmt_value(v, currency),
                                   share_pct=round(v / total * 100.0, 1) if total else None) for l, v in top],
        other_groups=len(rest), other_display=fmt_value(sum(v or 0.0 for _l, v in rest), currency) if rest else None,
        total_value=round(total, 2), total_line=f"All groups total ({total_label}): {fmt_value(total, currency)}",
    )


# =========================================================================== summary (templates)
def build_summary(r: ReportResponse, primary_kpi: Optional[ReportKPI], trend_last_full: Optional[Tuple[str, float, float]]) -> List[str]:
    s: List[str] = []
    if r.period:
        rows = f" with {r.total_rows:,} rows across {len(r.row_counts)} tables" if r.total_rows is not None else ""
        s.append(f"{r.dataset_name} covers {r.period}{rows}.")
    elif r.total_rows is not None:
        s.append(f"{r.dataset_name} has {r.total_rows:,} rows across {len(r.row_counts)} tables and no usable time column.")
    if primary_kpi is not None:
        others = [k for k in (r.kpis or []) if k is not primary_kpi][:2]
        extra = f" ({'; '.join(f'{k.label}: {k.display}' for k in others)})" if others else ""
        s.append(f"{primary_kpi.label} is {primary_kpi.display}{extra}.")
    if trend_last_full is not None:
        month, value, change = trend_last_full
        unit = r.currency if (r.is_demo and r.trend and "revenue" in r.trend.title.lower()) else None
        if change is None:
            s.append(f"The latest full month in the trend ({month}) was {fmt_value(value, unit)}.")
        else:
            s.append(f"The latest full month in the trend ({month}) was {fmt_value(value, unit)}, "
                     f"{'up' if change >= 0 else 'down'} {abs(change):.1f}% on the previous month.")
    if r.breakdowns:
        b = r.breakdowns[0]
        if b.items and b.items[0].share_pct is not None:
            s.append(f"In {b.title.lower()}, {b.items[0].label} leads with {b.items[0].share_pct:.1f}% of the total.")
    if r.anomalies is not None:
        if r.anomalies:
            a = r.anomalies[0]
            s.append(f"{r.anomaly_count} anomalies were flagged; the largest was a {a.direction} on {a.period} "
                     f"({a.observed_display} vs {a.expected_display} expected). {a.driver_sentence}")
        else:
            s.append("No anomalies were flagged in the daily series.")
    if r.forecast is not None:
        f = r.forecast
        if f.status == "ok" and f.points:
            s.append(f"The baseline forecast for {f.metric_label.lower()} over the next {len(f.points)} months is "
                     f"{', '.join(p.expected_display for p in f.points)} (reliability: {f.reliability}).")
        else:
            s.append(f"No forecast is shown for {f.metric_label.lower()}: {f.reason}")
    if r.data_quality is not None:
        counts = {k: sum(1 for d in r.data_quality if d.status == k) for k in ("PASS", "WARN", "FAIL")}
        s.append(f"Data quality: {counts['PASS']} checks pass, {counts['WARN']} warn and {counts['FAIL']} fail.")
    return s[:8]


def last_full_month(points: List[ReportTrendPoint], partial_month: Optional[str]) -> Optional[Tuple[str, float, Optional[float]]]:
    pts = [p for p in points if p.period != partial_month]
    if not pts:
        return None
    last = pts[-1]
    prev = pts[-2].value if len(pts) > 1 else None
    return last.period, last.value, (pct_change(last.value, prev) if prev is not None else None)


# =========================================================================== Olist
class OlistReportService:

    @classmethod
    def build(cls) -> ReportResponse:
        hit = _cache_get("olist-demo", "")
        if hit is not None:
            return hit
        r = cls._compute()
        if not r.section_errors:
            _cache_put("olist-demo", "", r)
        return r

    @classmethod
    def _compute(cls) -> ReportResponse:
        from backend.app.services.analytics_service import AnalyticsService
        from backend.app.services.anomaly_explain_service import OlistAnomalyExplainService
        from backend.app.services.anomaly_service import AnomalyService
        from backend.app.services.data_quality_service import DataQualityService
        from backend.app.services.forecast_service import OlistForecastService

        t0 = time.time()
        deadline = t0 + REPORT_BUDGET_SECONDS
        cur = "R$"
        r = ReportResponse(dataset_id="olist-demo", dataset_name="Olist E-Commerce (demo)", is_demo=True, currency=cur,
                           generated_at=datetime.now(timezone.utc), methodology=list(METHODOLOGY))

        def anomalies_task():
            from backend.app.services.forecast_service import _retry_once
            det = _retry_once(lambda: AnomalyService.detect_all(grain="daily", metric="gross_revenue"))
            top = top_anomalies(det.anomalies)
            explained = explain_top(top, lambda a: OlistAnomalyExplainService.explain("gross_revenue", a.period, "daily"), deadline)
            return det.total_anomalies, explained

        results = run_sections({
            "kpis": AnalyticsService.fetch_canonical_kpis,
            "trend": AnalyticsService.fetch_revenue_trend,
            "categories": lambda: AnalyticsService.fetch_categories(limit=500),
            "states": AnalyticsService.fetch_states,
            "payments": AnalyticsService.fetch_payments,
            "anomalies": anomalies_task,
            "forecast": lambda: OlistForecastService.forecast("gross_revenue", REPORT_FORECAST_HORIZON, False),
            "data_quality": DataQualityService.fetch_audit_summary,
        }, REPORT_BUDGET_SECONDS)

        primary = None
        ok, k = results["kpis"]
        if ok:
            r.kpis = [
                ReportKPI(label="Gross revenue", value=k["gross_revenue"], display=fmt_value(k["gross_revenue"], cur)),
                ReportKPI(label="Delivered orders", value=k["delivered_orders"], display=fmt_value(k["delivered_orders"])),
                ReportKPI(label="Average order value", value=k["aov"], display=fmt_value(k["aov"], cur)),
                ReportKPI(label="Product revenue", value=k["product_revenue"], display=fmt_value(k["product_revenue"], cur)),
                ReportKPI(label="Freight revenue", value=k["freight_revenue"], display=fmt_value(k["freight_revenue"], cur)),
                ReportKPI(label="Active customers", value=k["active_customers"], display=fmt_value(k["active_customers"])),
                ReportKPI(label="Units sold", value=k["units_sold"], display=fmt_value(k["units_sold"])),
                ReportKPI(label="Average review score", value=k["csat"], display=fmt_value(k["csat"], avg=True)),
            ]
            primary = r.kpis[0]
        else:
            r.section_errors["kpis"] = k

        ok, rows = results["trend"]
        if ok and rows:
            r.trend = ReportTrend(title="Gross revenue by month (delivered orders)",
                                  points=[ReportTrendPoint(period=str(x["month"])[:7], value=float(x["gross_revenue"])) for x in rows])
            r.period = f"{r.trend.points[0].period} to {r.trend.points[-1].period}"
        else:
            r.section_errors["trend"] = rows if not ok else "no months returned"

        bds, bd_err = [], []
        for key, title, total_label, conv in (
            ("categories", "Product revenue by category", "all categories", lambda x: (x["category"], float(x["total_revenue"]))),
            ("states", "Gross revenue by customer state", "all states", lambda x: (x["state"], float(x["total_gross_revenue"]))),
            ("payments", "Payment value by payment type", "all payment types", lambda x: (x["payment_type"], float(x["total_payment_value"]))),
        ):
            ok, val = results[key]
            if ok:
                bds.append(breakdown_from_groups(title, [conv(x) for x in val], cur, total_label))
            else:
                bd_err.append(f"{title}: {val}")
        if bds:
            r.breakdowns = bds
        if bd_err and not bds:
            r.section_errors["breakdowns"] = "; ".join(bd_err)
        elif bd_err:
            r.caveats.append("Some breakdowns are unavailable: " + "; ".join(bd_err))

        ok, val = results["anomalies"]
        if ok:
            total, explained = val
            r.anomaly_count = total
            r.anomalies = [ReportAnomaly(period=a.period, metric_label="Gross revenue", direction=a.direction, severity=a.severity,
                                         method=a.method, observed_display=fmt_value(a.observed, cur),
                                         expected_display=fmt_value(a.expected, cur), driver_sentence=s) for a, s in explained]
        else:
            r.section_errors["anomalies"] = val

        partial = None
        ok, fc = results["forecast"]
        if ok:
            r.forecast = forecast_section(fc, cur)
            partial = next((n.split(":")[0].replace("Dropped ", "") for n in fc.notes if "partial month" in n), None)
        else:
            r.section_errors["forecast"] = fc

        ok, dq = results["data_quality"]
        if ok:
            r.row_counts = {k2: int(v) for k2, v in dq.get("table_row_counts", {}).items()}
            r.total_rows = sum(r.row_counts.values())
            missing = dq.get("missing_value_summary", {}) or {}
            r.data_quality = [
                ReportDQRow(check="Overall audit", status=status_word(dq.get("audit_status", "")), detail=dq.get("audit_status", "")),
                ReportDQRow(check="Primary key uniqueness", status=status_word(dq.get("primary_key_uniqueness", "")), detail=dq.get("primary_key_uniqueness", "")),
                ReportDQRow(check="Foreign key integrity", status=status_word(dq.get("foreign_key_integrity", "")), detail=dq.get("foreign_key_integrity", "")),
                ReportDQRow(check="Domain bounds", status=status_word(dq.get("domain_bounds_status", "")), detail=dq.get("domain_bounds_status", "")),
                ReportDQRow(check="Join safety", status=status_word(dq.get("join_safety_status", "")), detail=dq.get("join_safety_status", "")),
                ReportDQRow(check="Missing values", status="WARN" if missing else "PASS",
                            detail="; ".join(f"{c}: {n:,}" for c, n in missing.items()) or "no missing values"),
            ]
        else:
            r.section_errors["data_quality"] = dq
            r.section_errors["header"] = "row counts unavailable (data quality audit failed)"

        r.caveats += [
            "Revenue counts delivered orders only (item price + freight), the same definition as the KPI tiles.",
            "Category revenue is product revenue (no freight); state revenue is gross revenue; payment value includes all instalments, so the three totals differ by design.",
            "The first months (2016) and the last month (2018-08) are sparse or partial in the source data.",
        ]
        if r.forecast is not None:
            r.caveats.append(r.forecast.disclaimer)
        return finish(r, primary, last_full_month(r.trend.points, partial) if r.trend else None, t0)


def finish(r: ReportResponse, primary: Optional[ReportKPI], trend_last: Optional[Tuple], t0: float) -> ReportResponse:
    try:
        r.summary = build_summary(r, primary, trend_last)
        if not r.summary:
            r.summary = None
            r.section_errors["summary"] = "no section produced numbers to summarise"
    except Exception as e:
        r.section_errors["summary"] = _short(e)
    r.elapsed_seconds = round(time.time() - t0, 2)
    return r


# =========================================================================== uploaded datasets
class DatasetReportService:

    @classmethod
    def build(cls, dataset_id: str, owner_token: Optional[str]) -> ReportResponse:
        from backend.app.services.dataset_file_parser import FileValidationError
        from backend.app.services.dataset_service import DatasetService, hash_token

        # Owner isolation first (403 wrong / missing token, 404 unknown id) - also before any cache hit.
        profile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)
        if profile.is_demo or profile.schema_name == "insightforge":
            raise FileValidationError("Use /api/report for the Olist demo dataset.", status_code=400)
        owner_hash = hash_token(owner_token) if owner_token else ""
        hit = _cache_get(dataset_id, owner_hash)
        if hit is not None:
            return hit
        r = cls._compute(dataset_id, owner_token, profile)
        if not r.section_errors:
            _cache_put(dataset_id, owner_hash, r)
        return r

    @classmethod
    def _compute(cls, dataset_id: str, owner_token: Optional[str], profile: Any) -> ReportResponse:
        from backend.app.services.anomaly_explain_service import DatasetAnomalyExplainService
        from backend.app.services.dataset_anomaly_service import DatasetAnomalyService
        from backend.app.services.dataset_workspace_service import DatasetWorkspaceQuality, DatasetWorkspaceService
        from backend.app.services.forecast_service import DatasetForecastService

        t0 = time.time()
        deadline = t0 + REPORT_BUDGET_SECONDS
        r = ReportResponse(dataset_id=profile.id, dataset_name=profile.name, is_demo=False, currency=None,
                           generated_at=datetime.now(timezone.utc), methodology=list(METHODOLOGY))
        r.row_counts = {t.safe_name: int(t.row_count) for t in profile.tables}
        r.total_rows = sum(r.row_counts.values())

        def anomalies_task():
            det = DatasetAnomalyService.get_anomalies(dataset_id, owner_token, grain="daily")
            if det.section_errors.get("anomalies") and not det.anomalies:
                raise ValueError(det.section_errors["anomalies"])
            label = next((m.label for m in det.metrics if m.key == det.metric), det.metric or "metric")
            top = top_anomalies(det.anomalies)
            explained = explain_top(top, lambda a: DatasetAnomalyExplainService.explain(dataset_id, owner_token, det.metric, a.period, "daily"), deadline)
            return det.total_anomalies, label, explained, det.notes

        results = run_sections({
            "overview": lambda: DatasetWorkspaceService.get_overview(dataset_id, owner_token),
            "anomalies": anomalies_task,
            "forecast": lambda: DatasetForecastService.forecast(dataset_id, owner_token, None, REPORT_FORECAST_HORIZON, False),
            "data_quality": lambda: DatasetWorkspaceQuality.get_data_quality(dataset_id, owner_token),
        }, REPORT_BUDGET_SECONDS)

        primary = None
        ok, ov = results["overview"]
        if ok:
            if ov.kpis:
                r.kpis = [ReportKPI(label=k.label if k.column is not None else f"{k.table.replace('_', ' ').title()} rows",
                                    value=k.value, display=(fmt_value(k.value, avg=k.aggregation.upper() == "AVG") if k.error is None else f"n/a ({k.error})"))
                          for k in ov.kpis]
                primary = next((k for k, src in zip(r.kpis, ov.kpis) if ov.primary_measure and
                                f"{src.table}.{src.column}" == ov.primary_measure), r.kpis[0] if r.kpis else None)
            else:
                r.section_errors["kpis"] = ov.section_errors.get("kpis", "no KPIs")
            if ov.trend and ov.trend.points:
                r.trend = ReportTrend(title=ov.trend.title,
                                      points=[ReportTrendPoint(period=str(p["period"])[:7], value=float(p.get("value") or 0.0)) for p in ov.trend.points])
                r.period = f"{r.trend.points[0].period} to {r.trend.points[-1].period}"
            else:
                r.section_errors["trend"] = ov.section_errors.get("trend", "no date/time column for a monthly trend")
            if ov.breakdowns:
                r.breakdowns = []
                for b in ov.breakdowns[:REPORT_MAX_BREAKDOWNS]:
                    is_sum = b.total_value is not None
                    r.breakdowns.append(ReportBreakdown(
                        title=b.title,
                        items=[ReportBreakdownItem(label=i.label, value=i.value, display=fmt_value(i.value, avg=b.aggregation.upper() == "AVG"),
                                                   share_pct=(round(i.value / b.total_value * 100.0, 1) if (is_sum and b.total_value and i.value is not None) else None))
                               for i in b.items[:REPORT_BREAKDOWN_ITEMS]],
                        other_groups=b.other_groups + max(0, len(b.items) - REPORT_BREAKDOWN_ITEMS),
                        other_display=fmt_value(b.other_value) if b.other_value is not None else None,
                        total_value=b.total_value,
                        total_line=f"All groups total: {fmt_value(b.total_value)}" if is_sum else None,
                    ))
                r.caveats += [f"Breakdown skipped: {s.dimension} ({s.reason})." for s in ov.skipped_breakdowns[:4]]
            else:
                r.section_errors["breakdowns"] = ov.section_errors.get("breakdowns", "no groupable dimension")
        else:
            for s in ("kpis", "trend", "breakdowns"):
                r.section_errors[s] = ov

        ok, val = results["anomalies"]
        if ok:
            total, label, explained, notes = val
            r.anomaly_count = total
            r.anomalies = [ReportAnomaly(period=a.period, metric_label=label, direction=a.direction, severity=a.severity,
                                         method=a.method, observed_display=fmt_value(a.observed), expected_display=fmt_value(a.expected),
                                         driver_sentence=s) for a, s in explained]
            r.caveats += notes[:2]
        else:
            r.section_errors["anomalies"] = val

        ok, fc = results["forecast"]
        partial = None
        if ok:
            r.forecast = forecast_section(fc, None)
            partial = next((n.split(":")[0].replace("Dropped ", "") for n in fc.notes if "partial month" in n), None)
        else:
            r.section_errors["forecast"] = fc

        ok, dq = results["data_quality"]
        if ok:
            rows = [ReportDQRow(check="Overall audit", status=status_word(dq.audit_status), detail=dq.audit_status)]
            for label, val in (("Primary key uniqueness", dq.primary_key_uniqueness), ("Foreign key integrity", dq.foreign_key_integrity),
                               ("Domain bounds", dq.domain_bounds_status), ("Join safety", dq.join_safety_status)):
                if val:
                    rows.append(ReportDQRow(check=label, status=status_word(val), detail=val))
            for c in dq.checks:
                if c.status in ("WARN", "FAIL"):
                    rows.append(ReportDQRow(check=f"{c.check.replace('_', ' ')}: {c.table}{'.' + c.column if c.column else ''}",
                                            status=c.status, detail=c.detail))
            r.data_quality = rows[:20]
        else:
            r.section_errors["data_quality"] = dq

        r.caveats += [
            "Numbers are shown without a currency symbol: the dataset does not say which currency it uses.",
            "Breakdowns that use another table only follow relationships you confirmed on the Datasets page (no row multiplication).",
        ]
        if r.forecast is not None:
            r.caveats.append(r.forecast.disclaimer)
        return finish(r, primary, last_full_month(r.trend.points, partial) if r.trend else None, t0)
