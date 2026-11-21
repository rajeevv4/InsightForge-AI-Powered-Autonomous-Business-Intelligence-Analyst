#!/usr/bin/env python3
"""
Live Voice Transcription Test Script
====================================
Sends real audio recordings from `data/samples/voice/` to the Gemini
transcription pipeline and prints transcription text, detected language,
confidence score, and round-trip latency.

Zero-Persistence Guarantee: Audio bytes are processed in-memory only and never
written to disk or database.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings
from backend.app.services.voice_service import VoiceService


def run_live_transcription_test() -> int:
    # 1. Verify Gemini API key configuration
    gemini_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not gemini_key or gemini_key.strip().lower() in ("your_gemini_api_key_here", "dummy", "none", ""):
        print("=" * 70)
        print("ERROR: GEMINI_API_KEY is not configured.")
        print("Live voice transcription requires a valid Google Gemini API key.")
        print("Please configure GEMINI_API_KEY in your .env file or environment.")
        print("=" * 70)
        return 1

    # 2. Check for audio sample directory and files
    samples_dir = PROJECT_ROOT / "data" / "samples" / "voice"
    samples_dir.mkdir(parents=True, exist_ok=True)

    supported_exts = {".webm", ".ogg", ".wav", ".mp3", ".m4a"}
    audio_files = [
        f for f in sorted(samples_dir.iterdir())
        if f.is_file() and f.suffix.lower() in supported_exts
    ]

    if not audio_files:
        print("=" * 70)
        print(f"NO AUDIO FILES FOUND in {samples_dir.relative_to(PROJECT_ROOT)}")
        print("Please place test audio files (e.g. english.mp3, hindi.wav, hinglish.webm)")
        print("into data/samples/voice/ to run live transcription tests.")
        print("Supported formats: WebM, OGG, WAV, MP3, M4A (max 10 MB, <= 60 seconds).")
        print("=" * 70)
        return 0

    print("=" * 70)
    print("      INSIGHTFORGE LIVE GEMINI VOICE TRANSCRIPTION TEST      ")
    print("=" * 70)
    print(f"Found {len(audio_files)} audio file(s) in {samples_dir.relative_to(PROJECT_ROOT)}:\n")

    success_count = 0
    total_latency = 0.0

    for idx, audio_path in enumerate(audio_files, 1):
        filename = audio_path.name
        file_size_kb = audio_path.stat().st_size / 1024.0
        print(f"[{idx}/{len(audio_files)}] Processing '{filename}' ({file_size_kb:.1f} KB)...")

        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            t0 = time.perf_counter()
            result = VoiceService.transcribe_audio(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=None
            )
            elapsed = time.perf_counter() - t0
            total_latency += elapsed
            success_count += 1

            print(f"  • Latency:           {elapsed:.2f} s")
            print(f"  • Detected Language: {result.detected_language}")
            print(f"  • Confidence:        {result.confidence:.2f}")
            print(f"  • Est Duration:      {result.duration_est_s:.1f} s")
            print(f"  • Transcript:        \"{result.text}\"\n")

        except Exception as e:
            print(f"  FAILED: {str(e)}\n")

    print("=" * 70)
    print(f"Summary: {success_count}/{len(audio_files)} succeeded")
    if success_count > 0:
        print(f"Average Round-Trip Latency: {total_latency / success_count:.2f} s")
    print("=" * 70)
    return 0 if success_count == len(audio_files) else 1


if __name__ == "__main__":
    sys.exit(run_live_transcription_test())
