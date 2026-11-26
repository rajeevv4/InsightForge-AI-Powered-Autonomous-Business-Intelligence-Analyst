import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.exceptions import DatabaseUnavailableError
from backend.app.schemas.briefing import BriefingThresholds, MorningBriefingResponse, ThresholdAlert
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.data_quality_service import DataQualityService

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300.0
_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: Optional[Tuple[float, Dict[str, Any]]] = None


class BriefingService:
    """
    Deterministic Morning Briefing & Threshold Alert Evaluator.
    Zero LLM calls, zero background cron dependency; evaluates on-demand with a 5-minute metric snapshot cache.
    """

    @classmethod
    def clear_cache(cls) -> None:
        global _SNAPSHOT_CACHE
        with _CACHE_LOCK:
            _SNAPSHOT_CACHE = None

    @classmethod
    def _load_snapshot(cls) -> Tuple[Dict[str, Any], bool]:
        global _SNAPSHOT_CACHE
        now = time.monotonic()
        with _CACHE_LOCK:
            if _SNAPSHOT_CACHE and (now - _SNAPSHOT_CACHE[0]) < _CACHE_TTL_SECONDS:
                return _SNAPSHOT_CACHE[1], True

        kpis = AnalyticsService.fetch_canonical_kpis()
        trend = AnalyticsService.fetch_revenue_trend()
        delivery = AnalyticsService.fetch_delivery_performance()
        dq = DataQualityService.fetch_audit_summary()

        high_anomalies = 0
        total_anomalies = 0
        try:
            anom = AnomalyService.detect_all(grain="daily", metric="gross_revenue")
            total_anomalies = anom.anomalies_detected
            high_anomalies = sum(1 for a in anom.anomalies if str(a.severity).lower() == "high")
        except DatabaseUnavailableError:
            raise
        except Exception as e:
            logger.warning(f"Briefing anomaly check skipped: {e}")

        snapshot = {
            "kpis": kpis,
            "trend": trend,
            "delivery": delivery,
            "dq": dq,
            "high_anomalies": high_anomalies,
            "total_anomalies": total_anomalies,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with _CACHE_LOCK:
            _SNAPSHOT_CACHE = (now, snapshot)
        return snapshot, False

    @classmethod
    def build(cls, thresholds: Optional[BriefingThresholds] = None) -> MorningBriefingResponse:
        cfg = thresholds or BriefingThresholds()
        snap, was_cached = cls._load_snapshot()

        kpis = snap["kpis"]
        trend = snap["trend"]
        delivery = snap["delivery"]
        dq = snap["dq"]
        high_anomalies = int(snap["high_anomalies"])
        total_anomalies = int(snap["total_anomalies"])

        gross_rev = float(kpis.get("gross_revenue", 0.0))
        delivered_orders = int(kpis.get("delivered_orders", 0))
        aov = float(kpis.get("aov", 0.0))
        csat = float(kpis.get("csat", 0.0))

        # Delivery late share
        delayed_row = next((d for d in delivery if str(d.get("delivery_status", "")).lower() == "delayed"), None)
        late_pct = round(float(delayed_row.get("percentage", 0.0)) if delayed_row else 0.0, 2)

        # Latest MoM revenue change
        mom_pct = 0.0
        latest_month = "N/A"
        latest_rev = 0.0
        if len(trend) >= 2:
            prev = trend[-2]
            curr = trend[-1]
            latest_month = str(curr.get("month", "N/A"))[:10]
            latest_rev = float(curr.get("gross_revenue", 0.0))
            prev_rev = float(prev.get("gross_revenue", 0.0))
            if prev_rev > 0:
                mom_pct = round(((latest_rev - prev_rev) / prev_rev) * 100.0, 2)
        elif len(trend) == 1:
            latest_month = str(trend[0].get("month", "N/A"))[:10]
            latest_rev = float(trend[0].get("gross_revenue", 0.0))

        dq_status = str(dq.get("audit_status", "UNKNOWN"))

        # Evaluate deterministic threshold rules
        alerts: List[ThresholdAlert] = [
            ThresholdAlert(
                id="late_delivery",
                label="Late Delivery Rate",
                metric="late_delivery_pct",
                current_value=late_pct,
                threshold=cfg.max_late_delivery_pct,
                operator=">",
                triggered=late_pct > cfg.max_late_delivery_pct,
                severity="warning" if late_pct > cfg.max_late_delivery_pct else "ok",
                message=(
                    f"Delayed orders at {late_pct:.2f}% (exceeds {cfg.max_late_delivery_pct:.1f}% limit)."
                    if late_pct > cfg.max_late_delivery_pct
                    else f"Delayed orders at {late_pct:.2f}% (within {cfg.max_late_delivery_pct:.1f}% limit)."
                ),
            ),
            ThresholdAlert(
                id="min_csat",
                label="Customer Satisfaction (CSAT)",
                metric="csat",
                current_value=round(csat, 2),
                threshold=cfg.min_csat,
                operator="<",
                triggered=csat < cfg.min_csat,
                severity="warning" if csat < cfg.min_csat else "ok",
                message=(
                    f"Average CSAT is {csat:.2f}★ (below {cfg.min_csat:.2f}★ target)."
                    if csat < cfg.min_csat
                    else f"Average CSAT is {csat:.2f}★ (meets {cfg.min_csat:.2f}★ target)."
                ),
            ),
            ThresholdAlert(
                id="mom_revenue",
                label="Latest MoM Revenue Change",
                metric="mom_revenue_change_pct",
                current_value=mom_pct,
                threshold=cfg.min_mom_revenue_pct,
                operator="<",
                triggered=mom_pct < cfg.min_mom_revenue_pct,
                severity="critical" if mom_pct < cfg.min_mom_revenue_pct else "ok",
                message=(
                    f"Latest month ({latest_month}) revenue changed {mom_pct:+.2f}% (below {cfg.min_mom_revenue_pct:+.1f}% floor)."
                    if mom_pct < cfg.min_mom_revenue_pct
                    else f"Latest month ({latest_month}) revenue changed {mom_pct:+.2f}% (above {cfg.min_mom_revenue_pct:+.1f}% floor)."
                ),
            ),
            ThresholdAlert(
                id="high_anomalies",
                label="High-Severity Anomalies",
                metric="high_severity_anomalies",
                current_value=float(high_anomalies),
                threshold=float(cfg.max_high_anomalies),
                operator=">",
                triggered=high_anomalies > cfg.max_high_anomalies,
                severity="critical" if high_anomalies > cfg.max_high_anomalies else "ok",
                message=(
                    f"{high_anomalies} high-severity revenue anomalies detected (above {cfg.max_high_anomalies} limit)."
                    if high_anomalies > cfg.max_high_anomalies
                    else f"{high_anomalies} high-severity anomalies (within {cfg.max_high_anomalies} limit)."
                ),
            ),
        ]

        triggered_count = sum(1 for a in alerts if a.triggered)
        headline = (
            f"{triggered_count} threshold alert{'s' if triggered_count != 1 else ''} active · "
            f"Cumulative Gross Revenue R$ {gross_rev:,.2f} across {delivered_orders:,} delivered orders."
            if triggered_count > 0
            else f"All {len(alerts)} monitored thresholds healthy · Cumulative Gross Revenue R$ {gross_rev:,.2f}."
        )

        bullets = [
            f"Latest full/recorded month ({latest_month}) generated R$ {latest_rev:,.2f} ({mom_pct:+.2f}% MoM) with overall AOV of R$ {aov:,.2f}.",
            f"Delivery SLA: {late_pct:.2f}% of delivered orders were delayed; overall CSAT stands at {csat:.2f} / 5.00.",
            f"Statistical monitoring detected {total_anomalies} revenue anomalies ({high_anomalies} high-severity).",
            f"Data Quality integrity audit status: {dq_status}.",
        ]

        return MorningBriefingResponse(
            headline=headline,
            bullets=bullets,
            alerts=alerts,
            triggered_count=triggered_count,
            thresholds=cfg,
            generated_at=snap["generated_at"],
            cached=was_cached,
        )
