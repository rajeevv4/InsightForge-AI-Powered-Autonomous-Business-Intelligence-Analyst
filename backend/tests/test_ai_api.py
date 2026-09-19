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

        # Return non-JSON text
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
        # Empty question
        res1 = self.client.post("/api/ai/ask", json={"question": "   "})
        self.assertEqual(res1.status_code, 422)

        # Question too short
        res2 = self.client.post("/api/ai/ask", json={"question": "Hi"})
        self.assertEqual(res2.status_code, 422)

        # Question too long (>500 chars)
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


if __name__ == "__main__":
    unittest.main()
