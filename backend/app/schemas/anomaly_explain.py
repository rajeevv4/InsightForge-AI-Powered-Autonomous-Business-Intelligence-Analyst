"""Response models for "Explain this anomaly" (root-cause waterfall). All text is template-generated."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExplainHeadline(BaseModel):
    observed: float
    expected: float
    change_abs: float
    change_pct: Optional[float] = Field(None, description="None when expected is 0")
    direction: str = Field(..., description="spike | drop")
    source: str = Field(..., description="detector | time_series_baseline | trailing_baseline")
    method: Optional[str] = Field(None, description="Detector that flagged the period, if any")
    severity: Optional[str] = None
    sentence: str


class ExplainDriver(BaseModel):
    label: str
    observed: float
    expected: float
    contribution: float
    share_of_change_pct: Optional[float] = None
    sentence: str


class WaterfallStep(BaseModel):
    name: str
    kind: str = Field(..., description="total | up | down | other")
    start: float
    end: float
    value: float = Field(..., description="end - start for steps, the level for totals")


class ExplainDimension(BaseModel):
    key: str
    label: str
    explanatory_power: float = Field(..., description="0..1: share of the change explained by the top 3 groups")
    mix_shift: float = Field(0.0, description="0..1: how far the group mix of this period moved from the baseline mix "
                                                "(total variation distance). 0 = every group moved proportionally.")
    rank_score: float = Field(0.0, description="explanatory_power x mix_shift; tabs are ordered by this (best first)")
    groups: int
    drivers: List[ExplainDriver]
    other_contribution: float = 0.0
    other_groups: int = 0
    waterfall: List[WaterfallStep]
    summary: str
    join_path: Optional[str] = None


class ExplainTopDriver(BaseModel):
    dimension: str
    label: str
    contribution: float
    share_of_change_pct: Optional[float] = None
    sentence: str


class VolumeValue(BaseModel):
    volume_label: str
    value_label: str
    volume_observed: float
    volume_expected: float
    value_observed: Optional[float] = None
    value_expected: Optional[float] = None
    volume_effect: float
    value_effect: float
    dominant: str = Field(..., description="volume | value")
    sentences: List[str]


class SkippedDimension(BaseModel):
    dimension: str
    reason: str


class AnomalyExplanationResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    metric: str
    metric_label: str
    period: str
    grain: str
    currency: Optional[str] = Field(None, description="'R$' for the Olist demo, None for uploaded datasets")
    unit: str = Field("number", description="currency | count | percent | score | number")
    additive: bool = True
    baseline_window: str = ""
    baseline_periods: int = 0
    headline: Optional[ExplainHeadline] = None
    dimensions: List[ExplainDimension] = Field(default_factory=list)
    top_drivers: List[ExplainTopDriver] = Field(default_factory=list)
    volume_value: Optional[VolumeValue] = None
    skipped_dimensions: List[SkippedDimension] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    section_errors: Dict[str, str] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None
    cached: bool = False
