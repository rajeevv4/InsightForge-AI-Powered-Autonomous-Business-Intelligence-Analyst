import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.forecast_service import OlistForecastService

client = TestClient(app)


def test_scenario_baseline_fixture_mode():
    OlistForecastService.clear_cache()
    with patch.dict(os.environ, {"USE_FIXTURES": "1"}):
        resp = client.get("/api/forecast/scenario-baseline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["on_time_orders"] > data["late_orders"]
    assert data["observed_review_gap"] == round(data["on_time_avg_review"] - data["late_avg_review"], 2)
    assert "not proven causation" in data["disclaimer"].lower()
