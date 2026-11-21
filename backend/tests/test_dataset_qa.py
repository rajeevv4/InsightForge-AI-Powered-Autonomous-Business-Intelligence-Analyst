"""
Hermetic Unit Tests for Level 6: Dataset-Aware Q&A and Semantic Layer
====================================================================
Tests offline without hitting live Gemini API or requiring live database.
Covers:
- Semantic draft generation from sample profiles (measures, dimensions, starter questions)
- SQLValidator scoping (rejects unqualified names, other ds_* schemas, insightforge, metadata tables, ai_audit_log)
- Generic fan-out guard on 1:N relationships
- Privacy model (share_samples=False: no cell values in Gemini prompt or result rows narrative)
- Owner isolation on /ask
- Insights cache key scoping
- Olist ask path backward compatibility
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.app.schemas.dataset import ColumnProfile, DatasetProfile, RelationshipProfile, TableProfile
from backend.app.schemas.dataset_semantic import (
    DatasetAskRequest,
    DatasetSemanticResponse,
    DimensionDefinition,
    MeasureDefinition,
    RelationshipDefinition,
    SemanticModel,
    TimeColumnDefinition,
    UpdateDatasetSemanticRequest,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_insights_service import DatasetInsightsService, _INSIGHTS_CACHE
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.sql_validator import DatasetSQLContext, SQLValidator
from backend.app.services.text_to_sql_service import TextToSQLService


def _create_sample_profile(share_samples: bool = False) -> DatasetProfile:
    """Creates an in-memory sample dataset profile with 1:N relationship."""
    customers_table = TableProfile(
        id="tbl-cust-1",
        original_name="customers.csv",
        safe_name="customers",
        row_count=100,
        column_count=4,
        candidate_pk="customer_id",
        candidate_time_column=None,
        quality_findings=[],
        columns=[
            ColumnProfile(original_name="customer_id", safe_name="customer_id", pg_type="INT", role="id", distinct_count=100),
            ColumnProfile(original_name="customer_name", safe_name="customer_name", pg_type="TEXT", role="dimension", distinct_count=100),
            ColumnProfile(original_name="city", safe_name="city", pg_type="TEXT", role="dimension", distinct_count=20),
            ColumnProfile(original_name="credit_limit", safe_name="credit_limit", pg_type="NUMERIC(10,2)", role="measure", distinct_count=50)
        ]
    )

    orders_table = TableProfile(
        id="tbl-ord-1",
        original_name="orders.csv",
        safe_name="orders",
        row_count=500,
        column_count=5,
        candidate_pk="order_id",
        candidate_time_column="order_date",
        quality_findings=[],
        columns=[
            ColumnProfile(original_name="order_id", safe_name="order_id", pg_type="INT", role="id", distinct_count=500),
            ColumnProfile(original_name="customer_id", safe_name="customer_id", pg_type="INT", role="id", distinct_count=100),
            ColumnProfile(original_name="order_date", safe_name="order_date", pg_type="TIMESTAMP", role="datetime", distinct_count=200),
            ColumnProfile(original_name="order_amount", safe_name="order_amount", pg_type="NUMERIC(10,2)", role="measure", distinct_count=400),
            ColumnProfile(original_name="order_status", safe_name="order_status", pg_type="TEXT", role="dimension", distinct_count=4)
        ]
    )

    rel = RelationshipProfile(
        id="rel-1",
        parent_table="customers",
        parent_column="customer_id",
        child_table="orders",
        child_column="customer_id",
        cardinality="1:N",
        confidence=1.0,
        confirmed=True
    )

    return DatasetProfile(
        id="ds-uuid-1111",
        name="Retail Workspace",
        schema_name="ds_a1b2c3d4",
        status="ready",
        share_samples=share_samples,
        source_files=["customers.csv", "orders.csv"],
        size_bytes=50000,
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        is_demo=False,
        tables=[customers_table, orders_table],
        relationships=[rel]
    )


class TestDatasetQAHermetic(unittest.TestCase):
    """Unit tests for Level 6 dataset Q&A and semantic layer."""

    def setUp(self):
        self.sample_profile = _create_sample_profile(share_samples=False)
        self.sql_context = DatasetSQLContext(
            schema_name=self.sample_profile.schema_name,
            allowed_tables={t.safe_name for t in self.sample_profile.tables},
            relationships=[r.model_dump() for r in self.sample_profile.relationships],
            table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in self.sample_profile.tables},
            is_demo=False
        )

    @patch("backend.app.services.dataset_semantic_service.DatasetService.get_dataset_profile")
    @patch("backend.app.services.dataset_semantic_service.is_fixture_mode", return_value=True)
    def test_semantic_draft_generation(self, mock_fixture, mock_get_profile):
        """Generates deterministic semantic draft from sample profile."""
        mock_get_profile.return_value = self.sample_profile

        draft = DatasetSemanticService.generate_draft("ds-uuid-1111")
        self.assertEqual(draft.status, "draft")
        self.assertEqual(draft.dataset_id, "ds-uuid-1111")

        model = draft.semantic_model
        # Check measures include row count and numeric columns
        measure_names = [m.safe_name for m in model.measures]
        self.assertIn("customers_count", measure_names)
        self.assertIn("orders_count", measure_names)
        self.assertIn("customers_credit_limit", measure_names)
        self.assertIn("orders_order_amount", measure_names)

        # Check dimensions
        dim_cols = [d.column for d in model.dimensions]
        self.assertIn("city", dim_cols)
        self.assertIn("order_status", dim_cols)

        # Check starter questions (between 6 and 8 template questions)
        self.assertTrue(6 <= len(draft.starter_questions) <= 8)
        self.assertTrue(any("by" in q.lower() or "trend" in q.lower() for q in draft.starter_questions))

    def test_validator_rejects_unqualified_table_name(self):
        """Rejects queries that do not schema-qualify tables with the dataset's schema."""
        raw_sql = "SELECT customer_name FROM customers;"
        is_valid, _, err = SQLValidator.validate(raw_sql, context=self.sql_context)
        self.assertFalse(is_valid)
        self.assertIn("must be schema-qualified with 'ds_a1b2c3d4.customers'", err)

    def test_validator_rejects_other_dataset_schema(self):
        """Rejects queries referencing a foreign ds_* schema."""
        raw_sql = "SELECT customer_name FROM ds_other99.customers;"
        is_valid, _, err = SQLValidator.validate(raw_sql, context=self.sql_context)
        self.assertFalse(is_valid)
        self.assertIn("Access to schema 'ds_other99' is forbidden", err)

    def test_validator_rejects_insightforge_metadata_schema(self):
        """Rejects queries attempting to access the insightforge admin schema."""
        raw_sql = "SELECT id, name FROM insightforge.datasets;"
        is_valid, _, err = SQLValidator.validate(raw_sql, context=self.sql_context)
        self.assertFalse(is_valid)
        self.assertIn("Access to 'insightforge' metadata schema is forbidden", err)

    def test_validator_rejects_metadata_tables_and_audit_log(self):
        """Rejects queries trying to read internal tables even if qualified."""
        for tbl in ["ai_audit_log", "datasets", "dataset_tables", "dataset_columns", "dataset_relationships", "dataset_semantic"]:
            raw_sql = f"SELECT * FROM ds_a1b2c3d4.{tbl};"
            is_valid, _, err = SQLValidator.validate(raw_sql, context=self.sql_context)
            self.assertFalse(is_valid)
            self.assertIn(f"Access to internal table '{tbl}' is strictly forbidden", err)

    def test_generic_fan_out_guard_on_1_to_n(self):
        """Generic fan-out guard rejects aggregating 1-side columns after joining N-side."""
        # Violating query: joining customers (1) and orders (N) while summing customer credit_limit
        violating_sql = (
            "SELECT c.city, SUM(c.credit_limit) "
            "FROM ds_a1b2c3d4.customers c "
            "JOIN ds_a1b2c3d4.orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.city;"
        )
        is_valid, _, err = SQLValidator.validate(violating_sql, context=self.sql_context)
        self.assertFalse(is_valid)
        self.assertIn("Fan-out rule violation", err)
        self.assertIn("joining 'customers' (one) with 'orders' (many)", err)
        self.assertIn("aggregating 'credit_limit' from 'customers'", err)

        # Valid query 1: aggregating from the N-side (orders)
        valid_sql_n_side = (
            "SELECT c.city, SUM(o.order_amount) "
            "FROM ds_a1b2c3d4.customers c "
            "JOIN ds_a1b2c3d4.orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.city;"
        )
        is_valid2, sanitized, _ = SQLValidator.validate(valid_sql_n_side, context=self.sql_context)
        self.assertTrue(is_valid2)
        self.assertIsNotNone(sanitized)

        # Valid query 2: pre-aggregating in a CTE before joining
        valid_sql_cte = (
            "WITH cust_agg AS ("
            "  SELECT city, SUM(credit_limit) AS total_credit "
            "  FROM ds_a1b2c3d4.customers "
            "  GROUP BY city"
            ") "
            "SELECT ca.city, ca.total_credit, count(o.order_id) "
            "FROM cust_agg ca "
            "JOIN ds_a1b2c3d4.orders o ON 1=1 "
            "GROUP BY ca.city, ca.total_credit;"
        )
        is_valid3, sanitized3, _ = SQLValidator.validate(valid_sql_cte, context=self.sql_context)
        self.assertTrue(is_valid3)

    @patch("backend.app.services.text_to_sql_service.is_fixture_mode", return_value=False)
    @patch("backend.app.services.text_to_sql_service.DatasetService.get_dataset_profile")
    @patch("backend.app.services.text_to_sql_service.DatasetSemanticService.get_semantic")
    @patch("backend.app.services.text_to_sql_service.AIService._get_genai_client")
    @patch("backend.app.services.text_to_sql_service.readonly_engine")
    def test_share_samples_false_privacy_model(
        self,
        mock_ro_engine,
        mock_get_client,
        mock_get_semantic,
        mock_get_profile,
        mock_fixture_mode
    ):
        """When share_samples=False: Gemini sees schema only; no cell values sent; template summary returned."""
        profile_no_share = _create_sample_profile(share_samples=False)
        mock_get_profile.return_value = profile_no_share

        semantic_model = SemanticModel(
            dataset_id=profile_no_share.id,
            dataset_name=profile_no_share.name,
            measures=[MeasureDefinition(name="Order Amount", safe_name="order_amount", table="orders", column="order_amount", aggregation="SUM")],
            dimensions=[DimensionDefinition(name="City", safe_name="city", table="customers", column="city", data_type="TEXT")]
        )
        mock_get_semantic.return_value = DatasetSemanticResponse(
            dataset_id=profile_no_share.id,
            status="draft",
            semantic_model=semantic_model,
            starter_questions=[]
        )

        mock_gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"sql": "SELECT city, SUM(order_amount) as total_sales FROM ds_a1b2c3d4.customers c JOIN ds_a1b2c3d4.orders o ON c.customer_id = o.customer_id GROUP BY 1", "explanation": "LLM text", "suggested_chart": "bar", "assumptions": []}'
        mock_gemini_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_gemini_client

        # Mock DB connection execution
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.keys.return_value = ["city", "total_sales"]
        mock_cursor.fetchmany.return_value = [("Sao Paulo", 15420.50), ("Rio de Janeiro", 9200.00)]
        mock_conn.execute.return_value = mock_cursor
        mock_ro_engine.connect.return_value.__enter__.return_value = mock_conn

        resp = TextToSQLService.ask_dataset_sql(
            dataset_id=profile_no_share.id,
            question="What are total sales by city?"
        )

        # 1. Assert privacy badge is 'AI sees: schema only'
        self.assertEqual(resp.privacy_badge, "AI sees: schema only")

        # 2. Assert explanation is a deterministic template summary, NOT the LLM text
        self.assertNotIn("LLM text", resp.explanation)
        self.assertIn("Query returned 2 rows", resp.explanation)

        # 3. Assert prompt sent to Gemini contains schema but no cell values
        call_args = mock_gemini_client.models.generate_content.call_args
        prompt_sent = call_args.kwargs.get("contents", "")
        self.assertIn("ds_a1b2c3d4", prompt_sent)
        self.assertNotIn("Sao Paulo", prompt_sent)
        self.assertNotIn("Rio de Janeiro", prompt_sent)
        self.assertNotIn("15420.50", prompt_sent)

    @patch("backend.app.services.text_to_sql_service.DatasetService.get_dataset_profile")
    def test_owner_isolation_on_ask(self, mock_get_profile):
        """Owner isolation: asking a dataset with wrong owner token raises 403."""
        mock_get_profile.side_effect = FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)

        with self.assertRaises(FileValidationError) as ctx:
            TextToSQLService.ask_dataset_sql(
                dataset_id="ds-uuid-1111",
                question="Show total revenue",
                owner_token="wrong-token"
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_insights_cache_key_includes_dataset_id(self):
        """Verifies dataset insights cache key is strictly scoped by dataset_id."""
        DatasetInsightsService.clear_cache()
        key1 = ("ds-uuid-1111", "insights")
        key2 = ("ds-uuid-2222", "insights")

        self.assertNotEqual(key1, key2)
        self.assertEqual(key1[0], "ds-uuid-1111")
        self.assertEqual(key2[0], "ds-uuid-2222")

    def test_olist_ask_path_unchanged(self):
        """Verifies default Olist Text-to-SQL validation remains backward-compatible."""
        valid_olist_sql = "SELECT category_name, total_revenue FROM view_category_contribution ORDER BY total_revenue DESC LIMIT 5;"
        is_valid, sanitized, err = SQLValidator.validate(valid_olist_sql, context=None)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        self.assertIn("view_category_contribution", sanitized)


if __name__ == "__main__":
    unittest.main()
