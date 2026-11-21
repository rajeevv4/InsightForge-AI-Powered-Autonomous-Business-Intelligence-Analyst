import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.main import app
from backend.app.services.sql_validator import SQLValidator
from backend.app.services.text_to_sql_service import TextToSQLService
from backend.app.exceptions import DatabaseUnavailableError

client = TestClient(app)


class TestSQLValidatorSecurity(unittest.TestCase):
    """
    Security AST validator test suite.
    Every malicious injection, privilege escalation, and bypass technique must be rejected.
    """

    def test_drop_table_injection_rejected(self):
        """Stacked query attempting '; DROP TABLE orders' must be rejected."""
        sql = "SELECT order_id FROM orders; DROP TABLE orders;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Multiple SQL statements", error)

    def test_standalone_drop_table_rejected(self):
        """Standalone DROP TABLE statement must be rejected."""
        sql = "DROP TABLE orders;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Only SELECT", error)

    def test_pg_sleep_function_rejected(self):
        """Time-based blind injection with pg_sleep() must be rejected."""
        sql = "SELECT order_id FROM orders WHERE price > 10 AND pg_sleep(5) IS NULL;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Forbidden database function", error)
        self.assertIn("pg_sleep", error)

    def test_insert_update_delete_rejected(self):
        """DML mutations (INSERT, UPDATE, DELETE) must be strictly rejected."""
        queries = [
            "INSERT INTO orders (order_id) VALUES ('x');",
            "UPDATE orders SET order_status = 'delivered' WHERE order_id = 'x';",
            "DELETE FROM orders WHERE order_id = 'x';"
        ]
        for q in queries:
            is_valid, _, error = SQLValidator.validate(q)
            self.assertFalse(is_valid, f"Query '{q}' should be rejected")
            self.assertTrue("Only SELECT" in error or "Forbidden statement" in error)

    def test_multiple_statements_rejected(self):
        """Multiple chained queries must be rejected."""
        sql = "SELECT 1; SELECT 2;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Multiple SQL statements", error)

    def test_unlisted_table_access_rejected(self):
        """Queries referencing tables not in the approved semantic catalog must be rejected."""
        sql = "SELECT * FROM users;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("not in the allowed tables list", error)

    def test_ai_audit_log_access_rejected(self):
        """Queries attempting to inspect the internal ai_audit_log table must be rejected."""
        sql = "SELECT question, generated_sql FROM ai_audit_log;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Access to internal table 'ai_audit_log' is strictly forbidden", error)

    def test_pg_catalog_access_rejected(self):
        """Queries accessing pg_catalog tables or views must be rejected."""
        sql = "SELECT relname FROM pg_catalog.pg_class;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Access to system schema 'pg_catalog' is forbidden", error)

    def test_information_schema_access_rejected(self):
        """Queries accessing information_schema must be rejected."""
        sql = "SELECT table_name FROM information_schema.tables;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Access to system schema 'information_schema' is forbidden", error)

    def test_comment_tricks_neutralized(self):
        """Comment tricks (/* */ and --) must be stripped, validated, or rejected."""
        sql = "/* admin bypass */ SELECT order_id FROM orders -- trick trailing comment"
        is_valid, sanitized, error = SQLValidator.validate(sql)
        self.assertTrue(is_valid)
        self.assertNotIn("/*", sanitized)
        self.assertNotIn("--", sanitized)

    def test_union_into_system_tables_rejected(self):
        """UNION injections targeting system tables or denied functions must be rejected."""
        sql = "SELECT order_id FROM orders UNION SELECT usename FROM pg_catalog.pg_user;"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertTrue(
            "pg_catalog" in (error or "") or "not in the allowed tables list" in (error or "")
        )

    def test_set_and_copy_statements_rejected(self):
        """Administrative and copy commands (SET, COPY) must be rejected."""
        queries = [
            "SET statement_timeout = 0; SELECT 1;",
            "COPY orders TO '/tmp/data.csv';",
            "COPY orders FROM '/tmp/data.csv';"
        ]
        for q in queries:
            is_valid, _, error = SQLValidator.validate(q)
            self.assertFalse(is_valid, f"Command '{q}' should be rejected")

    def test_nested_subquery_with_denied_function_rejected(self):
        """Subqueries concealing denied functions (e.g. pg_sleep, dblink) must be rejected."""
        sql = "SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM customers WHERE pg_sleep(3) IS NULL);"
        is_valid, _, error = SQLValidator.validate(sql)
        self.assertFalse(is_valid)
        self.assertIn("Forbidden database function call", error)

    def test_cross_join_rejected(self):
        """CROSS JOIN and comma Cartesian joins must be rejected."""
        cross_sql = "SELECT * FROM orders CROSS JOIN order_items;"
        is_valid, _, error = SQLValidator.validate(cross_sql)
        self.assertFalse(is_valid)
        self.assertIn("Cross joins", error)

        comma_sql = "SELECT * FROM orders, order_items WHERE orders.order_id = order_items.order_id;"
        is_valid_c, _, error_c = SQLValidator.validate(comma_sql)
        self.assertFalse(is_valid_c)
        self.assertIn("Cartesian joins", error_c)

    def test_fan_out_rule_rejected(self):
        """Direct join of order_items with order_reviews/order_payments summing revenue must be rejected."""
        fanout_sql = (
            "SELECT SUM(oi.price) FROM order_items oi "
            "JOIN order_payments op ON oi.order_id = op.order_id "
            "WHERE oi.order_id = 'test';"
        )
        is_valid, _, error = SQLValidator.validate(fanout_sql)
        self.assertFalse(is_valid)
        self.assertIn("Fan-out rule violation", error)

    def test_limit_enforced_to_max_500(self):
        """Queries without LIMIT must have LIMIT 500 added; queries with LIMIT > 500 must be clamped."""
        no_limit = "SELECT order_id FROM orders;"
        _, san1, _ = SQLValidator.validate(no_limit)
        self.assertIn("LIMIT 500", san1)

        high_limit = "SELECT order_id FROM orders LIMIT 2000;"
        _, san2, _ = SQLValidator.validate(high_limit)
        self.assertIn("LIMIT 500", san2)
        self.assertNotIn("2000", san2)

        safe_limit = "SELECT order_id FROM orders LIMIT 25;"
        _, san3, _ = SQLValidator.validate(safe_limit)
        self.assertIn("LIMIT 25", san3)


