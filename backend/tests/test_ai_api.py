import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.ai_analytics_router import AIAnalyticsRouter, SUPPORTED_INTENTS
from backend.app.services.ai_service import AIService
from backend.app.schemas.ai import AskAIResponse, AIEvidence


class TestAIAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_valid_category_question(self, mock_get_client):
        """Test asking a valid category question with mocked Gemini response."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock classification response
        mock_class_resp = MagicMock()
        mock_class_resp.text = '{"intent": "category_analysis", "confidence": 0.94, "reason": "User asks for top revenue category."}'

        # Mock synthesis response
        mock_synth_resp = MagicMock()
        mock_synth_resp.text = "Based on PostgreSQL analytics, **Health Beauty** generated the highest revenue."

        mock_client.models.generate_content.side_effect = [mock_class_resp, mock_synth_resp]

        response = self.client.post("/api/ai/ask", json={"question": "Which category generated the highest revenue?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["question"], "Which category generated the highest revenue?")
        self.assertEqual(data["intent"], "category_analysis")
        self.assertGreaterEqual(data["confidence"], 0.60)
        self.assertIn("Health Beauty", data["answer"])
        self.assertIsNotNone(data["evidence"])
        self.assertEqual(data["evidence"]["intent"], "category_analysis")

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_valid_kpi_question(self, mock_get_client):
        """Test asking a valid KPI question."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_class_resp = MagicMock()
        mock_class_resp.text = '{"intent": "kpi_summary", "confidence": 0.96, "reason": "User asks for AOV and executive KPIs."}'

        mock_synth_resp = MagicMock()
        mock_synth_resp.text = "Our average order value (AOV) is R$ 159.83 across 96,478 delivered orders."

        mock_client.models.generate_content.side_effect = [mock_class_resp, mock_synth_resp]

        response = self.client.post("/api/ai/ask", json={"question": "What is our average order value?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["intent"], "kpi_summary")
        self.assertIn("159.83", data["answer"])
        self.assertEqual(data["evidence"]["metric"], "Executive KPI Summary")

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_valid_delivery_question(self, mock_get_client):
        """Test asking a valid delivery performance question."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_class_resp = MagicMock()
        mock_class_resp.text = '{"intent": "delivery_analysis", "confidence": 0.92, "reason": "User asks about shipping SLA performance."}'

        mock_synth_resp = MagicMock()
        mock_synth_resp.text = "Over 92% of orders were delivered on-time within an average of 12.5 days."

        mock_client.models.generate_content.side_effect = [mock_class_resp, mock_synth_resp]

        response = self.client.post("/api/ai/ask", json={"question": "How is our delivery performance?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["intent"], "delivery_analysis")
        self.assertIn("delivered", data["answer"].lower())

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_unsupported_low_confidence_question(self, mock_get_client):
        """Test handling of unsupported or low confidence questions."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_class_resp = MagicMock()
        mock_class_resp.text = '{"intent": "unknown", "confidence": 0.25, "reason": "Question is unrelated to business analytics."}'

        mock_client.models.generate_content.return_value = mock_class_resp

        response = self.client.post("/api/ai/ask", json={"question": "What is the capital of France?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["intent"], "unknown")
        self.assertLess(data["confidence"], 0.60)
        self.assertTrue(data["rephrase_suggested"])
        self.assertIsNone(data["evidence"])
        self.assertIn("rephrase your question", data["answer"].lower())

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_malformed_ai_response_fallback(self, mock_get_client):
        """Test handling when Gemini returns invalid JSON during classification."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_class_resp = MagicMock()
        mock_class_resp.text = "Sorry, I am just an AI and cannot process this."
        mock_client.models.generate_content.return_value = mock_class_resp

        response = self.client.post("/api/ai/ask", json={"question": "Which category generated the highest revenue?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Heuristic classifier takes over
        self.assertEqual(data["intent"], "category_analysis")
        self.assertGreaterEqual(data["confidence"], 0.60)
        self.assertIsNotNone(data["evidence"])

    def test_analytics_routing(self):
        """Test that all 8 supported intents successfully route to analytics functions without errors."""
        for intent in SUPPORTED_INTENTS:
            evidence = AIAnalyticsRouter.route_intent(intent)
            self.assertEqual(evidence["source"], "PostgreSQL analytics")
            self.assertEqual(evidence["intent"], intent)
            self.assertIn("data", evidence)

    def test_api_validation(self):
        """Test API request payload validation rules."""
        res1 = self.client.post("/api/ai/ask", json={"question": "   "})
        self.assertEqual(res1.status_code, 422)

        res2 = self.client.post("/api/ai/ask", json={"question": "Hi"})
        self.assertEqual(res2.status_code, 422)

        res3 = self.client.post("/api/ai/ask", json={"question": "A" * 501})
        self.assertEqual(res3.status_code, 422)

    @patch("backend.app.services.ai_service.AIService.ask")
    def test_safe_error_handling(self, mock_ask):
        """Test that unhandled service exceptions return safe HTTP 500 without leaking stack traces."""
        mock_ask.side_effect = Exception("Sensitive DB Password Leaked!")

        response = self.client.post("/api/ai/ask", json={"question": "What is our revenue?"})
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("detail", data)
        self.assertNotIn("Sensitive DB Password", data["detail"])

    # ======================================================================
    # Regression: Item 5 — word-boundary false positive tests
    # ======================================================================
    def test_heuristic_false_positive_moment(self):
        """'moment' should NOT trigger 'mom' revenue_trend intent."""
        result = AIService.classify_intent_heuristic("Can you describe the moment we launched?")
        self.assertNotEqual(result["intent"], "revenue_trend",
                            "'moment' falsely matched 'mom' — word boundary broken")

    def test_heuristic_false_positive_estate(self):
        """'estate' should NOT trigger 'state' state_analysis intent."""
        result = AIService.classify_intent_heuristic("Tell me about real estate pricing trends.")
        self.assertNotEqual(result["intent"], "state_analysis",
                            "'estate' falsely matched 'state' — word boundary broken")

    def test_heuristic_false_positive_slack(self):
        """'slack' should NOT trigger 'sla' delivery_analysis intent."""
        result = AIService.classify_intent_heuristic("Is our team using slack effectively?")
        self.assertNotEqual(result["intent"], "delivery_analysis",
                            "'slack' falsely matched 'sla' — word boundary broken")

    # ======================================================================
    # Regression: Item 3 — semantic context loader
    # ======================================================================
    def test_semantic_context_loads_glossary(self):
        """load_semantic_context should return glossary content with synonyms."""
        ctx = AIService.load_semantic_context()
        self.assertIn("BUSINESS GLOSSARY", ctx, "Glossary section not loaded")
        self.assertIn("Revenue", ctx, "Revenue term missing from glossary")
        self.assertIn("synonyms:", ctx.lower(), "Synonyms not included in glossary context")

    # ======================================================================
    # Regression: Item 2 — data quality real checks
    # ======================================================================
    def test_data_quality_has_real_pk_check(self):
        """data quality API should return computed PK check, not hardcoded PASS."""
        response = self.client.get("/api/data-quality")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        pk = data["primary_key_uniqueness"]
        self.assertTrue("PASS" in pk or "FAIL" in pk,
                        f"PK uniqueness should be PASS/FAIL with detail, got: {pk}")
        self.assertIn("duplicates", pk.lower(),
                       f"PK status should mention duplicate count, got: {pk}")

    def test_data_quality_has_real_fk_check(self):
        """data quality API should return computed FK check, not hardcoded PASS."""
        response = self.client.get("/api/data-quality")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        fk = data["foreign_key_integrity"]
        self.assertTrue("PASS" in fk or "FAIL" in fk,
                        f"FK integrity should be PASS/FAIL with detail, got: {fk}")
        self.assertIn("orphans", fk.lower(),
                       f"FK status should mention orphan count, got: {fk}")

    def test_data_quality_has_real_domain_check(self):
        """data quality API should return computed domain bounds check."""
        response = self.client.get("/api/data-quality")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        domain = data["domain_bounds_status"]
        self.assertTrue("PASS" in domain or "FAIL" in domain,
                        f"Domain check should be PASS/FAIL with detail, got: {domain}")

    # ======================================================================
    # Regression: Item 1 — category contribution
    # ======================================================================
    def test_category_revenue_via_api(self):
        """Categories endpoint revenue sum should match canonical 13,221,498.11."""
        response = self.client.get("/api/analytics/categories?limit=200")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        total_rev = sum(c["total_revenue"] for c in data)
        self.assertAlmostEqual(total_rev, 13221498.11, places=2,
                               msg=f"API category revenue sum {total_rev} != 13221498.11")


    # ======================================================================
    # AI Infrastructure: History, Grounding Verification, Rate Limiter
    # ======================================================================
    def test_ai_history_endpoint(self):
        """Test GET /api/ai/history returns audit log records."""
        # Make a request first to populate audit log
        self.client.post("/api/ai/ask", json={"question": "What is our average order value?"})
        response = self.client.get("/api/ai/history?limit=10")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        first = data[0]
        self.assertIn("question", first)
        self.assertIn("latency_ms", first)
        self.assertIn("success", first)
        self.assertIn("timestamp", first)

    @patch("backend.app.services.ai_service.AIService._get_genai_client")
    def test_numeric_hallucination_fallback(self, mock_get_client):
        """When LLM hallucinates an ungrounded number, verify fallback to heuristic and grounding_verified=False."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_class_resp = MagicMock()
        mock_class_resp.text = '{"intent": "kpi_summary", "confidence": 0.95, "reason": "KPI request"}'

        # Hallucinated number 999999999.99
        mock_synth_resp = MagicMock()
        mock_synth_resp.text = "Our total gross revenue is R$ 999,999,999.99 which was huge."

        mock_client.models.generate_content.side_effect = [mock_class_resp, mock_synth_resp]

        response = self.client.post("/api/ai/ask", json={"question": "What is our average order value?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["grounding_verified"])
        # Answer must NOT contain the hallucinated number
        self.assertNotIn("999,999,999.99", data["answer"])

    def test_rate_limiter_registered(self):
        """Test that slowapi rate limiter is registered on app state."""
        self.assertTrue(hasattr(app.state, "limiter"))
        self.assertIsNotNone(app.state.limiter)


if __name__ == "__main__":
    unittest.main()
