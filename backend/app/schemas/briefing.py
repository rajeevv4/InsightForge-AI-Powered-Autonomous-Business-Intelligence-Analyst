from typing import List
from pydantic import BaseModel, Field


class BriefingThresholds(BaseModel):
    max_late_delivery_pct: float = Field(default=7.0, ge=0.0, le=100.0, description="Alert when delayed delivery share exceeds this %")
    min_csat: float = Field(default=4.2, ge=1.0, le=5.0, description="Alert when average CSAT falls below this score")
    min_mom_revenue_pct: float = Field(default=-15.0, ge=-100.0, le=100.0, description="Alert when latest MoM revenue change drops below this %")
    max_high_anomalies: int = Field(default=0, ge=0, le=100, description="Alert when high-severity anomaly count exceeds this number")


class ThresholdAlert(BaseModel):
    id: str
    label: str
    metric: str
    current_value: float
    threshold: float
    operator: str
    triggered: bool
    severity: str = Field(description="'ok' | 'warning' | 'critical'")
    message: str


class MorningBriefingResponse(BaseModel):
    headline: str
    bullets: List[str]
    alerts: List[ThresholdAlert]
    triggered_count: int
    thresholds: BriefingThresholds
    generated_at: str
    cached: bool = False
