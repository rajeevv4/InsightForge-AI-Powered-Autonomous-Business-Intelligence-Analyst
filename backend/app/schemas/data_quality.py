from typing import Dict, List
from pydantic import BaseModel, Field

class DataQualityResponse(BaseModel):
    audit_status: str = Field(..., example="PASS")
    table_row_counts: Dict[str, int]
    missing_value_summary: Dict[str, int]
    primary_key_uniqueness: str
    foreign_key_integrity: str
    domain_bounds_status: str
    order_status_breakdown: Dict[str, int]
    join_safety_status: str
    anomalies_flagged: List[str]
