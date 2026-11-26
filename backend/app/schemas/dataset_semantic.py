from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MeasureDefinition(BaseModel):
    name: str = Field(description="Display name of the measure")
    safe_name: str = Field(description="SQL safe identifier")
    table: str = Field(description="Table containing this measure")
    column: Optional[str] = Field(None, description="Column name or None if row count")
    aggregation: str = Field(default="SUM", description="Aggregation function: SUM, AVG, COUNT, MIN, MAX")
    formula: Optional[str] = Field(None, description="SQL expression if custom")
    description: Optional[str] = Field(None, description="Metric business description")
    synonyms: List[str] = Field(default_factory=list, description="Alternative names / search terms")


class DimensionDefinition(BaseModel):
    name: str = Field(description="Display name of the dimension")
    safe_name: str = Field(description="SQL safe identifier")
    table: str = Field(description="Table containing this dimension")
    column: str = Field(description="Column name")
    data_type: str = Field(description="Data type (e.g. TEXT, VARCHAR)")
    description: Optional[str] = Field(None, description="Business meaning of this dimension")
    synonyms: List[str] = Field(default_factory=list, description="Alternative names / search terms")


class TimeColumnDefinition(BaseModel):
    name: str
    safe_name: str
    table: str
    column: str
    data_type: str


class CandidateKeyDefinition(BaseModel):
    table: str
    column: str


class RelationshipDefinition(BaseModel):
    parent_table: str
    parent_column: str
    child_table: str
    child_column: str
    cardinality: str = Field(description="'1:1' or '1:N'")
    confirmed: bool = False


class SemanticModel(BaseModel):
    dataset_id: str
    dataset_name: str
    measures: List[MeasureDefinition] = Field(default_factory=list)
    dimensions: List[DimensionDefinition] = Field(default_factory=list)
    time_columns: List[TimeColumnDefinition] = Field(default_factory=list)
    candidate_keys: List[CandidateKeyDefinition] = Field(default_factory=list)
    relationships: List[RelationshipDefinition] = Field(default_factory=list)
    user_notes: Optional[str] = None


class DatasetSemanticResponse(BaseModel):
    dataset_id: str
    status: str = Field(default="draft", description="'draft' | 'confirmed'")
    semantic_model: SemanticModel
    starter_questions: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UpdateDatasetSemanticRequest(BaseModel):
    status: Optional[str] = Field(None, description="'draft' | 'confirmed'")
    measures: Optional[List[MeasureDefinition]] = None
    dimensions: Optional[List[DimensionDefinition]] = None
    relationships: Optional[List[RelationshipDefinition]] = None
    starter_questions: Optional[List[str]] = None
    user_notes: Optional[str] = None


from backend.app.schemas.ai import ConversationTurn


class DatasetAskRequest(BaseModel):
    question: str
    language: Optional[str] = Field(default="auto", description="'auto', 'en', 'hi', or 'hinglish'")
    history: Optional[List[ConversationTurn]] = Field(
        default=None,
        max_length=10,
        description="Optional prior conversation turns (question + SQL only, no result rows)"
    )


class DatasetAskResponse(BaseModel):
    question: str
    sql: str
    explanation: str
    suggested_chart: str = Field(default="table", description="'bar' | 'line' | 'pie' | 'table'")
    assumptions: List[str] = Field(default_factory=list)
    data_rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    privacy_badge: str = Field(description="'AI sees: schema only' | 'AI sees: schema + data'")
    execution_time_ms: float = 0.0
    row_count: int = 0


class InsightChartSpec(BaseModel):
    title: str
    chart_type: str = Field(description="'line' | 'bar' | 'pie' | 'table'")
    sql: str
    x_axis: str
    y_axis: str
    data: List[Dict[str, Any]] = Field(default_factory=list)


class DatasetInsightsResponse(BaseModel):
    dataset_id: str
    time_trend: Optional[InsightChartSpec] = None
    top_n: Optional[InsightChartSpec] = None
    distribution: Optional[InsightChartSpec] = None
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset Dashboard (uploaded datasets only; deterministic, no LLM)
# ---------------------------------------------------------------------------

class DashboardKPI(BaseModel):
    label: str
    table: str
    column: Optional[str] = Field(None, description="None for row-count KPIs")
    aggregation: str = Field(description="COUNT | SUM | AVG | MIN | MAX")
    value: Optional[float] = None
    error: Optional[str] = Field(None, description="Short reason if this KPI could not be computed")


class DashboardTrend(BaseModel):
    title: str
    table: str
    measure_column: str
    measure_label: str
    aggregation: str
    time_column: str
    points: List[Dict[str, Any]] = Field(default_factory=list, description="[{period: 'YYYY-MM-DD', value: number}] monthly")


class DashboardBreakdownItem(BaseModel):
    label: str
    value: Optional[float] = None
    row_count: int = 0


class DashboardBreakdown(BaseModel):
    title: str
    dimension_table: str
    dimension_column: str
    dimension_label: str
    measure_label: str
    aggregation: str
    join_path: Optional[str] = Field(None, description="e.g. 'orders.customer_id -> customers.customer_id (N:1)'; None if same table")
    items: List[DashboardBreakdownItem] = Field(default_factory=list, description="Top values, largest first")
    other_value: Optional[float] = Field(None, description="SUM of all remaining groups (SUM measures only)")
    other_groups: int = 0
    total_value: Optional[float] = Field(None, description="SUM over all groups incl. blanks (SUM measures only)")
    truncated: bool = False


class DashboardSkippedBreakdown(BaseModel):
    dimension: str = Field(description="table.column")
    reason: str


class DashboardQualityTable(BaseModel):
    table: str
    row_count: int
    findings: List[Dict[str, Any]] = Field(default_factory=list)


class DashboardAnomalies(BaseModel):
    measure_label: Optional[str] = None
    method: str = "rolling_mad_zscore"
    items: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


class DatasetDashboardResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    primary_measure: Optional[str] = Field(None, description="table.column used for trend/breakdowns")
    kpis: Optional[List[DashboardKPI]] = None
    trend: Optional[DashboardTrend] = None
    breakdowns: Optional[List[DashboardBreakdown]] = None
    skipped_breakdowns: List[DashboardSkippedBreakdown] = Field(default_factory=list)
    data_quality: Optional[List[DashboardQualityTable]] = None
    anomalies: Optional[DashboardAnomalies] = None
    section_errors: Dict[str, str] = Field(
        default_factory=dict,
        description="Section name -> short reason when that section is null/unavailable"
    )
