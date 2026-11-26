import pytest
from unittest.mock import MagicMock, patch

from backend.app.schemas.ai import AskAIRequest, ConversationTurn
from backend.app.schemas.dataset_semantic import DatasetAskRequest
from backend.app.services.text_to_sql_service import TextToSQLService


def test_ask_requests_backward_compatible_without_history():
    req1 = AskAIRequest(question="What is the total revenue?")
    assert req1.history is None

    req2 = DatasetAskRequest(question="Show total sales")
    assert req2.history is None


def test_format_history_context_caps_at_5_and_redacts_literals():
    turns = [
        ConversationTurn(question=f"Question {i}", sql=f"SELECT * FROM orders WHERE state = 'SP{i}' LIMIT 10")
        for i in range(1, 8)
    ]
    ctx_unredacted = TextToSQLService._format_history_context(turns, redact_literals=False)
    assert "Question 1" not in ctx_unredacted
    assert "Question 2" not in ctx_unredacted
    assert "Question 3" in ctx_unredacted
    assert "Question 7" in ctx_unredacted
    assert "'SP7'" in ctx_unredacted

    ctx_redacted = TextToSQLService._format_history_context(turns, redact_literals=True)
    assert "'SP7'" not in ctx_redacted
    assert "'<literal>'" in ctx_redacted


def test_multi_turn_follow_up_bypasses_canned_intent_and_validates_sql():
    mock_client = MagicMock()
    history = [
        ConversationTurn(
            question="Top 5 categories by revenue",
            sql="SELECT p.product_category_name, SUM(oi.price) AS rev FROM insightforge.order_items oi JOIN insightforge.products p ON oi.product_id = p.product_id GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
        )
    ]

    with patch("backend.app.services.ai_service.AIService._get_genai_client", return_value=mock_client), \
         patch.object(TextToSQLService, "generate_and_validate_sql", return_value={
             "success": True,
             "sql": "SELECT p.product_category_name, SUM(oi.price) AS rev FROM insightforge.order_items oi JOIN insightforge.products p ON oi.product_id = p.product_id JOIN insightforge.orders o ON oi.order_id = o.order_id JOIN insightforge.customers c ON o.customer_id = c.customer_id WHERE c.customer_state = 'SP' GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
             "explanation": "Top 5 categories in SP.",
             "assumptions": ["Filtered for SP"],
             "suggested_chart": "bar",
             "rows": [{"product_category_name": "cama_mesa_banho", "rev": 500000.0}],
             "columns": ["product_category_name", "rev"],
         }) as mock_gen, \
         patch("backend.app.services.text_to_sql_service.AIAuditService.log"):
        resp = TextToSQLService.ask_sql("Now filter that only for SP", history=history)

    assert resp.route == "text_to_sql"
    assert resp.row_count == 1
    mock_gen.assert_called_once()
    assert mock_gen.call_args.kwargs["history"] == history