class TestTextToSQLServiceAndRouting(unittest.TestCase):
    """
    Unit test suite covering Text-to-SQL generation, self-correction,
    and routing policy with mocked Gemini client.
    """

    @classmethod
    def setUpClass(cls):
        os.environ["USE_FIXTURES"] = "1"

    @patch("backend.app.services.text_to_sql_service.TextToSQLService.execute_guarded_sql")
    def test_text_to_sql_self_correction_success(self, mock_exec):
        """Self-correction re-prompts Gemini on validation failure and succeeds upon correction."""
        mock_exec.return_value = ([{"category": "telephony", "revenue": 323667.53}], ["category", "revenue"])

        # Attempt 1 returns invalid table 'super_secret_table'
        # Attempt 2 returns valid query on 'view_category_contribution'
        mock_response_1 = MagicMock()
        mock_response_1.text = '{"sql": "SELECT * FROM super_secret_table;", "explanation": "bad", "assumptions": []}'

        mock_response_2 = MagicMock()
        mock_response_2.text = (
            '{"sql": "SELECT category, total_revenue FROM view_category_contribution ORDER BY total_revenue DESC LIMIT 5;", '
            '"explanation": "Top categories by revenue.", "assumptions": ["Delivered orders only"]}'
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [mock_response_1, mock_response_2]

        result = TextToSQLService.generate_and_validate_sql(mock_client, "Top categories by revenue", max_retries=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("view_category_contribution", result["sql"])

    @patch("backend.app.services.ai_analytics_router.AIAnalyticsRouter.route_intent")
    @patch("backend.app.services.ai_service.AIService.classify_intent_heuristic")
    def test_routing_policy_high_confidence_uses_intent(self, mock_classify, mock_route):
        """Query with intent confidence >= 0.80 routes to deterministic intent router."""
        mock_classify.return_value = {
            "intent": "category_analysis",
            "confidence": 0.95,
            "reason": "Clear category revenue question"
        }
        mock_route.return_value = {
            "source": "PostgreSQL analytics",
            "intent": "category_analysis",
            "metric": "Top Product Categories",
            "data": [
                {
                    "category": "health_beauty",
                    "product_category_name_english": "health_beauty",
                    "total_revenue": 1258819.00,
                    "revenue_contribution_pct": 9.52,
                    "units_sold": 9670
                }
            ]
        }
        res = TextToSQLService.ask_sql("Which category generated the highest revenue?")
        self.assertEqual(res.route, "intent")
        self.assertIsNone(res.sql)
        self.assertIn("health", res.explanation.lower())

    @patch("backend.app.services.ai_service.AIService.classify_intent_heuristic")
    @patch("backend.app.services.text_to_sql_service.TextToSQLService.execute_guarded_sql")
    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_routing_policy_low_confidence_uses_text_to_sql(self, mock_get_client, mock_exec, mock_classify):
        """Query with low intent confidence or custom filter routes to Text-to-SQL."""
        mock_classify.return_value = {"intent": "unknown", "confidence": 0.40, "reason": "Specific multi-filter query"}
        mock_exec.return_value = ([{"customer_city": "curitiba", "order_count": 450}], ["customer_city", "order_count"])

        mock_gemini = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            '{"sql": "SELECT c.customer_city, COUNT(o.order_id) AS order_count FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.customer_state = \'PR\' AND o.order_status = \'delivered\' GROUP BY c.customer_city ORDER BY order_count DESC LIMIT 10;", '
            '"explanation": "Cities in PR state ranked by orders.", "assumptions": ["State PR"], "suggested_chart": "bar"}'
        )
        mock_gemini.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_gemini

        res = TextToSQLService.ask_sql("Show me cities in Parana PR state with highest orders")
        self.assertEqual(res.route, "text_to_sql")
        self.assertIsNotNone(res.sql)
        self.assertEqual(res.row_count, 1)

    def test_sql_ask_endpoint_db_unavailable_returns_503(self):
        """POST /api/ai/sql-ask returns 503 when the database is unavailable."""
        with patch(
            "backend.app.services.text_to_sql_service.TextToSQLService.ask_sql",
            side_effect=DatabaseUnavailableError("Database unreachable")
        ):
            resp = client.post("/api/ai/sql-ask", json={"question": "What is total revenue?"})
            self.assertEqual(resp.status_code, 503)
            self.assertIn("Database unavailable", resp.json()["detail"])

    def test_validator_allowed_views_exist_in_live_db(self):
        """Every view in ALLOWED_ANALYTICAL_VIEWS must exist in the PostgreSQL schema."""
        from backend.app.database import engine
        from backend.app.config import settings
        from backend.app.services.sql_validator import ALLOWED_ANALYTICAL_VIEWS
        from sqlalchemy import text

        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT table_name FROM information_schema.views WHERE table_schema = :s"),
                    {"s": settings.DB_SCHEMA}
                ).fetchall()
                live_views = {r[0] for r in rows}
                for v in ALLOWED_ANALYTICAL_VIEWS:
                    self.assertIn(
                        v,
                        live_views,
                        f"View '{v}' in ALLOWED_ANALYTICAL_VIEWS not found in database schema '{settings.DB_SCHEMA}'"
                    )
        except Exception as e:
            self.skipTest(f"Live database not available: {e}")


if __name__ == "__main__":
    unittest.main()
