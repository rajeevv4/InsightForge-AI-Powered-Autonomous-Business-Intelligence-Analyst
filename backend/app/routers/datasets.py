import logging
from typing import List, Optional
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile, status

from backend.app.config import settings
from backend.app.fixture_guard import is_fixture_mode
from backend.app.limiter import limiter, get_client_ip
from backend.app.schemas.dataset import (
    DatasetProfile,
    DatasetSummary,
    TablePreviewResponse,
    UpdateDatasetRequest,
    UploadDatasetResponse,
)
from backend.app.schemas.ai import SQLRerunRequest, SQLRerunResponse
from backend.app.schemas.dataset_semantic import (
    DatasetAskRequest,
    DatasetAskResponse,
    DatasetDashboardResponse,
    DatasetInsightsResponse,
    DatasetSemanticResponse,
    UpdateDatasetSemanticRequest,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_service import DatasetService
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_insights_service import DatasetInsightsService
from backend.app.services.dataset_dashboard_service import DatasetDashboardService
from backend.app.services.dataset_navigation_service import DatasetNavigationResponse, DatasetNavigationService
from backend.app.services.dataset_workspace_service import (
    DatasetWorkspaceQuality,
    DatasetWorkspaceService,
    DatasetWorkspaceTables,
    WorkspaceCache,
)
from backend.app.services.dataset_anomaly_service import DatasetAnomalyService
from backend.app.services.anomaly_explain_service import DatasetAnomalyExplainService
from backend.app.schemas.anomaly_explain import AnomalyExplanationResponse
from backend.app.schemas.forecast import ForecastResponse
from backend.app.services.forecast_service import DatasetForecastService
from backend.app.schemas.report import ReportResponse
from backend.app.services.report_service import DatasetReportService, clear_report_cache
from backend.app.schemas.dataset_workspace import (
    WorkspaceAnomalyResponse,
    WorkspaceAnomalyScanResponse,
    WorkspaceAnalyticsResponse,
    WorkspaceDataQualityResponse,
    WorkspaceOverviewResponse,
    WorkspaceTableAnalysisResponse,
)
from backend.app.services.text_to_sql_service import TextToSQLService
from backend.app.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


def _invalidate_workspace(dataset_id: str) -> None:
    """Drop cached workspace pages for a dataset after its relationships/semantic model/existence change."""
    WorkspaceCache.invalidate(dataset_id)
    clear_report_cache(dataset_id)


def _workspace_call(dataset_id: str, what: str, fn):
    """Shared error mapping for the dataset workspace page endpoints."""
    _check_live_db()
    try:
        return fn()
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build {what} for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to build {what}.")


def _check_live_db():
    if is_fixture_mode():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dataset workspace requires live PostgreSQL database. Dynamic uploads are unavailable in fixture mode."
        )


@router.post(
    "",
    response_model=UploadDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and profile a new dataset (1-5 tabular files)"
)
@limiter.limit(settings.RATE_LIMIT_DATASET_UPLOAD)
def upload_dataset(
    request: Request,
    files: List[UploadFile] = File(..., description="1-5 CSV, TSV, or XLSX files"),
    dataset_name: Optional[str] = Form(None, description="Optional custom dataset name"),
    share_samples: bool = Form(False, description="Whether sample values may be used for LLM context"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token for dataset tenancy")
):
    """
    Safely ingest and profile 1-5 tabular files (CSV, TSV, XLSX) into an isolated PostgreSQL schema (ds_<8hex>).
    Deterministic zero-LLM profiling runs immediately upon upload.
    """
    _check_live_db()

    if not files or len(files) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one file is required.")
    if len(files) > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 5 files allowed per dataset upload.")

    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    files_data = []

    for f in files:
        filename = f.filename or "upload.csv"
        # Check allowed extensions
        lower_name = filename.lower()
        if not (lower_name.endswith(".csv") or lower_name.endswith(".tsv") or lower_name.endswith(".xlsx")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{filename}'. Only .csv, .tsv, and .xlsx files are supported."
            )

        # Plain `def` endpoint (runs in FastAPI's threadpool): read the spooled upload synchronously.
        content = f.file.read()
        if len(content) > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB."
            )
        files_data.append((filename, content))

    try:
        client_ip = get_client_ip(request)
        resp = DatasetService.upload_dataset(
            files_data=files_data,
            owner_token=x_owner_token,
            dataset_name=dataset_name,
            client_ip=client_ip
        )
        # Update share_samples if specified
        if share_samples:
            DatasetService.update_dataset(
                dataset_id=resp.dataset_id,
                req=UpdateDatasetRequest(share_samples=True),
                owner_token=resp.owner_token or x_owner_token
            )
        return resp
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to upload dataset: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Dataset processing error: {str(e)}")


