from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.briefing_service import BriefingService

client = TestClient(app)


def _mock_snapshot_sources():
    kpis = {
        "gross_revenue": 15419773.75,
        "delivered_orders": 96478,
        "aov": 159.83,
        "csat": 4.16,
    }
    trend = [
        {"month": "2018-07-01", "gross_revenue": 1000000.0},
        {"month": "2018-08-01", "gross_revenue": 800000.0},  # -20% MoM
    ]
    delivery = [
        {"delivery_status": "On-Time", "percentage": 91.88},
        {"delivery_status": "Delayed", "percentage": 8.12},
    ]
    dq = {"audit_status": "PASS"}
    anom = SimpleNamespace(
        anomalies_detected=3,
        anomalies=[SimpleNamespace(severity="high"), SimpleNamespace(severity="low")],
    )
    return kpis, trend, delivery, dq, anom


def test_briefing_default_thresholds_triggers_alerts():
    BriefingService.clear_cache()
    kpis, trend, delivery, dq, anom = _mock_snapshot_sources()

    with patch("backend.app.services.briefing_service.AnalyticsService.fetch_canonical_kpis", return_value=kpis), \
         patch("backend.app.services.briefing_service.AnalyticsService.fetch_revenue_trend", return_value=trend), \
         patch("backend.app.services.briefing_service.AnalyticsService.fetch_delivery_performance", return_value=delivery), \
         patch("backend.app.services.briefing_service.DataQualityService.fetch_audit_summary", return_value=dq), \
         patch("backend.app.services.briefing_service.AnomalyService.detect_all", return_value=anom):
        resp = client.get("/api/briefing")

    assert resp.status_code == 200
    data = resp.json()
    assert data["triggered_count"] == 4
    assert len(data["bullets"]) == 4
    assert data["cached"] is False

    # Second call with relaxed thresholds should hit the 5-minute snapshot cache and show 0 alerts
    resp2 = client.post(
        "/api/briefing",
        json={
            "max_late_delivery_pct": 15.0,
            "min_csat": 3.5,
            "min_mom_revenue_pct": -30.0,
            "max_high_anomalies": 5,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["triggered_count"] == 0
