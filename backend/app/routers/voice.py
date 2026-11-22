import logging
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from backend.app.config import settings
from backend.app.limiter import limiter
from backend.app.schemas.voice import VoiceTranscribeResponse
from backend.app.services.voice_service import (
    VoiceService,
    AudioValidationError,
    GeminiKeyMissingError,
    VoiceQuotaExceededError,
    VoiceTranscriptionError
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/voice",
    tags=["Voice AI & Speech Transcription"]
)


@router.post(
    "/transcribe",
    response_model=VoiceTranscribeResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe Multilingual Audio Query (Hindi, English, Hinglish)",
    description=(
        "Accepts multipart audio files (max 60 seconds / 10 MB, webm, ogg, wav, mp3, m4a), "
        "validates audio content, and transcribes speech to text using Google Gemini Audio API. "
        "Strictly logs metadata only (no audio is saved to disk or database)."
    )
)
@limiter.limit(settings.RATE_LIMIT_VOICE_TRANSCRIBE)
async def transcribe_voice(request: Request, file: UploadFile = File(...)) -> VoiceTranscribeResponse:
    try:
        content_type = file.content_type or "audio/webm"
        audio_bytes = await file.read()

        response = await run_in_threadpool(VoiceService.transcribe_audio, audio_bytes, content_type)
        return response

    except AudioValidationError as e:
        logger.warning(f"Audio validation error: {e}")
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e)
        )
    except GeminiKeyMissingError as e:
        logger.warning(f"Gemini API key missing for voice transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except VoiceQuotaExceededError as e:
        logger.warning(f"Voice transcription quota exceeded: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except VoiceTranscriptionError as e:
        logger.error(f"Voice transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during voice transcription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during audio transcription. Please try again."
        )
