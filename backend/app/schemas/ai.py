from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AskAIRequest(BaseModel):
    question: str = Field(
        ...,
        description="The natural language business question to ask InsightForge",
        examples=["Which category generated the highest revenue?"]
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Question cannot be empty or only whitespace.")
        if len(cleaned) < 3:
            raise ValueError("Question must be at least 3 characters long.")
        if len(cleaned) > 500:
            raise ValueError("Question must not exceed 500 characters.")
        return cleaned


class AIEvidence(BaseModel):
    source: str = Field(default="PostgreSQL analytics", description="Data source provenance")
    intent: str = Field(..., description="Target business intent resolved")
    metric: str = Field(..., description="Primary metric or scope evaluated")
    data: Any = Field(..., description="Validated raw analytics payload")


class AskAIResponse(BaseModel):
    question: str = Field(..., description="Original user question")
    intent: str = Field(..., description="Classified intent name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score in intent classification (0.0 to 1.0)")
    reason: str = Field(..., description="Reasoning behind intent classification")
    answer: str = Field(..., description="Concise, evidence-grounded AI explanation")
    evidence: Optional[AIEvidence] = Field(default=None, description="Grounding data evidence from analytics layer")
    rephrase_suggested: bool = Field(default=False, description="True if intent confidence was below threshold")
