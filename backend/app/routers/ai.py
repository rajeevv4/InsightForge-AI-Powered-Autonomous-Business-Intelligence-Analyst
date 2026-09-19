import logging
from fastapi import APIRouter, HTTPException, status
from backend.app.schemas.ai import AskAIRequest, AskAIResponse
from backend.app.services.ai_service import AIService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["Ask InsightForge AI"]
)


@router.post(
    "/ask",
    response_model=AskAIResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask InsightForge - AI Business Intelligence Assistant",
    description=(
        "Processes natural-language business questions, classifies them into controlled "
        "intents, routes to validated PostgreSQL analytics functions, and returns a grounded "
        "natural-language business explanation backed by real evidence."
    )
)
def ask_ai_question(payload: AskAIRequest) -> AskAIResponse:
    try:
        response = AIService.ask(payload.question)
        return response
    except ValueError as e:
        logger.warning(f"Validation error in Ask AI: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error processing AI request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your natural language question. Please try again."
        )
