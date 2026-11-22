import io
import json
import logging
import re
import time
from typing import Dict, Any, Optional, Tuple

from backend.app.config import settings
from backend.app.schemas.voice import VoiceTranscribeResponse
from backend.app.services.audit_service import AIAuditService

logger = logging.getLogger(__name__)

# Try importing official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai SDK not available in environment.")


class VoiceTranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


class VoiceQuotaExceededError(Exception):
    """Raised when Gemini audio transcription quota is exceeded or rate limited."""
    pass


class GeminiKeyMissingError(Exception):
    """Raised when Gemini API key is missing for voice transcription."""
    pass


class AudioValidationError(Exception):
    """Raised when audio file payload is invalid or unsupported."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# Allowed audio MIME types
ALLOWED_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a"
}

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_audio_content(audio_bytes: bytes, declared_mime: str) -> str:
    """
    Validates audio size and magic bytes against allowed audio formats.
    Normalizes parameters (e.g. codecs=opus) and maps container formats.
    Returns normalized mime type or raises AudioValidationError.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise AudioValidationError("Audio file is empty. Please provide recorded audio data.", status_code=400)

    if len(audio_bytes) < 32:
        raise AudioValidationError(
            f"Audio payload is too short ({len(audio_bytes)} bytes) to contain valid audio data or headers.",
            status_code=400
        )

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AudioValidationError(
            f"Audio file exceeds maximum allowed size of 10 MB (provided: {len(audio_bytes) / (1024 * 1024):.2f} MB).",
            status_code=413
        )

    raw_mime = (declared_mime or "").lower().split(";")[0].strip()

    # Normalize aliases / containers to standard MIME types
    if raw_mime in ("audio/webm", "video/webm", "application/webm"):
        norm_mime = "audio/webm"
    elif raw_mime in ("audio/ogg", "application/ogg", "video/ogg", "audio/opus"):
        norm_mime = "audio/ogg"
    elif raw_mime in ("audio/wav", "audio/x-wav", "audio/wave"):
        norm_mime = "audio/wav"
    elif raw_mime in ("audio/mpeg", "audio/mp3"):
        norm_mime = "audio/mpeg"
    elif raw_mime in ("audio/mp4", "audio/m4a", "audio/x-m4a", "video/mp4", "audio/aac"):
        norm_mime = "audio/mp4"
    elif raw_mime in ("application/octet-stream", "binary/octet-stream", ""):
        norm_mime = "application/octet-stream"
    else:
        norm_mime = raw_mime

    if norm_mime not in ALLOWED_MIME_TYPES and norm_mime != "application/octet-stream":
        raise AudioValidationError(
            f"Unsupported audio format '{declared_mime}'. Allowed formats: webm, ogg, wav, mp3, m4a.",
            status_code=415
        )

    # Magic byte signature verification
    magic_ok = False
    prefix = audio_bytes[:32]

    if prefix.startswith(b"RIFF") and b"WAVE" in prefix[:12]:
        magic_ok = True
        norm_mime = "audio/wav"
    elif prefix.startswith(b"OggS"):
        magic_ok = True
        norm_mime = "audio/ogg"
    elif prefix.startswith(b"\x1a\x45\xdf\xa3"):
        magic_ok = True
        norm_mime = "audio/webm"
    elif prefix.startswith(b"ID3") or prefix[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        magic_ok = True
        norm_mime = "audio/mpeg"
    elif b"ftyp" in prefix or prefix[4:8] == b"ftyp" or (len(prefix) >= 2 and prefix[0] == 0xFF and (prefix[1] & 0xF6) == 0xF0):
        magic_ok = True
        norm_mime = "audio/mp4"

    if not magic_ok:
        raise AudioValidationError(
            "Audio file content does not match recognized audio signatures (RIFF, OGG, WebM, MP3, MP4/M4A).",
            status_code=415
        )

    if norm_mime not in ALLOWED_MIME_TYPES:
        raise AudioValidationError(
            f"Unsupported audio format '{declared_mime}'. Allowed formats: webm, ogg, wav, mp3, m4a.",
            status_code=415
        )

    # Decoded audio duration check for WAV audio (exact PCM header inspection)
    if norm_mime == "audio/wav":
        try:
            import io
            import wave
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                if framerate > 0:
                    decoded_dur = float(nframes) / float(framerate)
                    if decoded_dur > 60.0:
                        raise AudioValidationError(
                            f"Decoded audio length ({decoded_dur:.1f} s) exceeds maximum limit of 60 seconds.",
                            status_code=400
                        )
        except AudioValidationError:
            raise
        except Exception:
            # If wave header is partial/unsupported compression, pass to downstream handler
            pass

    return norm_mime


class VoiceService:
    """
    Voice Transcription Service using Google Gemini Audio Input.
    Transcribes English, Hindi (Devanagari), and Hinglish (Roman script) speech audio.
    Strictly enforces zero audio persistence (audio is never stored to disk or database).
    """

    @classmethod
    def transcribe_audio(cls, audio_bytes: bytes, content_type: str) -> VoiceTranscribeResponse:
        start_time = time.time()
        size_bytes = len(audio_bytes)

        # 1. Content validation
        validated_mime = validate_audio_content(audio_bytes, content_type)

        # 2. Check Gemini API Key
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            err_msg = (
                "Gemini API key is not configured. Voice transcription requires a valid GEMINI_API_KEY. "
                "Please configure GEMINI_API_KEY in your environment or .env file."
            )
            logger.warning(err_msg)
            # Log failure metadata only
            AIAuditService.log(
                question=f"[voice_transcribe: key_missing, size: {size_bytes}B]",
                intent="voice_transcribe_unavailable",
                generated_sql=None,
                latency_ms=(time.time() - start_time) * 1000.0,
                success=False,
                error="GEMINI_API_KEY is not configured"
            )
            raise GeminiKeyMissingError(err_msg)

        if not GENAI_AVAILABLE:
            raise VoiceTranscriptionError("google-genai SDK is not available in backend environment.")

        # 3. Transcribe via Gemini Audio Input
        try:
            client = genai.Client(api_key=api_key)

            prompt = (
                "You are an expert multilingual audio transcriber for the InsightForge business intelligence platform.\n"
                "Transcribe the provided speech audio exactly as spoken.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Return strictly a JSON object with keys: \"text\", \"detected_language\", \"confidence\".\n"
                "2. \"detected_language\" MUST be exactly one of:\n"
                "   - \"hi\" (for pure Hindi spoken speech transcribed in Devanagari script)\n"
                "   - \"hinglish\" (for mixed Hindi-English speech transcribed in Roman/Latin script)\n"
                "   - \"en\" (for standard English speech)\n"
                "3. For Hindi speech, transcribe in standard Devanagari script (e.g. \"सबसे ज्यादा बिक्री किस श्रेणी में हुई?\").\n"
                "4. For Hinglish speech, KEEP THE TRANSCRIPT IN ROMAN SCRIPT (e.g. \"sabse zyada bikri kis category mein hui?\").\n"
                "5. For English speech, transcribe in standard English.\n"
                "6. \"confidence\" must be a float between 0.0 and 1.0 reflecting transcription certainty.\n"
                "7. Transcribe verbatim. Do NOT summarize, do NOT reply to the question, and do NOT add explanatory text.\n\n"
                "Respond ONLY with a valid JSON object."
            )

            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=validated_mime)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )

            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[audio_part, prompt],
                config=config
            )

            raw_text = response.text.strip()
            # Clean possible markdown wrapping
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned)

            text_out = str(parsed.get("text", "")).strip()
            lang_out = str(parsed.get("detected_language", "en")).lower()
            conf_out = float(parsed.get("confidence", 0.90))
            conf_out = max(0.0, min(1.0, conf_out))

            if lang_out not in ("hi", "en", "hinglish"):
                # Heuristic fallback if unrecognized code
                if re.search(r'[\u0900-\u097F]', text_out):
                    lang_out = "hi"
                else:
                    lang_out = "en"

            # Rough estimate of duration based on typical uncompressed/compressed bitrate
            # e.g. webm/ogg ~ 64kbps = 8 KB/s
            est_duration = round(size_bytes / 16000.0, 1)

            latency_ms = (time.time() - start_time) * 1000.0

            # 4. Audit Log (Log ONLY metadata: duration, language, size, success. NEVER store audio)
            AIAuditService.log(
                question=f"[voice_transcribe: {lang_out}, est_dur: {est_duration}s, size: {size_bytes}B]",
                intent=f"voice_transcribe_{lang_out}",
                generated_sql=None,
                latency_ms=latency_ms,
                success=True,
                error=None
            )

            return VoiceTranscribeResponse(
                text=text_out,
                detected_language=lang_out,
                confidence=conf_out,
                duration_est_s=est_duration
            )

        except json.JSONDecodeError as e:
            latency_ms = (time.time() - start_time) * 1000.0
            logger.error(f"Failed to parse Gemini transcription JSON response: {e}")
            AIAuditService.log(
                question=f"[voice_transcribe: parse_error, size: {size_bytes}B]",
                intent="voice_transcribe_error",
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
            raise VoiceTranscriptionError(f"Transcription formatting failed: {e}")

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            err_str = str(e)
            logger.error(f"Gemini voice transcription failed: {err_str}", exc_info=True)
            AIAuditService.log(
                question=f"[voice_transcribe: failed, size: {size_bytes}B]",
                intent="voice_transcribe_error",
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=err_str
            )
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                raise VoiceQuotaExceededError(
                    "Voice transcription quota exceeded or temporarily unavailable. Please type your question or use browser speech fallback."
                )
            raise VoiceTranscriptionError(
                "Voice transcription service error. Please type your question or use browser speech fallback."
            )
