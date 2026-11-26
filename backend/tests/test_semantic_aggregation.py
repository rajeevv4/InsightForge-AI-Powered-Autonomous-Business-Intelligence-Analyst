"""
Unit tests for default measure aggregation in the dataset semantic layer
and primary-measure selection for Quick Insights charts.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_semantic_aggregation
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.app.schemas.dataset import ColumnProfile, DatasetProfile, TableProfile
from backend.app.schemas.dataset_semantic import MeasureDefinition
from backend.app.services.dataset_insights_service import select_main_measure
from backend.app.services.dataset_semantic_service import DatasetSemanticService, pick_default_aggregation


class TestPickDefaultAggregation(unittest.TestCase):
    """Column name -> default aggregation."""

    def test_new_avg_keywords(self):
        self.assertEqual(pick_default_aggregation("customer_rating"), "AVG")
        self.assertEqual(pick_default_aggregation("delivery_days"), "AVG")
        self.assertEqual(pick_default_aggregation("discount_percent"), "AVG")
        self.assertEqual(pick_default_aggregation("unit_price"), "AVG")

    def test_totals_stay_sum(self):
        self.assertEqual(pick_default_aggregation("total_amount"), "SUM")
        self.assertEqual(pick_default_aggregation("quantity"), "SUM")
        self.assertEqual(pick_default_aggregation("revenue"), "SUM")
        self.assertEqual(pick_default_aggregation("sales_amount"), "SUM")
        self.assertEqual(pick_default_aggregation("order_amount"), "SUM")
        self.assertEqual(pick_default_aggregation("total_days"), "SUM")  # guard on added keywords

    def test_original_keywords_unchanged(self):
        self.assertEqual(pick_default_aggregation("score"), "AVG")
        self.assertEqual(pick_default_aggregation("marks"), "AVG")
        self.assertEqual(pick_default_aggregation("conversion_rate"), "AVG")
        self.assertEqual(pick_default_aggregation("duration_mins"), "AVG")
        self.assertEqual(pick_default_aggregation("credit_limit"), "SUM")


def _profile_with(columns):
    table = TableProfile(
        id="tbl-1", original_name="sales.csv", safe_name="sales", row_count=10,
        column_count=len(columns) + 1, candidate_pk="sale_id", candidate_time_column="sale_date",
        quality_findings=[],
        columns=[
            ColumnProfile(original_name="sale_id", safe_name="sale_id", pg_type="INT", role="id", distinct_count=10),
            ColumnProfile(original_name="sale_date", safe_name="sale_date", pg_type="TIMESTAMP", role="datetime", distinct_count=10),
        ] + [ColumnProfile(original_name=c, safe_name=c, pg_type="NUMERIC(10,2)", role="measure", distinct_count=10) for c in columns],
    )
    return DatasetProfile(
        id="ds-agg-1", name="Agg Test", schema_name="ds_00aa11bb", status="ready", share_samples=False,
        source_files=["sales.csv"], size_bytes=100, created_at=datetime.now(timezone.utc), expires_at=None,
        is_demo=False, tables=[table], relationships=[],
    )


class TestSemanticDraftAggregations(unittest.TestCase):
    """The drafted semantic model uses the new rule end-to-end."""

    @patch("backend.app.services.dataset_semantic_service.DatasetService.get_dataset_profile")
    @patch("backend.app.services.dataset_semantic_service.is_fixture_mode", return_value=True)
    def test_draft_measure_aggregations(self, _fixture, mock_profile):
        cols = ["customer_rating", "delivery_days", "discount_percent", "unit_price", "total_amount", "quantity", "score"]
        mock_profile.return_value = _profile_with(cols)
        draft = DatasetSemanticService.generate_draft("ds-agg-1")
        aggs = {m.column: m.aggregation for m in draft.semantic_model.measures if m.column}
        self.assertEqual(aggs, {
            "customer_rating": "AVG", "delivery_days": "AVG", "discount_percent": "AVG", "unit_price": "AVG",
            "total_amount": "SUM", "quantity": "SUM", "score": "AVG",
        })


def _m(col, agg):
    return MeasureDefinition(name=col, safe_name=f"t_{col}", table="t", column=col, aggregation=agg,
                             formula=f"{agg}(t.{col})", description="", synonyms=[])


class TestSelectMainMeasure(unittest.TestCase):
    """Quick Insights prefers a revenue/amount-like SUM measure."""

    def test_prefers_amount_sum_over_first_measure(self):
        measures = [_m("customer_rating", "AVG"), _m("quantity", "SUM"), _m("total_amount", "SUM")]
        self.assertEqual(select_main_measure(measures).column, "total_amount")

    def test_avg_price_is_not_preferred(self):
        measures = [_m("quantity", "SUM"), _m("unit_price", "AVG")]
        self.assertEqual(select_main_measure(measures).column, "quantity")

    def test_falls_back_to_first_measure(self):
        measures = [_m("customer_rating", "AVG"), _m("delivery_days", "AVG")]
        self.assertEqual(select_main_measure(measures).column, "customer_rating")


if __name__ == "__main__":
    unittest.main()
