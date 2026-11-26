from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ConversationTurn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Previous user question in the conversation")
    sql: Optional[str] = Field(default=None, max_length=4000, description="Validated SQL generated for that turn (never result rows)")
    intent: Optional[str] = Field(default=None, max_length=100, description="Resolved intent if handled by intent router")


class AskAIRequest(BaseModel):
    question: str = Field(
        ...,
        description="The natural language business question to ask InsightForge",
        examples=["Which category generated the highest revenue?"]
    )
    history: Optional[List[ConversationTurn]] = Field(
        default=None,
        max_length=10,
        description="Optional prior conversation turns (question + SQL only, no result rows)"
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
    language: str = Field(default="en", description="Detected query and response language ('en', 'hi', 'hinglish')")
    rephrase_suggested: bool = Field(default=False, description="True if intent confidence was below threshold")
    grounding_verified: bool = Field(default=True, description="True if output numbers are grounded in evidence; False if verification failed and fallback was triggered")


class SQLAskResponse(BaseModel):
    question: str = Field(..., description="The original business query")
    route: str = Field(..., description="'intent' if handled by deterministic router; 'text_to_sql' if handled by guarded SQL engine")
    intent: Optional[str] = Field(default=None, description="Resolved intent name when route='intent'")
    sql: Optional[str] = Field(default=None, description="The validated and executed SQL query (if text_to_sql route)")
    explanation: str = Field(..., description="Synthesized grounded answer")
    assumptions: Optional[List[str]] = Field(default=None, description="Assumptions or filters applied during SQL construction")
    rows: Optional[List[Dict[str, Any]]] = Field(default=None, description="Capped rows returned by PostgreSQL (max 500)")
    columns: Optional[List[str]] = Field(default=None, description="Column names returned")
    row_count: int = Field(default=0, description="Number of rows returned")
    language: str = Field(default="en", description="Detected query and response language ('en', 'hi', 'hinglish')")
    grounding_verified: bool = Field(default=True, description="True if output numbers are faithful to row evidence")
    suggested_chart: Optional[str] = Field(default=None, description="Suggested visualization ('bar', 'line', 'pie', 'table')")
    error: Optional[str] = Field(default=None, description="Error or diagnostic detail if query failed")


class SQLRerunRequest(BaseModel):
    route: str = Field(default="text_to_sql", pattern="^(intent|text_to_sql)$", description="Execution route ('intent' or 'text_to_sql')")
    intent: Optional[str] = Field(default=None, max_length=100, description="Canonical intent name when route='intent'")
    sql: Optional[str] = Field(default=None, max_length=4000, description="SQL SELECT query to re-validate and execute")


class SQLRerunResponse(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    sql: Optional[str] = None
    execution_time_ms: float = 0.0


class AIAuditLogItem(BaseModel):
    id: Optional[int] = Field(default=None, description="Primary key id of the audit entry")
    question: str = Field(..., description="User query submitted")
    intent: Optional[str] = Field(default=None, description="Classified intent or route")
    generated_sql: Optional[str] = Field(default=None, description="SQL query generated or executed")
    latency_ms: float = Field(..., description="Total execution time in milliseconds")
    success: bool = Field(..., description="True if request completed successfully")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
