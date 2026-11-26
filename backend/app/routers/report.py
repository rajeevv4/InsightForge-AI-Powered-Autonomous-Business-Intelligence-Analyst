import io
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.app.config import settings
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError
from backend.app.limiter import limiter
from backend.app.schemas.report import ReportResponse
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.report_service import OlistReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["Report"])


def report_response(report: ReportResponse, fmt: str):
    """JSON payload, or the PDF streamed from memory as InsightForge_Report_<dataset>_<date>.pdf."""
    if fmt == "pdf":
        from backend.app.services.report_pdf import build_pdf, safe_filename
        pdf = build_pdf(report)
        return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{safe_filename(report.dataset_name)}"',
            "Content-Length": str(len(pdf)),
            "Access-Control-Expose-Headers": "Content-Disposition",
        })
    return report


@router.get("", response_model=ReportResponse, status_code=status.HTTP_200_OK,
            summary="One-click report for the Olist demo (format=json | pdf; deterministic templates, no LLM)")
@limiter.limit(settings.RATE_LIMIT_REPORT)
def get_report(request: Request, format: str = Query("json", pattern="^(json|pdf)$", description="json | pdf")):
    try:
        return report_response(OlistReportService.build(), format)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except QueryTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Query timed out, please retry")
    except DatabaseUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Unexpected error in GET /report: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build report")