@router.get(
    "",
    response_model=List[DatasetSummary],
    summary="List available datasets"
)
def list_datasets(
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token for tenancy filtering")
):
    """
    Returns datasets accessible to this session: the built-in demo dataset ('olist-demo')
    plus any active datasets uploaded with the provided owner token.
    """
    _check_live_db()
    try:
        return DatasetService.list_datasets(owner_token=x_owner_token)
    except Exception as e:
        logger.error(f"Failed to list datasets: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list datasets.")


@router.get(
    "/{dataset_id}",
    response_model=DatasetProfile,
    summary="Get comprehensive dataset profile"
)
def get_dataset_profile(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Retrieves full deterministic profile: tables, column statistics, roles,
    quality findings, and inferred relationships.
    """
    _check_live_db()
    try:
        return DatasetService.get_dataset_profile(dataset_id=dataset_id, owner_token=x_owner_token)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to retrieve dataset profile: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve dataset profile.")


@router.patch(
    "/{dataset_id}/columns",
    response_model=DatasetProfile,
    summary="Update dataset column roles, descriptions, or confirmed relationships"
)
def update_dataset(
    dataset_id: str,
    req: UpdateDatasetRequest,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Allows user to refine profiling results: override column roles,
    add column descriptions, confirm/reject inferred relationships, and toggle share_samples.
    """
    _check_live_db()
    try:
        result = DatasetService.update_dataset(dataset_id=dataset_id, req=req, owner_token=x_owner_token)
        _invalidate_workspace(dataset_id)  # confirmed relationships / column roles may have changed
        return result
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to update dataset: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update dataset.")


@router.get(
    "/{dataset_id}/preview",
    response_model=TablePreviewResponse,
    summary="Preview rows from a dataset table"
)
def preview_table(
    dataset_id: str,
    table: str = Query(..., description="Table name to preview"),
    limit: int = Query(50, ge=1, le=50, description="Max rows to return (capped at 50)"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Safely previews rows from a dataset table using readonly permissions.
    Always capped at 50 rows.
    """
    _check_live_db()
    try:
        return DatasetService.preview_table(
            dataset_id=dataset_id,
            table_name=table,
            limit=limit,
            owner_token=x_owner_token
        )
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to preview table {table}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to preview table.")


@router.delete(
    "/{dataset_id}",
    summary="Delete dataset and cascade drop its PostgreSQL schema"
)
def delete_dataset(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Deletes an uploaded dataset, drops its isolated schema (DROP SCHEMA ds_<8hex> CASCADE),
    and clears its metadata records. Cannot delete the built-in demo dataset.
    """
    _check_live_db()
    try:
        DatasetService.delete_dataset(dataset_id=dataset_id, owner_token=x_owner_token)
        _invalidate_workspace(dataset_id)
        return {"detail": "Dataset deleted successfully", "dataset_id": dataset_id}
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to delete dataset {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete dataset.")


# ==============================================================================
# Level 6: Dataset-Aware Semantic Layer, Q&A, and Insights Endpoints
# ==============================================================================

@router.post(
    "/{dataset_id}/semantic/generate",
    response_model=DatasetSemanticResponse,
    summary="Generate deterministic semantic layer draft with optional schema enrichment"
)
def generate_dataset_semantic(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Builds a draft semantic layer deterministically from dataset profiling:
    measures, dimensions, time columns, candidate keys, relationships, and 6-8 starter questions.
    """
    _check_live_db()
    try:
        result = DatasetSemanticService.generate_draft(dataset_id=dataset_id, owner_token=x_owner_token)
        _invalidate_workspace(dataset_id)  # semantic model changed
        return result
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to generate semantic layer for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{dataset_id}/semantic",
    response_model=DatasetSemanticResponse,
    summary="Retrieve semantic layer for dataset"
)
def get_dataset_semantic(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """Retrieves existing semantic model or generates initial draft."""
    _check_live_db()
    try:
        return DatasetSemanticService.get_semantic(dataset_id=dataset_id, owner_token=x_owner_token)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to retrieve semantic model for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch(
    "/{dataset_id}/semantic",
    response_model=DatasetSemanticResponse,
    summary="Update measures, dimensions, synonyms, and confirm semantic model"
)
def update_dataset_semantic(
    dataset_id: str,
    req: UpdateDatasetSemanticRequest,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """Allows dataset owner to refine definitions and confirm the semantic model (status='confirmed')."""
    _check_live_db()
    try:
        result = DatasetSemanticService.update_semantic(dataset_id=dataset_id, req=req, owner_token=x_owner_token)
        _invalidate_workspace(dataset_id)  # semantic model changed
        return result
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to update semantic model for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{dataset_id}/ask",
    response_model=DatasetAskResponse,
    summary="Ask business question over uploaded dataset using guarded Text-to-SQL"
)
@limiter.limit(settings.RATE_LIMIT_AI_ASK)
def ask_dataset(
    request: Request,
    dataset_id: str,
    req: DatasetAskRequest,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Translates natural language questions to guarded PostgreSQL queries within the dataset's schema.
    Enforces privacy policy: if share_samples is False, no cell values reach the LLM.
    """
    _check_live_db()
    try:
        return TextToSQLService.ask_dataset_sql(
            dataset_id=dataset_id,
            question=req.question,
            owner_token=x_owner_token,
            language=req.language or "auto",
            history=req.history,
        )
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to execute dataset ask for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{dataset_id}/rerun",
    response_model=SQLRerunResponse,
    summary="Re-run a pinned custom dataset SQL query through AST validator and tenant-isolated DB (zero LLM)"
)
@limiter.limit(settings.RATE_LIMIT_AI_ASK)
def rerun_dataset_pin(
    request: Request,
    dataset_id: str,
    req: SQLRerunRequest,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    _check_live_db()
    try:
        res = TextToSQLService.rerun_dataset_pin(
            dataset_id=dataset_id,
            sql=req.sql or "",
            owner_token=x_owner_token,
        )
        return SQLRerunResponse(**res)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except QueryTimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Query timed out, please retry")
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to re-run pinned query for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{dataset_id}/insights",
    response_model=DatasetInsightsResponse,
    summary="Get pre-computed quick insights and statistical anomalies for dataset"
)
def get_dataset_insights(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    Computes 3 validated insight queries (time trend, top-N, distribution) and
    runs generic rolling MAD anomaly detection if time series >= 30 points.
    """
    _check_live_db()
    try:
        return DatasetInsightsService.get_insights(dataset_id=dataset_id, owner_token=x_owner_token)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compute insights for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{dataset_id}/navigation",
    response_model=DatasetNavigationResponse,
    summary="Which sidebar sections apply to an uploaded dataset (tables + topic groups)"
)
def get_dataset_navigation(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """Deterministic: one item per table, plus Geography/Sellers/Payments/Delivery when a column matches."""
    _check_live_db()
    try:
        return DatasetNavigationService.get_navigation(dataset_id=dataset_id, owner_token=x_owner_token)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to build navigation for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build navigation.")


@router.get(
    "/{dataset_id}/dashboard",
    response_model=DatasetDashboardResponse,
    summary="Deterministic dashboard (KPIs, trend, breakdowns, data quality, anomalies) for an uploaded dataset"
)
def get_dataset_dashboard(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token")
):
    """
    No LLM involved. Sections that cannot be computed are returned as null with a reason
    in `section_errors`; the dashboard as a whole never fails because of one section.
    Not available for the built-in Olist demo dataset (400).
    """
    _check_live_db()
    try:
        return DatasetDashboardService.get_dashboard(dataset_id=dataset_id, owner_token=x_owner_token)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to build dashboard for {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build dashboard.")



# ==============================================================================
# Dataset-aware workspace pages (uploaded datasets only; deterministic, no LLM)
# ==============================================================================

@router.get("/{dataset_id}/overview", response_model=WorkspaceOverviewResponse,
            summary="Overview page data for an uploaded dataset (KPIs, monthly trend, breakdowns)")
def get_dataset_overview(
    dataset_id: str,
    limit: int = Query(8, ge=1, le=8, description="Maximum number of breakdowns"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "overview",
                           lambda: DatasetWorkspaceService.get_overview(dataset_id, owner_token=x_owner_token, limit=limit))


@router.get("/{dataset_id}/analytics", response_model=WorkspaceAnalyticsResponse,
            summary="Analytics page data: any measure, daily/weekly/monthly trend, breakdowns")
def get_dataset_analytics(
    dataset_id: str,
    metric: Optional[str] = Query(None, description="'table.column' or 'table.*' (row count); default = primary measure"),
    grain: str = Query("monthly", description="daily | weekly | monthly"),
    limit: int = Query(8, ge=1, le=8, description="Maximum number of breakdowns"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "analytics",
                           lambda: DatasetWorkspaceService.get_analytics(dataset_id, owner_token=x_owner_token,
                                                                         metric=metric, grain=grain, limit=limit))


@router.get("/{dataset_id}/tables/{table}/analysis", response_model=WorkspaceTableAnalysisResponse,
            summary="Table page: row count, column profile, KPIs, trend and safe breakdowns for one table")
def get_dataset_table_analysis(
    dataset_id: str,
    table: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "table analysis",
                           lambda: DatasetWorkspaceTables.get_table_analysis(dataset_id, x_owner_token, table))


@router.get("/{dataset_id}/groups/{group}/analysis", response_model=WorkspaceTableAnalysisResponse,
            summary="Topic page (geography | sellers | payments | delivery): the table analysis filtered to that group's columns")
def get_dataset_group_analysis(
    dataset_id: str,
    group: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "group analysis",
                           lambda: DatasetWorkspaceTables.get_group_analysis(dataset_id, x_owner_token, group))


@router.get("/{dataset_id}/data-quality", response_model=WorkspaceDataQualityResponse,
            summary="Live deterministic data-quality checks (keys, orphans, domains, missing values, join safety)")
def get_dataset_data_quality(
    dataset_id: str,
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "data quality",
                           lambda: DatasetWorkspaceQuality.get_data_quality(dataset_id, x_owner_token))


@router.get("/{dataset_id}/anomalies", response_model=WorkspaceAnomalyResponse,
            summary="Deterministic anomalies on an uploaded dataset's time series (MAD, STL, IQR slices, IsolationForest)")
def get_dataset_anomalies(
    dataset_id: str,
    metric: Optional[str] = Query(None, description="'table.column' or 'table.*'; default = primary measure"),
    grain: str = Query("daily", description="daily | weekly"),
    severity: Optional[str] = Query(None, description="high | medium | low"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "anomalies",
                           lambda: DatasetAnomalyService.get_anomalies(dataset_id, x_owner_token, metric=metric,
                                                                       grain=grain, severity=severity))


@router.get("/{dataset_id}/anomalies/explain", response_model=AnomalyExplanationResponse,
            summary="Explain an anomaly of an uploaded dataset: which groups drove it (deterministic waterfall)")
@limiter.limit(settings.RATE_LIMIT_ANOMALY_EXPLAIN)
def explain_dataset_anomaly(
    request: Request,
    dataset_id: str,
    period: str = Query(..., description="YYYY-MM-DD (weekly: any day of the week)"),
    metric: Optional[str] = Query(None, description="'table.column' or 'table.*'; default = primary measure"),
    grain: str = Query("daily", description="daily | weekly"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "anomaly explanation",
                           lambda: DatasetAnomalyExplainService.explain(dataset_id, x_owner_token, metric=metric,
                                                                        period=period, grain=grain))


@router.get("/{dataset_id}/forecast", response_model=ForecastResponse,
            summary="Baseline forecast with 80% / 95% bands for an uploaded dataset (deterministic ETS, no LLM)")
@limiter.limit(settings.RATE_LIMIT_FORECAST)
def get_dataset_forecast(
    request: Request,
    dataset_id: str,
    metric: Optional[str] = Query(None, description="'table.column' or 'table.*' (SUM / COUNT measures); default = main measure"),
    horizon: int = Query(3, ge=1, le=6, description="Months ahead (1-6)"),
    exclude_anomalies: bool = Query(False, description="Replace flagged anomaly days by their expected value"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "forecast",
                           lambda: DatasetForecastService.forecast(dataset_id, x_owner_token, metric=metric, horizon=horizon,
                                                                   exclude_anomalies=exclude_anomalies))


@router.get("/{dataset_id}/report", response_model=ReportResponse,
            summary="One-click report for an uploaded dataset (format=json | pdf; deterministic templates, no LLM)")
@limiter.limit(settings.RATE_LIMIT_REPORT)
def get_dataset_report(
    request: Request,
    dataset_id: str,
    format: str = Query("json", pattern="^(json|pdf)$", description="json | pdf"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    from backend.app.routers.report import report_response
    return _workspace_call(dataset_id, "report",
                           lambda: report_response(DatasetReportService.build(dataset_id, x_owner_token), format))


@router.post("/{dataset_id}/anomalies/scan", response_model=WorkspaceAnomalyScanResponse,
             summary="Scan every time-based measure of an uploaded dataset (rate-limited like the Olist scan)")
@limiter.limit("10/minute")
def scan_dataset_anomalies(
    request: Request,
    dataset_id: str,
    grain: str = Query("daily", description="daily | weekly"),
    x_owner_token: Optional[str] = Header(None, alias="X-Owner-Token", description="Owner token"),
):
    return _workspace_call(dataset_id, "anomaly scan",
                           lambda: DatasetAnomalyService.scan(dataset_id, x_owner_token, grain=grain))
