from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

AnomalySeverity = Literal["low", "medium", "high"]
AnomalyDirection = Literal["spike", "drop"]
AnomalyMethod = Literal["rolling_zscore", "stl_residual", "iqr_dimension", "isolation_forest"]


class AnomalyItem(BaseModel):
    metric: str = Field(..., description="Target business metric (e.g. gross_revenue, order_count, aov)")
    dimension: str = Field(..., description="Dimension slice (e.g. overall, category:watches_gifts, state:SP)")
    period: str = Field(..., description="Timestamp or calendar period (YYYY-MM-DD or YYYY-Www)")
    observed: float = Field(..., description="Actual observed metric value")
    expected: float = Field(..., description="Expected/baseline predicted value")
    deviation_score: float = Field(..., description="Statistical deviation score (z-score, residual ratio, or anomaly score)")
    severity: AnomalySeverity = Field(..., description="Assessed severity level")
    direction: AnomalyDirection = Field(..., description="Direction of deviation (spike or drop)")
    method: AnomalyMethod = Field(..., description="Detection algorithm employed")
    known_event_candidate: Optional[str] = Field(None, description="Known calendar/promotional event candidate (e.g. Black Friday 2017)")


class AnomalyTimeSeriesPoint(BaseModel):
    period: str
    observed: float
    expected: float
    is_anomaly: bool = False
    severity: Optional[str] = None
    direction: Optional[str] = None
    known_event: Optional[str] = None


class AnomalyListResponse(BaseModel):
    total_anomalies: int
    grain: str
    metric: str
    anomalies: List[AnomalyItem]
    time_series: List[AnomalyTimeSeriesPoint]


class AnomalyScanRequest(BaseModel):
    metrics: Optional[List[str]] = Field(default=None, description="Metrics to scan (default: all core metrics)")
    grain: Optional[str] = Field(default="daily", description="Time grain ('daily' or 'weekly')")


class AnomalyScanResponse(BaseModel):
    scan_id: str
    status: str
    anomalies_detected: int
    high_severity_count: int
    scanned_metrics: List[str]
    anomalies: List[AnomalyItem]
