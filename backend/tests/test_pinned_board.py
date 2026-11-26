from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.text_to_sql_service import TextToSQLService

client = TestClient(app)


def test_rerun_olist_sql_rejects_unsafe_sql():
    resp = client.post(
        "/api/ai/rerun",
        json={"route": "text_to_sql", "sql": "DROP TABLE insightforge.orders;"},
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


def test_rerun_olist_sql_executes_valid_select():
    with patch.object(
        TextToSQLService,
        "execute_guarded_sql",
        return_value=([{"total_orders": 96478}], ["total_orders"]),
    ):
        resp = client.post(
            "/api/ai/rerun",
            json={
                "route": "text_to_sql",
                "sql": "SELECT COUNT(*) AS total_orders FROM orders WHERE order_status = 'delivered' LIMIT 10",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["total_orders"] == 96478


def test_rerun_olist_intent_valid_and_invalid():
    resp_bad = client.post(
        "/api/ai/rerun",
        json={"route": "intent", "intent": "nonexistent_intent"},
    )
    assert resp_bad.status_code == 400

    with patch(
        "backend.app.services.ai_analytics_router.AIAnalyticsRouter.route_intent",
        return_value={"data": [{"category": "health_beauty", "revenue": 1234.5}]},
    ):
        resp_ok = client.post(
            "/api/ai/rerun",
            json={"route": "intent", "intent": "category_analysis"},
        )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["row_count"] == 1


def test_rerun_dataset_expired_returns_404():
    with patch("backend.app.routers.datasets._check_live_db"), \
         patch(
             "backend.app.services.dataset_service.DatasetService.get_dataset_profile",
             side_effect=FileValidationError("Dataset not found or expired.", status_code=404),
         ):
        resp = client.post(
            "/api/datasets/missing-ds-123/rerun",
            json={"route": "text_to_sql", "sql": "SELECT * FROM sales LIMIT 5"},
            headers={"X-Owner-Token": "own_test"},
        )
    assert resp.status_code == 404
    assert "expired" in resp.json()["detail"].lower()
