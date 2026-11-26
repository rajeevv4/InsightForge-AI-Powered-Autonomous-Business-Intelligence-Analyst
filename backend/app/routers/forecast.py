import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.config import settings
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError
from backend.app.limiter import limiter
from backend.app.schemas.forecast import ForecastResponse
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.forecast_service import OlistForecastService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["Forecast"])


@router.get("", response_model=ForecastResponse, status_code=status.HTTP_200_OK,
            summary="Baseline forecast with 80% / 95% bands for the Olist demo (deterministic ETS, no LLM)")
@limiter.limit(settings.RATE_LIMIT_FORECAST)
def get_forecast(
    request: Request,
    metric: str = Query(default="gross_revenue", description="gross_revenue | order_count"),
    horizon: int = Query(default=3, ge=1, le=6, description="Months ahead (1-6)"),
    exclude_anomalies: bool = Query(default=False, description="Replace flagged anomaly days by their expected value"),
) -> ForecastResponse:
    try:
        return OlistForecastService.forecast(metric=metric, horizon=horizon, exclude_anomalies=exclude_anomalies)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except QueryTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Query timed out, please retry")
    except DatabaseUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in GET /forecast: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build forecast")
