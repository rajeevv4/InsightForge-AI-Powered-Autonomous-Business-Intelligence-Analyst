import logging
from typing import List, Optional
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile, status

from backend.app.config import settings
from backend.app.fixture_guard import is_fixture_mode
from backend.app.limiter import limiter
from backend.app.schemas.dataset import (
    DatasetProfile,
    DatasetSummary,
    TablePreviewResponse,
    UpdateDatasetRequest,
    UploadDatasetResponse,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


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
async def upload_dataset(
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

        content = await f.read()
        if len(content) > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB."
            )
        files_data.append((filename, content))

    try:
        resp = DatasetService.upload_dataset(
            files_data=files_data,
            owner_token=x_owner_token,
            dataset_name=dataset_name
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
async def list_datasets(
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
async def get_dataset_profile(
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
async def update_dataset(
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
        return DatasetService.update_dataset(dataset_id=dataset_id, req=req, owner_token=x_owner_token)
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
async def preview_table(
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
async def delete_dataset(
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
        return {"detail": "Dataset deleted successfully", "dataset_id": dataset_id}
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to delete dataset {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete dataset.")
