from typing import Optional
from pydantic import BaseModel, Field


class VoiceTranscribeResponse(BaseModel):
    text: str = Field(..., description="Exact transcribed speech text")
    detected_language: str = Field(..., description="Detected language ('hi', 'en', 'hinglish')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Transcription confidence score (0.0 to 1.0)")
    duration_est_s: Optional[float] = Field(default=None, description="Estimated audio duration in seconds")
