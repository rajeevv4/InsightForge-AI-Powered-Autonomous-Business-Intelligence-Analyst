from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = Field(..., example="healthy")
    database: str = Field(..., example="connected")
    service: str = Field(..., example="InsightForge")
    version: str = Field(..., example="0.1.0")
