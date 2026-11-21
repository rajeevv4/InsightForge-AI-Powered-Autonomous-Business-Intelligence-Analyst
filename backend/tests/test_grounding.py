import unittest
from backend.app.services.grounding import (
    extract_numbers_from_text,
    extract_numbers_from_evidence,
    verify_numeric_grounding
)


class TestGroundingVerifier(unittest.TestCase):

    def test_extract_numbers_from_text_formats(self):
        """Extract currency, comma-formatted numbers, decimals, and percentages."""
        text = "Revenue was R$ 13,221,498.11 with an AOV of R$ 159.83 across 96,478 orders (92.5% on-time)."
        extracted = extract_numbers_from_text(text)
        self.assertIn(13221498.11, extracted)
        self.assertIn(159.83, extracted)
        self.assertIn(96478.0, extracted)
        self.assertIn(92.5, extracted)
        self.assertIn(0.925, extracted)

    def test_extract_evidence_numbers_nested(self):
        """Recursively extract numbers from nested dictionaries and lists."""
        payload = {
            "gross_revenue": 15419773.75,
            "metrics": [
                {"score": 4.16, "orders": 96478},
                {"growth": 0.152}
            ]
        }
        extracted = extract_numbers_from_evidence(payload)
        self.assertIn(15419773.75, extracted)
        self.assertIn(4.16, extracted)
        self.assertIn(96478.0, extracted)
        self.assertIn(0.152, extracted)
        # Scaled percentage variant
        self.assertIn(15.2, extracted)

    def test_verify_numeric_grounding_valid(self):
        """Verified answer where all numbers exist in evidence."""
        evidence = {
            "gross_revenue": 15419773.75,
            "product_revenue": 13221498.11,
            "delivered_orders": 96478,
            "aov": 159.83,
            "csat": 4.16
        }
        answer = "Our gross revenue reached R$ 15,419,773.75 with 96,478 delivered orders and an AOV of R$ 159.83."
        self.assertTrue(verify_numeric_grounding(answer, evidence))

    def test_verify_numeric_grounding_hallucination_detected(self):
        """Fails when LLM invents a number not present in evidence."""
        evidence = {
            "gross_revenue": 15419773.75,
            "product_revenue": 13221498.11
        }
        # 999999.99 is not in evidence
        hallucinated_answer = "Total gross revenue was R$ 15,419,773.75 with a projected bonus of R$ 999,999.99."
        self.assertFalse(verify_numeric_grounding(hallucinated_answer, evidence))

    def test_verify_numeric_grounding_allows_metadata(self):
        """Allows dataset years (2017, 2018) and ranks (#1, top 5) without failing."""
        evidence = {
            "product_category": "health_beauty",
            "total_revenue": 1258819.00
        }
        answer = "In 2017 and 2018, the #1 category was Health Beauty generating R$ 1,258,819.00 across top 5 categories."
        self.assertTrue(verify_numeric_grounding(answer, evidence))

    def test_verify_numeric_grounding_empty_answer(self):
        """Empty or non-numeric answers pass trivially."""
        evidence = {"revenue": 1000.0}
        self.assertTrue(verify_numeric_grounding("No data was found for this query.", evidence))


if __name__ == "__main__":
    unittest.main()
