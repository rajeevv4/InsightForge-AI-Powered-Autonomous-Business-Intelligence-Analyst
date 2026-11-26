"""Response model for the one-click report (deterministic: every sentence is a fixed template)."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ReportKPI(BaseModel):
    label: str
    value: Optional[float] = None
    display: str


class ReportTrendPoint(BaseModel):
    period: str
    value: float


class ReportTrend(BaseModel):
    title: str
    points: List[ReportTrendPoint] = Field(default_factory=list)


class ReportBreakdownItem(BaseModel):
    label: str
    value: Optional[float] = None
    display: str
    share_pct: Optional[float] = None


class ReportBreakdown(BaseModel):
    title: str
    items: List[ReportBreakdownItem] = Field(default_factory=list)
    other_groups: int = 0
    other_display: Optional[str] = None
    total_value: Optional[float] = None
    total_line: Optional[str] = Field(None, description="'All groups total: X' (SUM-type measures only)")


class ReportAnomaly(BaseModel):
    period: str
    metric_label: str
    direction: str
    severity: str
    method: str
    observed_display: str
    expected_display: str
    driver_sentence: str


class ReportForecastPoint(BaseModel):
    period: str
    expected: float
    lower_80: float
    upper_80: float
    expected_display: str
    range_display: str


class ReportForecast(BaseModel):
    metric_label: str
    status: str
    reliability: Optional[str] = None
    reason: Optional[str] = None
    model: Optional[str] = None
    training_window: Optional[str] = None
    mape: Optional[float] = None
    naive_mape: Optional[float] = None
    points: List[ReportForecastPoint] = Field(default_factory=list)
    disclaimer: str = ""


class ReportDQRow(BaseModel):
    check: str
    status: str = Field(..., description="PASS | WARN | FAIL")
    detail: str


class ReportResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    is_demo: bool = False
    currency: Optional[str] = None
    generated_at: datetime
    period: Optional[str] = None
    row_counts: Dict[str, int] = Field(default_factory=dict)
    total_rows: Optional[int] = None
    summary: Optional[List[str]] = None
    kpis: Optional[List[ReportKPI]] = None
    trend: Optional[ReportTrend] = None
    breakdowns: Optional[List[ReportBreakdown]] = None
    anomalies: Optional[List[ReportAnomaly]] = None
    anomaly_count: Optional[int] = None
    forecast: Optional[ReportForecast] = None
    data_quality: Optional[List[ReportDQRow]] = None
    caveats: List[str] = Field(default_factory=list)
    methodology: List[str] = Field(default_factory=list)
    section_errors: Dict[str, str] = Field(default_factory=dict, description="section -> reason; shown as 'Section unavailable: <reason>'")
    budget_seconds: float = 45.0
    elapsed_seconds: float = 0.0
    cached: bool = False
