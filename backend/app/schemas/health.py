from pydantic import BaseModel, Field
from typing import Literal

class HealthResponse(BaseModel):
    status: str = Field(..., example="healthy")
    database: str = Field(..., example="connected")
    data_source: Literal["postgres", "fixture"] = Field(..., example="postgres")
    service: str = Field(..., example="InsightForge")
    version: str = Field(..., example="0.1.0")
