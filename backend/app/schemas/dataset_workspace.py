"""Schemas for the dataset-aware workspace pages (uploaded datasets only; deterministic, no LLM)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.anomaly import AnomalyItem, AnomalyTimeSeriesPoint
from backend.app.schemas.dataset_semantic import (
    DashboardBreakdown,
    DashboardKPI,
    DashboardSkippedBreakdown,
    DashboardTrend,
)


class MetricOption(BaseModel):
    key: str = Field(description="'table.column', or 'table.*' for a row count")
    label: str
    table: str
    column: Optional[str] = None
    aggregation: str


class WorkspaceSectionBase(BaseModel):
    dataset_id: str
    dataset_name: str
    section_errors: Dict[str, str] = Field(default_factory=dict, description="section -> short reason when it is null")
    cached: bool = False
    generated_at: datetime


class WorkspaceOverviewResponse(WorkspaceSectionBase):
    primary_measure: Optional[str] = None
    kpis: Optional[List[DashboardKPI]] = None
    trend: Optional[DashboardTrend] = None
    breakdowns: Optional[List[DashboardBreakdown]] = None
    skipped_breakdowns: List[DashboardSkippedBreakdown] = Field(default_factory=list)
    quality_summary: Optional[Dict[str, Any]] = Field(None, description="{tables, findings, by_severity} from the stored profile")


class WorkspaceAnalyticsResponse(WorkspaceSectionBase):
    metrics: List[MetricOption] = Field(default_factory=list)
    metric: Optional[str] = None
    grain: str = "monthly"
    available_grains: List[str] = Field(default_factory=list)
    time_column: Optional[str] = None
    trend: Optional[DashboardTrend] = None
    breakdowns: Optional[List[DashboardBreakdown]] = None
    skipped_breakdowns: List[DashboardSkippedBreakdown] = Field(default_factory=list)


class ColumnSummary(BaseModel):
    name: str
    pg_type: str
    role: str
    null_pct: float = 0.0
    distinct_count: int = 0
    min_val: Optional[str] = None
    max_val: Optional[str] = None


class WorkspaceTableAnalysisResponse(WorkspaceSectionBase):
    table: str
    group: Optional[str] = Field(None, description="geography | sellers | payments | delivery when this is a topic-group view")
    row_count: int = 0
    columns: List[ColumnSummary] = Field(default_factory=list)
    matched_columns: List[str] = Field(default_factory=list, description="group views: table.column that matched the group")
    kpis: Optional[List[DashboardKPI]] = None
    primary_measure: Optional[str] = None
    trend: Optional[DashboardTrend] = None
    breakdowns: Optional[List[DashboardBreakdown]] = None
    skipped_breakdowns: List[DashboardSkippedBreakdown] = Field(default_factory=list)


class DataQualityCheck(BaseModel):
    check: str = Field(description="primary_key | foreign_key | negative_values | future_dates | missing_values | join_safety")
    table: str
    column: Optional[str] = None
    status: str = Field(description="PASS | WARN | FAIL | SKIPPED")
    value: Optional[float] = None
    detail: str = ""


class WorkspaceDataQualityResponse(WorkspaceSectionBase):
    # Same top-level fields as the Olist /api/data-quality response, so the page visuals map 1:1
    audit_status: str = "PASS"
    table_row_counts: Dict[str, int] = Field(default_factory=dict)
    missing_value_summary: Dict[str, int] = Field(default_factory=dict)
    primary_key_uniqueness: str = ""
    foreign_key_integrity: str = ""
    domain_bounds_status: str = ""
    order_status_breakdown: Dict[str, int] = Field(default_factory=dict, description="breakdown of the first *status* column, if any")
    join_safety_status: str = ""
    anomalies_flagged: List[str] = Field(default_factory=list)
    # Dataset-specific detail
    checks: List[DataQualityCheck] = Field(default_factory=list)
    status_column: Optional[str] = None


class WorkspaceAnomalyResponse(WorkspaceSectionBase):
    # Mirrors AnomalyListResponse (total_anomalies, grain, metric, anomalies, time_series, slice_outliers)
    total_anomalies: int = 0
    grain: str = "daily"
    metric: str = ""
    anomalies: List[AnomalyItem] = Field(default_factory=list)
    time_series: List[AnomalyTimeSeriesPoint] = Field(default_factory=list)
    slice_outliers: List[AnomalyItem] = Field(default_factory=list)
    metrics: List[MetricOption] = Field(default_factory=list)
    methods_run: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WorkspaceAnomalyScanResponse(BaseModel):
    dataset_id: str
    scan_id: str
    status: str
    anomalies_detected: int
    high_severity_count: int
    scanned_metrics: List[str]
    anomalies: List[AnomalyItem]
    slice_outliers: List[AnomalyItem] = Field(default_factory=list)
