import logging
from fastapi import APIRouter, HTTPException, Request, status

from backend.app.config import settings
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError
from backend.app.limiter import limiter
from backend.app.schemas.briefing import BriefingThresholds, MorningBriefingResponse
from backend.app.services.briefing_service import BriefingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefing", tags=["Morning Briefing & Alerts"])


@router.get(
    "",
    response_model=MorningBriefingResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministic executive morning briefing with default threshold alerts",
)
@limiter.limit(settings.RATE_LIMIT_FORECAST)
def get_morning_briefing(request: Request) -> MorningBriefingResponse:
    try:
        return BriefingService.build()
    except QueryTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Query timed out, please retry")
    except DatabaseUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in GET /briefing: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build morning briefing")


@router.post(
    "",
    response_model=MorningBriefingResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate executive morning briefing against custom deterministic threshold rules",
)
@limiter.limit(settings.RATE_LIMIT_FORECAST)
def evaluate_morning_briefing(request: Request, thresholds: BriefingThresholds) -> MorningBriefingResponse:
    try:
        return BriefingService.build(thresholds=thresholds)
    except QueryTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Query timed out, please retry")
    except DatabaseUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in POST /briefing: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to evaluate morning briefing")
