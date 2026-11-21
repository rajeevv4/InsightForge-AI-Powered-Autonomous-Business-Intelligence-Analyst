import unittest
from backend.app.services.audit_service import AIAuditService


class TestAIAuditService(unittest.TestCase):

    def setUp(self):
        AIAuditService.clear_memory()

    def test_log_and_get_history_memory_fallback(self):
        """Test logging interactions and retrieving history via the memory fallback."""
        entry1 = AIAuditService.log(
            question="What is our total gross revenue?",
            intent="kpi_summary",
            generated_sql=None,
            latency_ms=45.2,
            success=True,
            error=None
        )
        self.assertEqual(entry1["question"], "What is our total gross revenue?")
        self.assertEqual(entry1["intent"], "kpi_summary")
        self.assertTrue(entry1["success"])

        entry2 = AIAuditService.log(
            question="Which category has lowest sales?",
            intent="category_analysis",
            generated_sql=None,
            latency_ms=120.5,
            success=False,
            error="Connection timeout"
        )
        self.assertFalse(entry2["success"])
        self.assertEqual(entry2["error"], "Connection timeout")

        history = AIAuditService.get_history(limit=10)
        self.assertGreaterEqual(len(history), 2)
        # Most recent first
        self.assertEqual(history[0]["question"], "Which category has lowest sales?")
        self.assertEqual(history[1]["question"], "What is our total gross revenue?")

    def test_history_limit_parameter(self):
        """Test that history respects the limit parameter."""
        for i in range(15):
            AIAuditService.log(
                question=f"Question #{i}",
                intent="kpi_summary",
                generated_sql=None,
                latency_ms=10.0,
                success=True
            )

        history_5 = AIAuditService.get_history(limit=5)
        self.assertEqual(len(history_5), 5)

        history_10 = AIAuditService.get_history(limit=10)
        self.assertEqual(len(history_10), 10)


if __name__ == "__main__":
    unittest.main()
