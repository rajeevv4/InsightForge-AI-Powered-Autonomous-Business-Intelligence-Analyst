"""
Cross-cutting tests for every dataset-aware endpoint added for the workspace pages:
owner isolation (token A can never read dataset B), 404 handling, demo rejection,
no LLM involvement, and the Olist snapshot baseline files.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_workspace_isolation
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.limiter import limiter
from backend.app.main import app
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.dataset_workspace_service import WorkspaceCache
from backend.tests.test_dataset_dashboard import _fake_rows, _profile, _semantic

OWNERS = {"ds-A": "tok-A", "ds-B": "tok-B"}

# (method, path template) for EVERY new dataset endpoint
NEW_ENDPOINTS = [
    ("get", "/api/datasets/{id}/navigation"),
    ("get", "/api/datasets/{id}/dashboard"),
    ("get", "/api/datasets/{id}/overview"),
    ("get", "/api/datasets/{id}/analytics"),
    ("get", "/api/datasets/{id}/analytics?metric=orders.customer_rating&grain=weekly"),
    ("get", "/api/datasets/{id}/tables/orders/analysis"),
    ("get", "/api/datasets/{id}/groups/geography/analysis"),
    ("get", "/api/datasets/{id}/data-quality"),
    ("get", "/api/datasets/{id}/anomalies"),
    ("post", "/api/datasets/{id}/anomalies/scan"),
]


def _owner_checked(dataset_id, owner_token=None):
    if dataset_id not in OWNERS:
        raise FileValidationError("Dataset not found.", status_code=404)
    if owner_token != OWNERS[dataset_id]:
        raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
    p = _profile()
    p.id = dataset_id
    return p


class TestWorkspaceIsolation(unittest.TestCase):

    def setUp(self):
        WorkspaceCache.invalidate()
        limiter.reset()
        self.client = TestClient(app)
        self.semantic_calls = []

        def _semantic_spy(dataset_id, owner_token=None, **kwargs):
            self.semantic_calls.append(kwargs)
            _owner_checked(dataset_id, owner_token)
            return _semantic()

        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()
        patch.object(DatasetService, "get_dataset_profile", side_effect=_owner_checked).start()
        patch.object(DatasetSemanticService, "get_semantic", side_effect=_semantic_spy).start()
        patch("backend.app.services.dataset_dashboard_service.DatasetInsightsService.execute_guarded_sql_in_schema",
              side_effect=lambda sql, schema: _fake_rows(sql)).start()
        # Any LLM use would go through these; they must never be touched by the workspace pages.
        self.genai = MagicMock(side_effect=AssertionError("LLM must not be called"))
        patch("backend.app.services.dataset_semantic_service.genai", self.genai).start()
        patch("backend.app.services.ai_service.AIService._get_genai_client",
              side_effect=AssertionError("LLM must not be called")).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()
        limiter.reset()

    def call(self, method, path, dataset_id, token):
        headers = {"X-Owner-Token": token} if token else {}
        return getattr(self.client, method)(path.format(id=dataset_id), headers=headers)

    def test_token_A_cannot_read_dataset_B_on_any_new_endpoint(self):
        for method, path in NEW_ENDPOINTS:
            r = self.call(method, path, "ds-B", "tok-A")
            self.assertEqual(r.status_code, 403, f"{method.upper()} {path}: {r.text[:120]}")
            self.assertIn("Access denied", r.json()["detail"])

    def test_missing_token_is_403_everywhere(self):
        for method, path in NEW_ENDPOINTS:
            self.assertEqual(self.call(method, path, "ds-A", None).status_code, 403, path)

    def test_owner_gets_200_everywhere(self):
        for method, path in NEW_ENDPOINTS:
            r = self.call(method, path, "ds-A", "tok-A")
            self.assertEqual(r.status_code, 200, f"{method.upper()} {path}: {r.text[:200]}")

    def test_cached_answer_for_A_is_never_served_to_B_owner(self):
        for method, path in NEW_ENDPOINTS:
            self.assertEqual(self.call(method, path, "ds-A", "tok-A").status_code, 200, path)
        for method, path in NEW_ENDPOINTS:
            self.assertEqual(self.call(method, path, "ds-A", "tok-B").status_code, 403, path)

    def test_unknown_dataset_is_404(self):
        for method, path in NEW_ENDPOINTS:
            self.assertEqual(self.call(method, path, "ds-nope", "tok-A").status_code, 404, path)

    def test_no_llm_and_semantic_model_loaded_deterministically(self):
        for method, path in NEW_ENDPOINTS:
            self.call(method, path, "ds-A", "tok-A")
        self.genai.assert_not_called()
        self.assertTrue(self.semantic_calls)
        self.assertTrue(all(kw.get("allow_llm") is False for kw in self.semantic_calls), self.semantic_calls)

    def test_responses_have_no_currency_assumption(self):
        for method, path in NEW_ENDPOINTS:
            body = self.call(method, path, "ds-A", "tok-A").text
            self.assertNotIn("R$", body, path)
            self.assertNotIn("BRL", body, path)


class TestOlistSnapshotBaseline(unittest.TestCase):
    """The byte-for-byte Olist baseline used by scripts/diff_olist_snapshots.py must stay intact."""

    def test_snapshot_files_present_and_valid(self):
        root = Path(__file__).resolve().parent / "snapshots" / "olist_before"
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "diff_olist_snapshots", Path(__file__).resolve().parents[2] / "scripts" / "diff_olist_snapshots.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(len(mod.ENDPOINTS), 9)
        for name in mod.ENDPOINTS:
            raw = (root / f"{name}.json").read_bytes()
            self.assertTrue(raw)
            json.loads(raw)
        kpis = json.loads((root / "kpis.json").read_bytes())
        self.assertAlmostEqual(kpis["gross_revenue"], 15419773.75, places=2)


if __name__ == "__main__":
    unittest.main()
