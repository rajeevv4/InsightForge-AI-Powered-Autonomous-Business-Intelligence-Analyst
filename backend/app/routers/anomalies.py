import time
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.config import settings
from backend.app.limiter import limiter
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.schemas.anomaly import (
    AnomalyListResponse,
    AnomalyScanRequest,
    AnomalyScanResponse
)
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.audit_service import AIAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.get("", response_model=AnomalyListResponse, status_code=status.HTTP_200_OK)
def get_anomalies(
    metric: str = Query(default="gross_revenue", description="Metric to inspect"),
    grain: str = Query(default="daily", description="Time aggregation ('daily' or 'weekly')"),
    severity: Optional[str] = Query(default=None, description="Optional severity filter ('low', 'medium', 'high')")
) -> AnomalyListResponse:
    """
    Retrieve historical time-series anomalies across statistical and machine learning models.
    """
    try:
        return AnomalyService.detect_all(grain=grain, metric=metric, severity=severity)
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in GET /anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in GET /anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve anomalies")


@router.post("/scan", response_model=AnomalyScanResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def trigger_anomaly_scan(
    request: Request,
    payload: Optional[AnomalyScanRequest] = None
) -> AnomalyScanResponse:
    """
    Execute comprehensive multi-method anomaly scan over business metrics.
    Rate-limited and logged to AI audit telemetry.
    """
    start_time = time.time()
    grain = payload.grain if payload and payload.grain else "daily"
    metrics = payload.metrics if payload and payload.metrics else None

    try:
        scan_result = AnomalyService.run_full_scan(metrics=metrics, grain=grain)
        latency_ms = (time.time() - start_time) * 1000.0

        AIAuditService.log(
            question=f"Anomaly scan [{grain}] ({len(scan_result.scanned_metrics)} metrics)",
            intent="anomaly_detection",
            generated_sql=f"anomaly_scan_full_{grain}",
            latency_ms=latency_ms,
            success=True,
            error=None
        )
        return scan_result
    except DatabaseUnavailableError as e:
        latency_ms = (time.time() - start_time) * 1000.0
        logger.error(f"Database unavailable in POST /anomalies/scan: {e}", exc_info=True)
        AIAuditService.log(
            question=f"Anomaly scan [{grain}]",
            intent="anomaly_detection",
            generated_sql=None,
            latency_ms=latency_ms,
            success=False,
            error=str(e)
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000.0
        logger.error(f"Unexpected error in POST /anomalies/scan: {e}", exc_info=True)
        AIAuditService.log(
            question=f"Anomaly scan [{grain}]",
            intent="anomaly_detection",
            generated_sql=None,
            latency_ms=latency_ms,
            success=False,
            error=str(e)
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to run anomaly scan")
