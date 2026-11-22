"""
Anomaly Explain Service ("Explain this anomaly": root-cause waterfall)
=====================================================================
Answers "WHY did <metric> spike/drop on <period>?" for an anomaly that the existing detectors
flagged, for both the Olist demo and uploaded datasets. Fully deterministic: every number comes
from SQL aggregates and every sentence from the templates in this module. No LLM calls.

Method (identical for both sources)
-----------------------------------
* Target period t (a day or an ISO week) and a trailing baseline window of the previous
  BASELINE_PERIODS periods (14 = the rolling z-score window the detector uses).
* One grouped query per dimension returns, per group, the metric's numerator for t and for the
  baseline window (conditional aggregation, so a dimension costs exactly one query).
* Additive metrics (SUM / COUNT, Olist revenue and order count):
      expected_k  = baseline_k / n_periods * scale      scale = E / sum(baseline_k / n_periods)
      contrib_k   = observed_k - expected_k
  The baseline MIX is taken from the trailing window and scaled so it adds up to the headline
  expected value E, so  E + sum(contrib_k) = O  and the waterfall reconciles exactly. Any
  difference between the detector's observed value and the grouped total goes into "All other".
* Ratio metrics (averages / rates: AOV, on-time %, review score, AVG measures):
      R = N / D,  contrib_k = N1_k / D1 - N0_k / D0     (sums exactly to R1 - R0)
  The waterfall runs from the trailing level R0 to the observed level R1.
* Volume vs value (sum-type metrics only): with V = volume (orders / rows) and A = value per unit,
      volume effect = (V1 - V0) * A0,   value effect = (A1 - A0) * V1   (sums exactly to the change)
* Explanatory power of a dimension = share of the change explained by its top 3 groups (pushing
  in the direction of the change), capped at 1.
* Mix shift = total variation distance between the baseline group mix and this period's mix
  (10 largest groups + one "other" bucket, so long tails of tiny groups do not add noise).
  0 = every group moved proportionally (a broad-based change).
* Dimensions are ordered best first by rank_score = explanatory power x mix shift: a dimension
  explains the anomaly when the change is concentrated in a few of its groups AND those groups
  moved differently from their usual share. (Power alone always favours dimensions with few
  groups; mix shift alone favours very fragmented dimensions.)

Safety
------
* Olist: fixed SQL with bound date parameters on the read-only engine (same engine the Olist
  analytics use). Fan-out rules: delivered orders only; one row per order for order-level
  dimensions (item revenue and reviews pre-aggregated per order, primary payment =
  payment_sequential 1, which is part of the primary key, so one row per order).
* Uploaded datasets: owner check via load_context (403 / 404), sqlglot-quoted identifiers, every
  statement validated by SQLValidator(DatasetSQLContext) and run on the existing read-only scoped
  path (DatasetDashboardService._run). Joins only along confirmed N:1 relationships
  (DatasetDashboardService.plan_breakdowns / find_safe_join). Date literals come from
  date.isoformat(), never from user text.
* Each section (headline, each dimension, volume/value) fails independently.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

from backend.app.database import readonly_engine
from backend.app.fixture_guard import is_fixture_mode_allowed
from backend.app.schemas.anomaly_explain import (
    AnomalyExplanationResponse,
    ExplainDimension,
    ExplainDriver,
    ExplainHeadline,
    ExplainTopDriver,
    SkippedDimension,
    VolumeValue,
    WaterfallStep,
)
from backend.app.schemas.dataset_semantic import MeasureDefinition
from backend.app.services.dataset_dashboard_service import (
    TIME_TYPE_MARKERS,
    DatasetDashboardService,
    _short,
    quote_ident,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import (
    WorkspaceCache,
    load_context,
    metric_key,
    run_tasks,
)

logger = logging.getLogger(__name__)

BASELINE_PERIODS = 14          # = rolling z-score window used by the detectors
WATERFALL_DRIVERS = 5          # driver steps shown before "All other"
LIST_DRIVERS = 8               # groups listed per dimension tab
MIX_TOP_GROUPS = 10            # mix shift compares the 10 largest groups + one "other" bucket
POWER_TOP_K = 3                # explanatory power = share explained by the top 3 groups
MAX_DATASET_DIMENSIONS = 4
RESIDUAL_NOTE_PCT = 0.5        # note when grouped totals differ from the headline by more than this %
EXPLAIN_CACHE_TTL = 600
GRAINS = {"daily": "day", "weekly": "week"}

OLIST_ID = "olist-demo"
OLIST_FIRST_DAY = date(2017, 1, 1)
OLIST_END_EXCL = date(2018, 9, 1)

# Olist metrics: label, unit, additive?, which dimension levels can split it exactly.
OLIST_METRICS: Dict[str, Dict[str, Any]] = {
    "gross_revenue": {"label": "Gross revenue", "unit": "currency", "additive": True, "levels": {"item", "order"}},
    "order_count": {"label": "Delivered orders", "unit": "count", "additive": True, "levels": {"order"}},
    "aov": {"label": "Average order value", "unit": "currency", "additive": False, "levels": {"item", "order"}},
    "on_time_delivery_rate": {"label": "On-time delivery rate", "unit": "percent", "additive": False, "levels": {"item", "order"}},
    "avg_review_score": {"label": "Average review score", "unit": "score", "additive": False, "levels": {"order"}},
}

# Olist dimensions: key -> (label, level, SQL expression over the row CTE, join clause)
OLIST_DIMENSIONS: Dict[str, Dict[str, str]] = {
    "category": {"label": "Category", "level": "item"},
    "seller": {"label": "Seller", "level": "item"},
    "state": {"label": "Customer state", "level": "order"},
    "payment_type": {"label": "Payment type", "level": "order"},
}


# =========================================================================== formatting
def _fmt_plain(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}"


def fmt_value(v: Optional[float], unit: str, currency: Optional[str] = None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    a = abs(v)
    if unit == "currency" and currency:
        body = _fmt_plain(a, 0 if a >= 1000 else 2)
        return f"{'-' if v < 0 else ''}{currency} {body}"
    if unit == "count":
        body = _fmt_plain(a, 0 if float(a).is_integer() else 1)
    elif unit == "percent":
        return f"{v:.1f}%"
    elif unit == "score":
        body = _fmt_plain(a, 2)
    else:
        body = _fmt_plain(a, 0 if (a >= 1000 or float(round(a, 2)).is_integer()) else 2)
    return f"{'-' if v < 0 else ''}{body}"


def fmt_change(v: float, unit: str, currency: Optional[str] = None) -> str:
    if unit == "percent":
        return f"{'+' if v >= 0 else '-'}{abs(v):.1f} pts"
    s = fmt_value(abs(v), unit, currency)
    return f"{'+' if v >= 0 else '-'}{s}"


def fmt_pct(p: Optional[float]) -> str:
    return "n/a" if p is None else f"{p:+.1f}%"


# =========================================================================== periods
def parse_period(period: str, grain: str) -> date:
    """'YYYY-MM-DD' (any grain; weekly snaps to the Monday) or 'YYYY-Www' (weekly)."""
    p = (period or "").strip()
    try:
        if "-W" in p:
            y, w = p.split("-W", 1)
            return date.fromisocalendar(int(y), int(w[:2]), 1)
        d = date.fromisoformat(p[:10])
    except (ValueError, TypeError):
        raise FileValidationError("period must be 'YYYY-MM-DD' (or 'YYYY-Www' for weekly).", status_code=400)
    if grain == "weekly":
        d = d - timedelta(days=d.weekday())
    return d


def period_phrase(t: date, grain: str) -> str:
    return f"in the week of {t.isoformat()}" if grain == "weekly" else f"on {t.isoformat()}"


def period_step(grain: str) -> timedelta:
    return timedelta(days=7 if grain == "weekly" else 1)


def periods_between(start: date, end: date, grain: str) -> int:
    days = (end - start).days
    return max(0, math.ceil(days / 7)) if grain == "weekly" else max(0, days)


# =========================================================================== core maths (pure)
@dataclass
class GroupRow:
    label: str
    num_t: float = 0.0
    num_b: float = 0.0
    den_t: float = 0.0
    den_b: float = 0.0
    vol_t: float = 0.0
    vol_b: float = 0.0


def _f(v: Any) -> float:
    try:
        x = float(v)
        return 0.0 if math.isnan(x) else x
    except (TypeError, ValueError):
        return 0.0


def additive_parts(groups: List[GroupRow], n_periods: int, expected: Optional[float]) -> Tuple[List[Tuple[str, float, float, float]], float, float]:
    """-> ([(label, observed_k, expected_k, contrib_k)], expected_total, observed_total)."""
    n = max(1, n_periods)
    base = [g.num_b / n for g in groups]
    base_sum = sum(base)
    e_total = expected if expected is not None else base_sum
    scale = (e_total / base_sum) if base_sum > 0 else 0.0
    out = []
    for g, b in zip(groups, base):
        exp_k = b * scale
        out.append((g.label, g.num_t, exp_k, g.num_t - exp_k))
    if base_sum <= 0 and e_total:
        # no baseline mix at all: the whole expected value is unattributed
        out.append(("(no baseline activity)", 0.0, e_total, -e_total))
    return out, e_total, sum(g.num_t for g in groups)


def ratio_parts(groups: List[GroupRow], den_t: float, den_b: float) -> Tuple[List[Tuple[str, float, float, float]], Optional[float], Optional[float]]:
    """contrib_k = N1_k / D1 - N0_k / D0. -> (parts, R0, R1); a missing side contributes 0."""
    r1 = (sum(g.num_t for g in groups) / den_t) if den_t else None
    r0 = (sum(g.num_b for g in groups) / den_b) if den_b else None
    out = []
    for g in groups:
        o = g.num_t / den_t if den_t else 0.0
        e = g.num_b / den_b if den_b else 0.0
        out.append((g.label, o, e, o - e))
    return out, r0, r1


def explanatory_power(contribs: List[float], change: float) -> float:
    if abs(change) < 1e-9:
        return 0.0
    sign = 1.0 if change > 0 else -1.0
    aligned = sorted((max(0.0, sign * c) for c in contribs), reverse=True)[:POWER_TOP_K]
    return round(min(1.0, sum(aligned) / abs(change)), 4)


def mix_shift(parts: List[Tuple[str, float, float, float]]) -> float:
    """Total variation distance between the baseline mix (expected_k shares) and the observed mix (observed_k shares)."""
    # Long tails (e.g. hundreds of sellers with a few orders each) add sampling noise, so only the
    # MIX_TOP_GROUPS largest groups are compared individually and the rest form one "other" bucket.
    ranked = sorted(parts, key=lambda p: (-(abs(p[1]) + abs(p[2])), p[0]))
    head, tail = ranked[:MIX_TOP_GROUPS], ranked[MIX_TOP_GROUPS:]
    if tail:
        head = head + [("__other__", sum(abs(p[1]) for p in tail), sum(abs(p[2]) for p in tail), 0.0)]
    parts = head
    e_sum = sum(abs(p[2]) for p in parts)
    o_sum = sum(abs(p[1]) for p in parts)
    if e_sum <= 0 or o_sum <= 0:
        return 0.0
    return round(min(1.0, 0.5 * sum(abs(abs(p[1]) / o_sum - abs(p[2]) / e_sum) for p in parts)), 4)


def driver_sentence(dim_label: str, label: str, contrib: float, share: Optional[float], direction: str,
                    unit: str, currency: Optional[str]) -> str:
    amount = fmt_change(contrib, unit, currency)
    if share is None:
        return f"{dim_label} {label} contributed {amount}."
    if share >= 0:
        return f"{dim_label} {label} contributed {amount} ({share:.0f}% of the {direction})."
    return f"{dim_label} {label} moved the other way: {amount} (offsetting {abs(share):.0f}% of the {direction})."


def build_dimension(key: str, label: str, parts: List[Tuple[str, float, float, float]], start: float, end: float,
                    direction: str, unit: str, currency: Optional[str], join_path: Optional[str] = None,
                    residual: float = 0.0, start_name: str = "Expected") -> ExplainDimension:
    """Waterfall + driver list for one dimension. start + sum(contribs) + residual == end."""
    change = end - start
    sign = 1.0 if change >= 0 else -1.0
    ranked = sorted(parts, key=lambda p: (-abs(p[3]), p[0]))
    shown = sorted(ranked[:WATERFALL_DRIVERS], key=lambda p: (-sign * p[3], p[0]))
    other = sum(p[3] for p in ranked[WATERFALL_DRIVERS:]) + residual

    def share(c: float) -> Optional[float]:
        return round(c / change * 100.0, 1) if abs(change) > 1e-9 else None

    steps = [WaterfallStep(name=start_name, kind="total", start=0.0, end=round(start, 4), value=round(start, 4))]
    running = start
    for lbl, _o, _e, c in shown:
        steps.append(WaterfallStep(name=str(lbl), kind="up" if c >= 0 else "down", start=round(running, 4),
                                   end=round(running + c, 4), value=round(c, 4)))
        running += c
    if len(ranked) > WATERFALL_DRIVERS or abs(residual) > 1e-9:
        steps.append(WaterfallStep(name="All other", kind="other", start=round(running, 4),
                                   end=round(running + other, 4), value=round(other, 4)))
        running += other
    steps.append(WaterfallStep(name="Observed", kind="total", start=0.0, end=round(end, 4), value=round(end, 4)))

    listed = sorted(ranked[:LIST_DRIVERS], key=lambda p: (-sign * p[3], p[0]))
    drivers = [ExplainDriver(label=str(lbl), observed=round(o, 4), expected=round(e, 4), contribution=round(c, 4),
                             share_of_change_pct=share(c),
                             sentence=driver_sentence(label, str(lbl), c, share(c), direction, unit, currency))
               for lbl, o, e, c in listed]
    power = explanatory_power([p[3] for p in parts], change)
    top_n = min(POWER_TOP_K, len(parts))
    shift = mix_shift(parts)
    summary = (f"The top {top_n} {label.lower()} group{'s' if top_n != 1 else ''} explain {power * 100:.0f}% "
               f"of the {direction} ({len(parts)} groups in total). The {label.lower()} mix moved {shift * 100:.0f}% "
               + ("away from the usual mix, so the change is concentrated in particular groups."
                  if shift >= 0.15 else "from the usual mix, so the change is broad-based across groups."))
    return ExplainDimension(key=key, label=label, explanatory_power=power, mix_shift=shift,
                            rank_score=round(power * shift, 4), groups=len(parts), drivers=drivers,
                            other_contribution=round(other, 4), other_groups=max(0, len(ranked) - WATERFALL_DRIVERS),
                            waterfall=steps, summary=summary, join_path=join_path)


def volume_value_section(vol_t: float, vol_b: float, num_t: float, num_b: float, n_periods: int,
                         expected: Optional[float], volume_label: str, value_label: str,
                         unit: str, currency: Optional[str]) -> Optional[VolumeValue]:
    """Revenue = volume x value-per-unit. Baseline scaled to the headline expected like the waterfall."""
    n = max(1, n_periods)
    if vol_b <= 0 or vol_t <= 0:
        return None
    a0 = num_b / vol_b
    a1 = num_t / vol_t
    v0 = vol_b / n
    base_total = num_b / n
    if expected is not None and base_total > 0:
        v0 = v0 * (expected / base_total)
    vol_eff = (vol_t - v0) * a0
    val_eff = (a1 - a0) * vol_t
    dominant = "volume" if abs(vol_eff) >= abs(val_eff) else "value"
    s = [
        f"Volume: {fmt_value(vol_t, 'count')} {volume_label} vs {fmt_value(round(v0, 1), 'count')} expected, "
        f"worth {fmt_change(vol_eff, unit, currency)}.",
        f"Value: {value_label} {fmt_value(a1, unit, currency)} vs {fmt_value(a0, unit, currency)} in the baseline, "
        f"worth {fmt_change(val_eff, unit, currency)}.",
        ("Mostly a volume effect: more or fewer " + volume_label + " rather than a different " + value_label + ".")
        if dominant == "volume" else
        ("Mostly a value effect: the " + value_label + " changed more than the number of " + volume_label + "."),
    ]
    return VolumeValue(volume_label=volume_label, value_label=value_label, volume_observed=round(vol_t, 4),
                       volume_expected=round(v0, 4), value_observed=round(a1, 4), value_expected=round(a0, 4),
                       volume_effect=round(vol_eff, 4), value_effect=round(val_eff, 4), dominant=dominant, sentences=s)


def headline_section(observed: float, expected: float, direction: Optional[str], source: str, method: Optional[str],
                     severity: Optional[str], metric_label: str, period_label: str, unit: str,
                     currency: Optional[str]) -> ExplainHeadline:
    change = observed - expected
    pct = round(change / expected * 100.0, 1) if expected else None
    direction = direction or ("spike" if change >= 0 else "drop")
    source_txt = {"detector": "the detector's expected value", "time_series_baseline": "the rolling median baseline",
                  "trailing_baseline": f"the trailing {BASELINE_PERIODS}-period average"}[source]
    sentence = (f"{metric_label} was {fmt_value(observed, unit, currency)} {period_label} vs "
                f"{fmt_value(expected, unit, currency)} expected ({source_txt}): "
                f"{fmt_change(change, unit, currency)}" + (f", {fmt_pct(pct)}." if pct is not None else "."))
    return ExplainHeadline(observed=round(observed, 4), expected=round(expected, 4), change_abs=round(change, 4),
                           change_pct=pct, direction=direction, source=source, method=method, severity=severity,
                           sentence=sentence)


METHOD_PREFERENCE = {"rolling_zscore": 0, "stl_residual": 1, "isolation_forest": 2}


def find_detector_item(items, ts_points, target: date, grain: str):
    """-> (observed, expected, direction, source, method, severity) or None."""
    def same(p: str) -> bool:
        try:
            return parse_period(p, grain) == target
        except FileValidationError:
            return False
    hits = sorted([a for a in items if a.dimension == "overall" and same(a.period)],
                  key=lambda a: METHOD_PREFERENCE.get(a.method, 9))
    point = next((p for p in ts_points if same(p.period)), None)
    best = next((a for a in hits if a.method != "isolation_forest"), None)
    if best is not None:
        return best.observed, best.expected, best.direction, "detector", best.method, best.severity
    if point is not None:
        iso = hits[0] if hits else None
        return (point.observed, point.expected, iso.direction if iso else None, "time_series_baseline",
                iso.method if iso else None, iso.severity if iso else None)
    return None


def assemble(resp: AnomalyExplanationResponse, dims: List[Tuple[str, str, Optional[str], Any]],
             head: Optional[Tuple], totals: Optional[GroupRow], additive: bool, n_periods: int,
             volume_labels: Optional[Tuple[str, str]], period_label: str) -> AnomalyExplanationResponse:
    """dims: [(key, label, join_path, (ok, groups|reason, den_t, den_b))]. Fills headline, dimensions, top drivers."""
    unit, cur = resp.unit, resp.currency
    # ---- headline
    if head is not None:
        obs, exp_, direction, source, method, severity = head
        resp.headline = headline_section(obs, exp_, direction, source, method, severity, resp.metric_label,
                                         period_label, unit, cur)
    elif totals is not None:
        if additive:
            obs, exp_ = totals.num_t, totals.num_b / max(1, n_periods)
        else:
            obs = totals.num_t / totals.den_t if totals.den_t else 0.0
            exp_ = totals.num_b / totals.den_b if totals.den_b else 0.0
        resp.headline = headline_section(obs, exp_, None, "trailing_baseline", None, None, resp.metric_label,
                                         period_label, unit, cur)
        resp.notes.append("This period is not in the anomaly log for this metric; compared with the trailing average.")
    else:
        resp.section_errors["headline"] = "could not compute observed and expected values"
    direction = resp.headline.direction if resp.headline else "change"

    # ---- dimensions
    built: List[ExplainDimension] = []
    residual_noted = False
    for key, label, join_path, (ok, payload, den_t, den_b) in dims:
        if not ok:
            resp.skipped_dimensions.append(SkippedDimension(dimension=label, reason=str(payload)))
            continue
        groups: List[GroupRow] = payload
        if not groups:
            resp.skipped_dimensions.append(SkippedDimension(dimension=label, reason="no rows in the analysed window"))
            continue
        try:
            if additive:
                exp_total = resp.headline.expected if resp.headline else None
                parts, e_total, o_grouped = additive_parts(groups, n_periods, exp_total)
                o_total = resp.headline.observed if resp.headline else o_grouped
                residual = o_total - o_grouped
                if (not residual_noted and o_total and abs(residual) / abs(o_total) * 100 > RESIDUAL_NOTE_PCT):
                    resp.notes.append(f"The grouped totals differ from the headline observed value by "
                                      f"{fmt_change(residual, unit, cur)}; the difference is shown in 'All other'.")
                    residual_noted = True
                built.append(build_dimension(key, label, parts, e_total, o_total, direction, unit, cur, join_path, residual))
            else:
                parts, r0, r1 = ratio_parts(groups, den_t, den_b)
                if r0 is None or r1 is None:
                    resp.skipped_dimensions.append(SkippedDimension(dimension=label, reason="no rows in the target period or the baseline window"))
                    continue
                built.append(build_dimension(key, label, parts, r0, r1, "rise" if r1 >= r0 else "fall", unit, cur,
                                             join_path, start_name="Trailing avg"))
        except Exception as e:
            resp.skipped_dimensions.append(SkippedDimension(dimension=label, reason=_short(e)))
    built.sort(key=lambda d: (-d.rank_score, -d.explanatory_power, d.key))
    resp.dimensions = built
    if not additive and built:
        resp.notes.append(f"For averages and rates the waterfall runs from the trailing {BASELINE_PERIODS}-period level "
                          f"('Trailing avg') to the observed level, so it can differ from the headline's expected value.")
    if not built and "dimensions" not in resp.section_errors:
        resp.section_errors["dimensions"] = "no dimension could be analysed (see skipped dimensions)"

    # ---- top drivers: top 3 of the best dimension + the top driver of each other dimension
    tops: List[ExplainTopDriver] = []
    for i, d in enumerate(built):
        for drv in d.drivers[: (3 if i == 0 else 1)]:
            tops.append(ExplainTopDriver(dimension=d.label, label=drv.label, contribution=drv.contribution,
                                         share_of_change_pct=drv.share_of_change_pct, sentence=drv.sentence))
    resp.top_drivers = tops[:6]

    # ---- volume vs value
    if volume_labels is None:
        resp.section_errors.setdefault("volume_value", "only available for sum-type metrics (e.g. revenue)")
    elif totals is None:
        resp.section_errors.setdefault("volume_value", "totals query failed")
    else:
        vv = volume_value_section(totals.vol_t, totals.vol_b, totals.num_t, totals.num_b, n_periods,
                                  resp.headline.expected if resp.headline else None, volume_labels[0], volume_labels[1],
                                  unit, cur)
        if vv is None:
            resp.section_errors["volume_value"] = "no volume in the target period or the baseline window"
        else:
            resp.volume_value = vv
    return resp


# =========================================================================== Olist
_OLIST_CACHE: Dict[Tuple, Tuple[float, AnomalyExplanationResponse]] = {}
_OLIST_LOCK = threading.Lock()


def _olist_sql(dim: str, trunc: str, need_reviews: bool = True) -> str:
    """Fixed SQL (no user text). Bound params: :bs (window start), :we (window end, exclusive), :t (target period).
    need_reviews=False drops the review pre-aggregation (only avg_review_score needs it; it is the slowest part)."""
    fo = (
        "WITH fo AS ("
        f" SELECT o.order_id, o.customer_id, CAST(DATE_TRUNC('{trunc}', o.order_purchase_timestamp) AS DATE) AS p,"
        "  CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 1 ELSE 0 END AS on_time"
        " FROM insightforge.orders o"
        " WHERE o.order_status = 'delivered'"
        "  AND o.order_purchase_timestamp >= :bs AND o.order_purchase_timestamp < :we"
        "  AND o.order_purchase_timestamp >= '2017-01-01' AND o.order_purchase_timestamp < '2018-09-01')"
    )
    measures = (
        " SUM(r.rev) FILTER (WHERE r.p = :t) AS rev_t, SUM(r.rev) FILTER (WHERE r.p < :t) AS rev_b,"
        " COUNT(DISTINCT r.order_id) FILTER (WHERE r.p = :t AND r.n_items > 0) AS orders_t,"
        " COUNT(DISTINCT r.order_id) FILTER (WHERE r.p < :t AND r.n_items > 0) AS orders_b,"
        " SUM(r.on_time * r.n_items) FILTER (WHERE r.p = :t) AS ontime_t, SUM(r.on_time * r.n_items) FILTER (WHERE r.p < :t) AS ontime_b,"
        " SUM(r.n_items) FILTER (WHERE r.p = :t) AS items_t, SUM(r.n_items) FILTER (WHERE r.p < :t) AS items_b,"
        " SUM(r.score_sum) FILTER (WHERE r.p = :t) AS score_t, SUM(r.score_sum) FILTER (WHERE r.p < :t) AS score_b,"
        " SUM(r.score_n) FILTER (WHERE r.p = :t) AS scoren_t, SUM(r.score_n) FILTER (WHERE r.p < :t) AS scoren_b"
    )
    if OLIST_DIMENSIONS[dim]["level"] == "item":
        dim_expr = "COALESCE(pr.product_category_name_english, pr.product_category_name, 'unknown')" if dim == "category" else "oi.seller_id"
        rows = (
            ", r AS (SELECT fo.p, fo.order_id, fo.on_time, (oi.price + oi.freight_value) AS rev, 1 AS n_items,"
            " 0 AS score_sum, 0 AS score_n, " + dim_expr + " AS dim"
            " FROM fo JOIN insightforge.order_items oi ON oi.order_id = fo.order_id"
            + (" LEFT JOIN insightforge.products pr ON pr.product_id = oi.product_id" if dim == "category" else "") + ")"
        )
    else:
        dim_expr = "COALESCE(c.customer_state, 'unknown')" if dim == "state" else "COALESCE(pay.payment_type, 'unknown')"
        join = ("JOIN insightforge.customers c ON c.customer_id = fo.customer_id" if dim == "state" else
                "LEFT JOIN insightforge.order_payments pay ON pay.order_id = fo.order_id AND pay.payment_sequential = 1")
        rows = (
            ", it AS (SELECT oi.order_id, SUM(oi.price + oi.freight_value) AS rev, COUNT(*) AS n_items"
            "  FROM insightforge.order_items oi JOIN fo ON fo.order_id = oi.order_id GROUP BY oi.order_id)"
            + (", rv AS (SELECT rr.order_id, SUM(rr.review_score) AS score_sum, COUNT(rr.review_score) AS score_n"
               "  FROM insightforge.order_reviews rr JOIN fo ON fo.order_id = rr.order_id GROUP BY rr.order_id)"
               if need_reviews else "")
            + ", r AS (SELECT fo.p, fo.order_id, fo.on_time, it.rev, COALESCE(it.n_items, 0) AS n_items,"
            + (" rv.score_sum, rv.score_n, " if need_reviews else " 0 AS score_sum, 0 AS score_n, ")
            + dim_expr + " AS dim"
            " FROM fo LEFT JOIN it ON it.order_id = fo.order_id "
            + ("LEFT JOIN rv ON rv.order_id = fo.order_id " if need_reviews else "") + join + ")"
        )
    return fo + rows + " SELECT r.dim AS label, GROUPING(r.dim) AS is_total," + measures + " FROM r GROUP BY GROUPING SETS ((r.dim), ())"


OLIST_METRIC_FIELDS = {
    # metric -> (numerator field, denominator field or None)
    "gross_revenue": ("rev", None),
    "order_count": ("orders", None),
    "aov": ("rev", "orders"),
    "on_time_delivery_rate": ("ontime", "items"),
    "avg_review_score": ("score", "scoren"),
}


def olist_groups(rows: List[Dict[str, Any]], metric: str, dim: str) -> Tuple[List[GroupRow], GroupRow]:
    num, den = OLIST_METRIC_FIELDS[metric]
    mult = 100.0 if metric == "on_time_delivery_rate" else 1.0
    groups: List[GroupRow] = []
    total = GroupRow(label="__total__")
    for r in rows:
        g = GroupRow(
            label=str(r.get("label")) if r.get("label") is not None else "unknown",
            num_t=_f(r.get(f"{num}_t")) * mult, num_b=_f(r.get(f"{num}_b")) * mult,
            den_t=_f(r.get(f"{den}_t")) if den else 0.0, den_b=_f(r.get(f"{den}_b")) if den else 0.0,
            vol_t=_f(r.get("orders_t")), vol_b=_f(r.get("orders_b")),
        )
        if int(r.get("is_total") or 0) == 1:
            total = g
        else:
            if dim == "seller" and len(g.label) > 10:
                g.label = g.label[:8] + "..."
            groups.append(g)
    return groups, total


class OlistAnomalyExplainService:

    @staticmethod
    def _query(sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Read-only engine (5 s statement timeout). One retry: a cold remote DB can time out once."""
        for attempt in range(2):
            try:
                with readonly_engine.connect() as conn:
                    res = conn.execute(text(sql), params)
                    cols = list(res.keys())
                    return [dict(zip(cols, row)) for row in res.fetchall()]
            except Exception as e:
                if attempt == 0 and "statement timeout" in str(e):
                    continue
                raise
        return []

    @classmethod
    def clear_cache(cls) -> None:
        with _OLIST_LOCK:
            _OLIST_CACHE.clear()

    @classmethod
    def explain(cls, metric: str, period: str, grain: str = "daily") -> AnomalyExplanationResponse:
        if grain not in GRAINS:
            raise FileValidationError("grain must be 'daily' or 'weekly'.", status_code=400)
        notes: List[str] = []
        if metric == "multivariate_daily":
            notes.append("IsolationForest flags a combination of metrics; explaining gross revenue for that day.")
            metric = "gross_revenue"
        if metric not in OLIST_METRICS:
            raise FileValidationError(f"Unknown metric '{metric}'. Use one of: {', '.join(OLIST_METRICS)}.", status_code=400)
        t = parse_period(period, grain)
        if not (OLIST_FIRST_DAY - timedelta(days=6) <= t < OLIST_END_EXCL):
            raise FileValidationError("period is outside the Olist analysis range (2017-01-01 to 2018-08-31).", status_code=400)
        key = (metric, t.isoformat(), grain)
        with _OLIST_LOCK:
            hit = _OLIST_CACHE.get(key)
        if hit and time.time() - hit[0] < EXPLAIN_CACHE_TTL:
            r = hit[1].model_copy(update={"cached": True})
            return r
        resp = cls._compute(metric, t, grain, notes)
        with _OLIST_LOCK:
            _OLIST_CACHE[key] = (time.time(), resp)
        return resp

    @classmethod
    def _compute(cls, metric: str, t: date, grain: str, notes: List[str]) -> AnomalyExplanationResponse:
        from backend.app.services.anomaly_service import AnomalyService  # local import: keep module load light

        cfg = OLIST_METRICS[metric]
        step = period_step(grain)
        bs = max(t - step * BASELINE_PERIODS, OLIST_FIRST_DAY)
        we = min(t + step, OLIST_END_EXCL)
        n = periods_between(bs, t, grain)
        resp = AnomalyExplanationResponse(
            dataset_id=OLIST_ID, dataset_name="Olist E-Commerce (demo)", metric=metric, metric_label=cfg["label"],
            period=t.isoformat(), grain=grain, currency="R$", unit=cfg["unit"], additive=cfg["additive"],
            baseline_window=f"{bs.isoformat()} to {(t - timedelta(days=1)).isoformat()} ({n} {'weeks' if grain == 'weekly' else 'days'})",
            baseline_periods=n, notes=list(notes), generated_at=datetime.now(timezone.utc),
        )
        trunc = GRAINS[grain]
        params = {"bs": datetime.combine(bs, datetime.min.time()), "we": datetime.combine(we, datetime.min.time()), "t": t}
        tasks: Dict[str, Callable[[], Any]] = {
            "detector": lambda: AnomalyService.detect_all(grain=grain, metric=metric),
        }
        usable = [d for d, c in OLIST_DIMENSIONS.items() if c["level"] in cfg["levels"]]
        skipped = [d for d in OLIST_DIMENSIONS if d not in usable]
        live = not is_fixture_mode_allowed()
        if live:
            for d in usable:
                tasks[f"dim:{d}"] = (lambda d=d: cls._query(_olist_sql(d, trunc, need_reviews=(metric == "avg_review_score")), params))
        else:
            resp.section_errors["dimensions"] = "dimension breakdowns need the live database (fixture mode)"
        results = run_tasks(tasks)

        head = None
        ok, det = results.get("detector", (False, "not run"))
        if ok:
            head = find_detector_item(det.anomalies, det.time_series, t, grain)
        else:
            resp.notes.append(f"Anomaly detector unavailable: {det}")

        dims: List[Tuple[str, str, Optional[str], Any]] = []
        totals: Optional[GroupRow] = None
        for d in usable if live else []:
            label = OLIST_DIMENSIONS[d]["label"]
            ok, val = results.get(f"dim:{d}", (False, "not run"))
            if not ok:
                dims.append((d, label, None, (False, f"query failed: {val}", 0.0, 0.0)))
                continue
            groups, total = olist_groups(val, metric, d)
            if totals is None:
                totals = total  # every dimension query carries the same overall total row (GROUPING SETS ())
            dims.append((d, label, None, (True, groups, total.den_t, total.den_b)))
        for d in skipped:
            resp.skipped_dimensions.append(SkippedDimension(
                dimension=OLIST_DIMENSIONS[d]["label"],
                reason=("an order can contain items from several groups, so this metric would be double counted"
                        if OLIST_DIMENSIONS[d]["level"] == "item" else
                        "reviews belong to orders, not items, so they cannot be split by this dimension")))
        volume_labels = ("orders", "average order value") if metric == "gross_revenue" else None
        if head is None and totals is None:
            resp.section_errors["headline"] = "period not found in the anomaly series and the live database is unavailable"
        return assemble(resp, dims, head, totals, cfg["additive"], n, volume_labels, period_phrase(t, grain))


