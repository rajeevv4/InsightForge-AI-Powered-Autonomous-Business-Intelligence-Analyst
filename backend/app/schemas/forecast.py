"""Response models for the baseline forecast (deterministic, no LLM)."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ForecastMetricOption(BaseModel):
    key: str
    label: str
    aggregation: str


class ForecastHistoryPoint(BaseModel):
    period: str = Field(..., description="YYYY-MM")
    value: float = Field(..., description="Value used for training (after anomaly-day adjustment, if any)")
    raw_value: Optional[float] = Field(None, description="Original value when it was adjusted")


class ForecastPoint(BaseModel):
    period: str
    expected: float
    lower_80: float
    upper_80: float
    lower_95: float
    upper_95: float


class BacktestPoint(BaseModel):
    period: str
    actual: float
    forecast: float
    naive: float


class ForecastBacktest(BaseModel):
    holdout: str
    mape: Optional[float] = None
    naive_mape: Optional[float] = None
    naive_method: str
    beats_naive: bool
    points: List[BacktestPoint] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    metric: Optional[str] = None
    metric_label: Optional[str] = None
    metrics: List[ForecastMetricOption] = Field(default_factory=list)
    currency: Optional[str] = Field(None, description="'R$' for the Olist demo, None for uploaded datasets")
    horizon: int
    exclude_anomalies: bool = False
    excluded_days: int = 0
    status: str = Field(..., description="ok | refused")
    reason: Optional[str] = None
    reliability: Optional[str] = Field(None, description="Good | Fair | Weak")
    model: Optional[str] = None
    model_kind: Optional[str] = Field(None, description="monthly | daily")
    training_window: Optional[str] = None
    history: List[ForecastHistoryPoint] = Field(default_factory=list)
    forecast: List[ForecastPoint] = Field(default_factory=list)
    backtest: Optional[ForecastBacktest] = None
    notes: List[str] = Field(default_factory=list)
    disclaimer: str = "Baseline forecast: ignores promotions, price changes and one-off events."
    section_errors: Dict[str, str] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None
    cached: bool = False
