from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    id: Optional[str] = None
    original_name: str
    safe_name: str
    pg_type: str
    role: str = Field(description="Role: id, datetime, measure, dimension, boolean, free_text")
    null_pct: float = 0.0
    distinct_count: int = 0
    min_val: Optional[str] = None
    max_val: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)
    user_description: Optional[str] = None


class TableProfile(BaseModel):
    id: Optional[str] = None
    original_name: str
    safe_name: str
    row_count: int = 0
    column_count: int = 0
    candidate_pk: Optional[str] = None
    candidate_time_column: Optional[str] = None
    quality_findings: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[ColumnProfile] = Field(default_factory=list)


class RelationshipProfile(BaseModel):
    id: Optional[str] = None
    parent_table: str
    parent_column: str
    child_table: str
    child_column: str
    cardinality: str = Field(description="'1:1' or '1:N'")
    confidence: float = 0.0
    confirmed: bool = False


class DatasetSummary(BaseModel):
    id: str
    name: str
    schema_name: str
    status: str
    share_samples: bool
    table_count: int = 0
    total_rows: int = 0
    size_bytes: int = 0
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_demo: bool = False


class DatasetProfile(BaseModel):
    id: str
    name: str
    schema_name: str
    status: str
    share_samples: bool
    source_files: List[str] = Field(default_factory=list)
    size_bytes: int = 0
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_demo: bool = False
    tables: List[TableProfile] = Field(default_factory=list)
    relationships: List[RelationshipProfile] = Field(default_factory=list)


class UploadDatasetResponse(BaseModel):
    dataset_id: str
    name: str
    schema_name: str
    owner_token: Optional[str] = None
    tables_count: int
    total_rows: int
    expires_at: Optional[datetime] = None
    message: str


class UpdateDatasetRequest(BaseModel):
    share_samples: Optional[bool] = None
    column_updates: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of {table_name, column_name, role, user_description}"
    )
    confirmed_relationships: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of {parent_table, parent_column, child_table, child_column, confirmed}"
    )


class TablePreviewResponse(BaseModel):
    dataset_id: str
    table_name: str
    total_rows: int
    preview_rows_count: int
    columns: List[str]
    rows: List[Dict[str, Any]]
