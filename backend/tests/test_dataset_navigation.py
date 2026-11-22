"""
Unit tests for GET /api/datasets/{id}/navigation (dataset-aware sidebar rules).
Hermetic: profile and semantic model are mocked.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_navigation
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.dataset import ColumnProfile, DatasetProfile, TableProfile
from backend.app.schemas.dataset_semantic import DatasetSemanticResponse, DimensionDefinition, SemanticModel
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_navigation_service import (
    NAV_GROUP_KEYWORDS,
    DatasetNavigationService,
    keyword_matches,
    table_label,
)

MOD = "backend.app.services.dataset_navigation_service"


def _table(name, cols, pg_type="TEXT"):
    return TableProfile(
        id=f"t-{name}", original_name=f"{name}.csv", safe_name=name, row_count=10, column_count=len(cols),
        candidate_pk=cols[0], candidate_time_column=None, quality_findings=[],
        columns=[ColumnProfile(original_name=c, safe_name=c, pg_type=pg_type, role="dimension", distinct_count=5) for c in cols],
    )


def indian_shop_profile() -> DatasetProfile:
    return DatasetProfile(
        id="ds-nav-1", name="Indian Shop", schema_name="ds_1a2b3c4d", status="ready", share_samples=False,
        source_files=["customers.csv", "products.csv", "orders.csv"], size_bytes=1,
        created_at=datetime.now(timezone.utc), expires_at=None, is_demo=False, relationships=[],
        tables=[
            _table("customers", ["customer_id", "customer_name", "city", "state", "signup_date", "is_prime_member"]),
            _table("products", ["product_id", "product_name", "category", "unit_price"]),
            _table("orders", ["order_id", "customer_id", "product_id", "order_date", "quantity", "discount_percent",
                              "total_amount", "payment_method", "order_status", "delivery_days", "customer_rating"]),
        ],
    )


def _semantic(dims) -> DatasetSemanticResponse:
    now = datetime.now(timezone.utc)
    return DatasetSemanticResponse(
        dataset_id="ds-nav-1", status="draft", created_at=now, updated_at=now, starter_questions=[],
        semantic_model=SemanticModel(dataset_id="ds-nav-1", dataset_name="Indian Shop", measures=[], time_columns=[],
                                     dimensions=dims),
    )


def _dim(table, column, synonyms=None):
    return DimensionDefinition(name=column.replace("_", " ").title(), safe_name=f"{table}_{column}", table=table,
                               column=column, data_type="TEXT", synonyms=synonyms or [])


class TestKeywordMatching(unittest.TestCase):

    def test_whole_token_matches(self):
        self.assertTrue(keyword_matches("city", "city"))
        self.assertTrue(keyword_matches("customer_city", "city"))
        self.assertTrue(keyword_matches("payment_method", "payment"))
        self.assertTrue(keyword_matches("Payment Method", "method"))
        self.assertTrue(keyword_matches("installments", "installment"))  # plural
        self.assertTrue(keyword_matches("supplier_name", "supplier"))
        self.assertTrue(keyword_matches("zip_code", "zip"))
        self.assertTrue(keyword_matches("avg_lead_time_days", "lead_time"))  # multi-token keyword

    def test_no_substring_false_positives(self):
        self.assertFalse(keyword_matches("capacity", "city"))
        self.assertFalse(keyword_matches("statement_date", "state"))
        self.assertFalse(keyword_matches("real_estate", "state"))
        self.assertFalse(keyword_matches("model_number", "mode"))
        self.assertFalse(keyword_matches("methodology", "method"))
        self.assertFalse(keyword_matches("lead_owner", "lead_time"))
        self.assertFalse(keyword_matches("time_lead", "lead_time"))

    def test_keyword_constant_is_complete(self):
        self.assertEqual(set(NAV_GROUP_KEYWORDS), {"geography", "sellers", "payments", "delivery"})
        self.assertEqual(NAV_GROUP_KEYWORDS["geography"]["keywords"],
                         ["city", "state", "country", "region", "district", "pincode", "zip", "location"])

    def test_table_label(self):
        self.assertEqual(table_label("orders"), "Orders")
        self.assertEqual(table_label("retail_customers"), "Retail Customers")


class TestBuildNavigation(unittest.TestCase):

    def test_indian_shop_rules(self):
        nav = DatasetNavigationService.build_navigation(indian_shop_profile(), dimension_names=None)
        keys = [i.key for i in nav.items]
        self.assertEqual(keys, [
            "overview", "datasets", "ask", "analytics",
            "table:customers", "table:products", "table:orders",
            "geography", "payments", "delivery",
            "data_quality", "anomalies", "forecast", "report",
        ])
        by_key = {i.key: i for i in nav.items}
        self.assertEqual(by_key["geography"].matched_columns, ["customers.city", "customers.state"])
        self.assertEqual(by_key["payments"].matched_columns, ["orders.payment_method"])
        self.assertEqual(by_key["delivery"].matched_columns, ["orders.delivery_days"])
        self.assertEqual(by_key["table:orders"].path, "/tables/orders")
        self.assertEqual(by_key["table:orders"].label, "Orders")
        self.assertEqual([h.key for h in nav.hidden], ["sellers"])
        self.assertIn("seller", nav.hidden[0].reason)

    def test_core_items_always_present_even_without_matches(self):
        p = indian_shop_profile()
        p.tables = [_table("readings", ["reading_id", "sensor_value"])]
        nav = DatasetNavigationService.build_navigation(p, dimension_names=None)
        self.assertEqual([i.key for i in nav.items],
                         ["overview", "datasets", "ask", "analytics", "table:readings", "data_quality", "anomalies", "forecast", "report"])
        self.assertEqual({h.key for h in nav.hidden}, {"geography", "sellers", "payments", "delivery"})

    def test_geography_from_semantic_synonym(self):
        p = indian_shop_profile()
        p.tables = [_table("stores", ["store_id", "area_name"])]
        nav = DatasetNavigationService.build_navigation(
            p, dimension_names={"stores.area_name": ["area_name", "Area Name", "region"]})
        self.assertIn("geography", [i.key for i in nav.items])

    def test_numeric_pincode_column_still_counts_for_geography(self):
        p = indian_shop_profile()
        p.tables = [_table("shops", ["shop_id", "pincode"], pg_type="INTEGER")]
        nav = DatasetNavigationService.build_navigation(p, dimension_names={})  # pincode is not a semantic dimension
        self.assertIn("geography", [i.key for i in nav.items])

    def test_sellers_shown_when_vendor_column_exists(self):
        p = indian_shop_profile()
        p.tables[1] = _table("products", ["product_id", "vendor_name", "category"])
        nav = DatasetNavigationService.build_navigation(p, dimension_names=None)
        self.assertIn("sellers", [i.key for i in nav.items])


class TestGetNavigation(unittest.TestCase):

    def tearDown(self):
        patch.stopall()

    def test_uses_semantic_dimensions(self):
        patch(f"{MOD}.DatasetService.get_dataset_profile", return_value=indian_shop_profile()).start()
        patch(f"{MOD}.DatasetSemanticService.get_semantic",
              return_value=_semantic([_dim("customers", "city"), _dim("orders", "payment_method")])).start()
        nav = DatasetNavigationService.get_navigation("ds-nav-1", owner_token="tok")
        self.assertTrue(nav.semantic_model_used)
        self.assertIn("geography", [i.key for i in nav.items])

    def test_semantic_failure_falls_back_to_columns(self):
        patch(f"{MOD}.DatasetService.get_dataset_profile", return_value=indian_shop_profile()).start()
        patch(f"{MOD}.DatasetSemanticService.get_semantic", side_effect=RuntimeError("semantic down")).start()
        nav = DatasetNavigationService.get_navigation("ds-nav-1", owner_token="tok")
        self.assertFalse(nav.semantic_model_used)
        self.assertEqual([h.key for h in nav.hidden], ["sellers"])

    def test_demo_dataset_rejected(self):
        demo = indian_shop_profile()
        demo.is_demo, demo.schema_name = True, "insightforge"
        patch(f"{MOD}.DatasetService.get_dataset_profile", return_value=demo).start()
        with self.assertRaises(FileValidationError) as ctx:
            DatasetNavigationService.get_navigation("00000000-0000-0000-0000-000000000001")
        self.assertEqual(ctx.exception.status_code, 400)


class TestNavigationEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

        def _owner_checked(dataset_id, owner_token=None):
            if owner_token != "right-token":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return indian_shop_profile()
        patch(f"{MOD}.DatasetService.get_dataset_profile", side_effect=_owner_checked).start()
        patch(f"{MOD}.DatasetSemanticService.get_semantic", return_value=_semantic([])).start()

    def tearDown(self):
        patch.stopall()

    def test_wrong_token_403(self):
        res = self.client.get("/api/datasets/ds-nav-1/navigation", headers={"X-Owner-Token": "wrong"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json()["detail"])

    def test_missing_token_403(self):
        self.assertEqual(self.client.get("/api/datasets/ds-nav-1/navigation").status_code, 403)

    def test_right_token_200_shape(self):
        res = self.client.get("/api/datasets/ds-nav-1/navigation", headers={"X-Owner-Token": "right-token"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body), {"dataset_id", "dataset_name", "items", "hidden", "semantic_model_used"})
        self.assertEqual(set(body["items"][0]), {"key", "label", "path", "kind", "table", "matched_columns"})

    def test_fixture_mode_503(self):
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=True).start()
        res = self.client.get("/api/datasets/ds-nav-1/navigation", headers={"X-Owner-Token": "right-token"})
        self.assertEqual(res.status_code, 503)


if __name__ == "__main__":
    unittest.main()
