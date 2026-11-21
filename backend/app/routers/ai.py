import logging
from typing import List
from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.config import settings
from backend.app.limiter import limiter
from backend.app.schemas.ai import AIAuditLogItem, AskAIRequest, AskAIResponse, SQLAskResponse
from backend.app.services.ai_service import AIService
from backend.app.services.text_to_sql_service import TextToSQLService
from backend.app.services.audit_service import AIAuditService
from backend.app.exceptions import DatabaseUnavailableError

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
@limiter.limit(settings.RATE_LIMIT_AI_ASK)
def ask_ai_question(request: Request, payload: AskAIRequest) -> AskAIResponse:
    try:
        response = AIService.ask(payload.question)
        return response
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in Ask AI: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
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


@router.post(
    "/sql-ask",
    response_model=SQLAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Guarded Text-to-SQL & Dynamic Query Routing",
    description=(
        "Converts natural language questions to safe, guarded PostgreSQL SELECT queries "
        "with AST validation, self-correction, and dual routing policy (intent router vs Text-to-SQL). "
        "Requires a live database connection."
    )
)
@limiter.limit(settings.RATE_LIMIT_AI_ASK)
def ask_sql_question(request: Request, payload: AskAIRequest) -> SQLAskResponse:
    try:
        response = TextToSQLService.ask_sql(payload.question)
        return response
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in SQL Ask: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable: SQL mode requires a live database connection."
        )
    except ValueError as e:
        logger.warning(f"Validation error in SQL Ask: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error processing SQL request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your dynamic SQL request. Please try again."
        )


@router.get(
    "/history",
    response_model=List[AIAuditLogItem],
    status_code=status.HTTP_200_OK,
    summary="Get AI Query Audit History",
    description="Returns recent natural-language queries, classified intents, latency, and execution status."
)
def get_ai_history(
    limit: int = Query(default=50, ge=1, le=500, description="Max number of audit log entries to return")
) -> List[AIAuditLogItem]:
    try:
        records = AIAuditService.get_history(limit=limit)
        return [AIAuditLogItem(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching AI query history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve AI interaction history."
        )