# =========================================================================== uploaded datasets
def _dataset_measure_parts(m: MeasureDefinition, col: str, cond: str) -> Optional[Dict[str, str]]:
    """SQL fragments for numerator / denominator / volume under a condition. None = not decomposable."""
    agg = m.aggregation.upper()
    if m.column is None:
        return {"num": f"COUNT(CASE WHEN {cond} THEN 1 END)"}
    if agg == "COUNT":
        return {"num": f"COUNT(CASE WHEN {cond} THEN {col} END)"}
    if agg == "SUM":
        return {"num": f"SUM(CASE WHEN {cond} THEN {col} END)", "vol": f"COUNT(CASE WHEN {cond} THEN 1 END)"}
    if agg == "AVG":
        return {"num": f"SUM(CASE WHEN {cond} THEN {col} END)", "den": f"COUNT(CASE WHEN {cond} THEN {col} END)"}
    return None


class DatasetAnomalyExplainService:

    @classmethod
    def explain(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str], period: str,
                grain: str = "daily") -> AnomalyExplanationResponse:
        if grain not in GRAINS:
            raise FileValidationError("grain must be 'daily' or 'weekly'.", status_code=400)
        t = parse_period(period, grain)
        return WorkspaceCache.get_or_compute("anomaly_explain", dataset_id, owner_token, (metric or "", t.isoformat(), grain),
                                             lambda: cls._compute(dataset_id, owner_token, metric, t, grain))

    @classmethod
    def _compute(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str], t: date,
                 grain: str) -> AnomalyExplanationResponse:
        from backend.app.services.dataset_anomaly_service import DatasetAnomalyService

        wc = load_context(dataset_id, owner_token)  # owner check: 403 / 404
        notes: List[str] = []
        if wc.model is None:
            raise FileValidationError(wc.model_error or "semantic model unavailable", status_code=400)
        by_key = {metric_key(m): m for m in wc.measures}
        if metric in (None, "", "multivariate_daily"):
            if metric == "multivariate_daily":
                notes.append("IsolationForest flags a combination of measures; explaining the main measure for that day.")
            chosen = wc.primary
        else:
            chosen = by_key.get(metric)
            if chosen is None:
                raise FileValidationError(f"Unknown metric '{metric}'.", status_code=400)
        if chosen is None:
            raise FileValidationError("No measure available in this dataset.", status_code=400)
        tc = DatasetDashboardService._time_column(wc.profile, wc.model, chosen.table)
        if tc is None:
            raise FileValidationError(f"Table '{chosen.table}' has no date/time column.", status_code=400)
        agg = chosen.aggregation.upper()
        additive = chosen.column is None or agg in ("SUM", "COUNT")
        label = chosen.name if chosen.column is not None else f"{chosen.table.replace('_', ' ').title()} Rows"
        step = period_step(grain)
        bs, we = t - step * BASELINE_PERIODS, t + step
        resp = AnomalyExplanationResponse(
            dataset_id=wc.profile.id, dataset_name=wc.profile.name, metric=metric_key(chosen), metric_label=label,
            period=t.isoformat(), grain=grain, currency=None,
            unit="count" if (chosen.column is None or agg == "COUNT") else "number", additive=additive,
            baseline_periods=BASELINE_PERIODS, notes=notes, generated_at=datetime.now(timezone.utc),
        )

        cand, colp = tc
        F, D, S = quote_ident("f"), quote_ident("d"), quote_ident(wc.profile.schema_name)
        tq = f"{F}.{quote_ident(cand.column)}"
        t_value = tq if any(k in colp.pg_type.upper() for k in TIME_TYPE_MARKERS) else f"NULLIF({tq}, '')::timestamp"
        P = f"CAST(DATE_TRUNC('{GRAINS[grain]}', {t_value}) AS DATE)"
        lit = lambda d: f"CAST('{d.isoformat()}' AS DATE)"  # noqa: E731  (date.isoformat() only)
        cond_t = f"{P} = {lit(t)}"
        cond_b = f"{P} >= {lit(bs)} AND {P} < {lit(t)}"
        where = f"{tq} IS NOT NULL AND {P} >= {lit(bs)} AND {P} < {lit(we)}"
        col = f"{F}.{quote_ident(chosen.column)}" if chosen.column is not None else ""
        pt, pb = _dataset_measure_parts(chosen, col, cond_t), _dataset_measure_parts(chosen, col, cond_b)

        def select_list() -> str:
            parts = [f"{pt['num']} AS num_t", f"{pb['num']} AS num_b"]
            for k in ("den", "vol"):
                if k in pt:
                    parts += [f"{pt[k]} AS {k}_t", f"{pb[k]} AS {k}_b"]
            return ", ".join(parts)

        fact = f"{S}.{quote_ident(chosen.table)} AS {F}"
        tasks: Dict[str, Callable[[], Any]] = {
            "detector": lambda: DatasetAnomalyService.get_anomalies(dataset_id, owner_token, metric=metric_key(chosen), grain=grain),
        }
        planned: List[Tuple[Any, Any]] = []
        if pt is None:
            resp.section_errors["dimensions"] = f"{agg} measures cannot be split into group contributions"
        else:
            tasks["totals"] = lambda: DatasetDashboardService._run(
                f"SELECT {select_list()}, MIN({P}) AS first_p FROM {fact} WHERE {where}", wc.ctx, wc.profile.schema_name)
            try:
                planned, skipped = DatasetDashboardService.plan_breakdowns(wc.profile, wc.model, chosen,
                                                                           max_breakdowns=MAX_DATASET_DIMENSIONS)
                resp.skipped_dimensions += [SkippedDimension(dimension=s.dimension, reason=s.reason) for s in skipped]
            except Exception as e:
                resp.section_errors["dimensions"] = _short(e)
            for i, (d, rel) in enumerate(planned):
                if rel is None:
                    dim_expr, from_sql = f"{F}.{quote_ident(d.column)}", fact
                else:
                    dim_expr = f"{D}.{quote_ident(d.column)}"
                    from_sql = (f"{fact} LEFT JOIN {S}.{quote_ident(d.table)} AS {D} "
                                f"ON {F}.{quote_ident(rel.child_column)} = {D}.{quote_ident(rel.parent_column)}")
                sql = f"SELECT CAST({dim_expr} AS TEXT) AS label, {select_list()} FROM {from_sql} WHERE {where} GROUP BY 1"
                tasks[f"dim:{i}"] = (lambda sql=sql: DatasetDashboardService._run(sql, wc.ctx, wc.profile.schema_name))
        results = run_tasks(tasks)

        head = None
        ok, det = results.get("detector", (False, "not run"))
        if ok:
            head = find_detector_item(det.anomalies, det.time_series, t, grain)
        else:
            resp.notes.append(f"Anomaly detector unavailable: {det}")

        totals: Optional[GroupRow] = None
        n = BASELINE_PERIODS
        ok, rows = results.get("totals", (False, None))
        if ok and rows:
            r = rows[0]
            totals = GroupRow(label="__total__", num_t=_f(r.get("num_t")), num_b=_f(r.get("num_b")),
                              den_t=_f(r.get("den_t")), den_b=_f(r.get("den_b")),
                              vol_t=_f(r.get("vol_t")), vol_b=_f(r.get("vol_b")))
            first = r.get("first_p")
            try:
                first_d = date.fromisoformat(str(first)[:10]) if first else None
            except ValueError:
                first_d = None
            if first_d and first_d > bs:
                n = max(1, periods_between(first_d, t, grain))
                resp.notes.append(f"The data starts on {first_d.isoformat()}, so the baseline uses {n} period(s).")
        elif pt is not None:
            resp.section_errors["totals"] = _short(Exception(str(rows))) if not ok else "no rows in the analysed window"
        resp.baseline_periods = n
        resp.baseline_window = (f"{(t - step * n).isoformat()} to {(t - timedelta(days=1)).isoformat()} "
                                f"({n} {'weeks' if grain == 'weekly' else 'days'})")

        dims: List[Tuple[str, str, Optional[str], Any]] = []
        for i, (d, rel) in enumerate(planned):
            ok, val = results.get(f"dim:{i}", (False, "not run"))
            join_path = None if rel is None else f"{chosen.table}.{rel.child_column} -> {d.table}.{rel.parent_column} (N:1)"
            if not ok:
                dims.append((f"{d.table}.{d.column}", d.name, join_path, (False, f"query failed: {val}", 0.0, 0.0)))
                continue
            groups = [GroupRow(label=str(r.get("label")) if r.get("label") is not None else "(blank)",
                               num_t=_f(r.get("num_t")), num_b=_f(r.get("num_b")),
                               den_t=_f(r.get("den_t")), den_b=_f(r.get("den_b"))) for r in val]
            if len(val) >= 500:
                resp.notes.append(f"{d.name}: only the first 500 groups were analysed (query row cap).")
            dims.append((f"{d.table}.{d.column}", d.name, join_path,
                         (True, groups, totals.den_t if totals else sum(g.den_t for g in groups),
                          totals.den_b if totals else sum(g.den_b for g in groups))))
        volume_labels = ("rows", f"average {label.lower()} per row") if (pt is not None and "vol" in pt) else None
        return assemble(resp, dims, head, totals, additive, n, volume_labels, period_phrase(t, grain))
