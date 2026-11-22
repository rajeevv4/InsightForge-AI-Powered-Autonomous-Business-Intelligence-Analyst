import os
import io
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import settings
from backend.app.services.ai_service import AIService, detect_language
from backend.app.services.grounding import (
    extract_numbers_from_text,
    normalize_multilingual_numbers,
    verify_numeric_grounding
)
from backend.app.services.audit_service import _memory_audit_log


class TestVoiceAndMultilingual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["USE_FIXTURES"] = "1"
        cls.client = TestClient(app)

    def setUp(self):
        from backend.app.limiter import limiter
        limiter.reset()

    # ------------------------------------------------------------------------
    # 1. Voice Transcribe Endpoint Tests
    # ------------------------------------------------------------------------
    def test_transcribe_valid_audio_gemini_mocked(self):
        """Valid audio with mocked Gemini returns 200 and transcript JSON."""
        # Simulated WebM header
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 500

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "sabse zyada bikri kis category mein hui?", "detected_language": "hinglish", "confidence": 0.96}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("speech.webm", io.BytesIO(dummy_audio), "audio/webm")}
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "sabse zyada bikri kis category mein hui?")
        self.assertEqual(data["detected_language"], "hinglish")
        self.assertGreaterEqual(data["confidence"], 0.90)

    def test_transcribe_webm_with_codecs_parameter_normalized(self):
        """Browser MediaRecorder audio/webm;codecs=opus is accepted and normalized."""
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 500

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "what is total delivered revenue?", "detected_language": "en", "confidence": 0.98}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("voice_query.webm", io.BytesIO(dummy_audio), "audio/webm;codecs=opus")}
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "what is total delivered revenue?")
        self.assertEqual(data["detected_language"], "en")

    def test_transcribe_gemini_quota_exceeded_returns_clean_503(self):
        """Gemini 429 quota error returns HTTP 503 with human message, no raw trace."""
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 500

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded on Free Tier")

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("speech.webm", io.BytesIO(dummy_audio), "audio/webm")}
                )

        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertIn("quota exceeded", detail.lower())
        self.assertNotIn("RESOURCE_EXHAUSTED:", detail)
        self.assertNotIn("Traceback", detail)

    def test_transcribe_real_sample_wav_file(self):
        """Real audio file from data/samples/voice/ passes validation and transcribes."""
        sample_path = "data/samples/voice/sample_question.wav"
        if not os.path.exists(sample_path):
            self.skipTest(f"{sample_path} not found")

        with open(sample_path, "rb") as f:
            audio_bytes = f.read()

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "sabse zyada bikri kis category mein hui?", "detected_language": "hinglish", "confidence": 0.95}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("sample_question.wav", io.BytesIO(audio_bytes), "audio/wav")}
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "sabse zyada bikri kis category mein hui?")

    def test_transcribe_oversize_audio_rejected(self):
        """Audio exceeding 10 MB limit returns HTTP 413 Payload Too Large."""
        oversize_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * (10 * 1024 * 1024 + 100)

        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("large.webm", io.BytesIO(oversize_audio), "audio/webm")}
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds maximum allowed size", response.json()["detail"])

    def test_transcribe_wrong_content_type_rejected(self):
        """Non-audio content type returns HTTP 415 Unsupported Media Type."""
        dummy_pdf = b"%PDF-1.4\n" + b"\x00" * 200

        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("document.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("Unsupported audio format", response.json()["detail"])

    def test_transcribe_empty_audio_rejected(self):
        """Empty audio file returns HTTP 400 Bad Request."""
        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("empty.wav", io.BytesIO(b""), "audio/wav")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Audio file is empty", response.json()["detail"])

    def test_transcribe_503_without_gemini_key(self):
        """Returns HTTP 503 when GEMINI_API_KEY is not configured."""
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 200

        with patch("backend.app.config.settings.GEMINI_API_KEY", ""):
            response = self.client.post(
                "/api/voice/transcribe",
                files={"file": ("speech.webm", io.BytesIO(dummy_audio), "audio/webm")}
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Gemini API key is not configured", response.json()["detail"])

    def test_transcribe_no_audio_persisted_to_disk_or_db(self):
        """Verify no audio files are saved to disk and audit log stores only metadata."""
        initial_files = set(os.listdir("."))
        dummy_audio = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 100

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "कुल राजस्व कितना है?", "detected_language": "hi", "confidence": 0.98}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                res = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("sample.wav", io.BytesIO(dummy_audio), "audio/wav")}
                )

        self.assertEqual(res.status_code, 200)

        # 1. No new files created in root workspace
        current_files = set(os.listdir("."))
        self.assertEqual(initial_files, current_files)

        # 2. Check audit log in memory: question contains only metadata tag
        latest_audit = _memory_audit_log[-1] if _memory_audit_log else None
        self.assertIsNotNone(latest_audit)
        self.assertTrue(latest_audit["question"].startswith("[voice_transcribe:"))
        self.assertIn("hi", latest_audit["question"])
        # Verify raw audio payload is NOT in audit log
        self.assertNotIn("RIFF", latest_audit["question"])

    # ------------------------------------------------------------------------
    # 2. Multilingual Understanding & Heuristic Routing
    # ------------------------------------------------------------------------
    def test_language_detection(self):
        """Test language detector for Hindi, Hinglish, and English."""
        self.assertEqual(detect_language("सबसे ज्यादा बिक्री किस श्रेणी में हुई?"), "hi")
        self.assertEqual(detect_language("sabse zyada bikri kis category mein hui?"), "hinglish")
        self.assertEqual(detect_language("Which category generated the highest revenue?"), "en")

    def test_hindi_devanagari_heuristic_routing(self):
        """Hindi questions in Devanagari route to expected business intents."""
        cases = [
            ("सबसे ज्यादा बिक्री किस श्रेणी में हुई?", "category_analysis"),
            ("ब्राजील के किस राज्य से सबसे ज्यादा राजस्व मिला?", "state_analysis"),
            ("सर्वश्रेष्ठ विक्रेता कौन सा है?", "seller_analysis"),
            ("समय पर डिलीवरी का प्रतिशत कितना है?", "delivery_analysis"),
            ("क्रेडिट कार्ड से कितना भुगतान हुआ?", "payment_analysis"),
            ("मासिक बिक्री का रुझान क्या है?", "revenue_trend"),
            ("कुल सकल राजस्व कितना है?", "kpi_summary"),
            ("डेटाबेस में डेटा गुणवत्ता की स्थिति क्या है?", "data_quality"),
            ("क्या बिक्री में कोई विसंगति या असामान्य उछाल है?", "anomaly_detection"),
            ("कल का मौसम कैसा रहेगा?", "unknown"),
        ]
        for q, expected in cases:
            res = AIService.classify_intent_heuristic(q)
            self.assertEqual(res["intent"], expected, f"Failed on Hindi question: '{q}'")

    def test_hinglish_heuristic_routing(self):
        """Hinglish questions in Roman script route to expected business intents."""
        cases = [
            ("sabse zyada bikri kis category mein hui?", "category_analysis"),
            ("kaunse state se sabse jyada orders aaye?", "state_analysis"),
            ("hamara delivery delay percentage kitna hai?", "delivery_analysis"),
            ("sabse popular payment method kaunsa hai?", "payment_analysis"),
            ("overall gross revenue aur aov kitna hai?", "kpi_summary"),
            ("kya koi black friday sales spike ya anomaly detect hui?", "anomaly_detection"),
        ]
        for q, expected in cases:
            res = AIService.classify_intent_heuristic(q)
            self.assertEqual(res["intent"], expected, f"Failed on Hinglish question: '{q}'")

    def test_routing_false_positives(self):
        """Ensure unrelated words with partial substrings do not trigger false positive intents."""
        unrelated = [
            "What is the capital of France?",
            "How do I cook pasta at home?",
            "Can you tell me a story about space?",
        ]
        for q in unrelated:
            res = AIService.classify_intent_heuristic(q)
            self.assertEqual(res["intent"], "unknown", f"False positive triggered for: '{q}'")

    # ------------------------------------------------------------------------
    # 3. Grounding Verifier & Digit Normalization
    # ------------------------------------------------------------------------
    def test_devanagari_digit_normalization(self):
        """Devanagari numerals are normalized to ASCII digits and extracted."""
        # 12,33,131.72 in Devanagari
        hindi_text = "स्वास्थ्य और सौंदर्य श्रेणी में कुल बिक्री R$ १२,३३,१३१.७२ रही।"
        nums = extract_numbers_from_text(hindi_text)
        self.assertIn(1233131.72, nums)

    def test_lakh_and_crore_normalization(self):
        """Test lakh and crore expansion in Hindi and Hinglish text."""
        self.assertIn(350000.0, extract_numbers_from_text("Total orders were 3.5 lakh this quarter."))
        self.assertIn(15400000.0, extract_numbers_from_text("Gross revenue reached 1.54 crore."))
        self.assertIn(50000.0, extract_numbers_from_text("50 hazaar orders fulfilled successfully."))
        self.assertIn(12000000.0, extract_numbers_from_text("कुल राजस्व १.२ करोड़ रुपये रहा।"))

    def test_hindi_answer_grounding_verified(self):
        """Faithful Hindi answer with matching numbers passes numeric grounding."""
        evidence_data = {
            "total_gross_revenue": 15419773.75,
            "total_delivered_orders": 96478,
            "aov": 159.83,
            "csat": 4.16
        }
        faithful_hindi_answer = (
            "सत्यापित PostgreSQL रिकॉर्ड्स से हमारा कार्यकारी सारांश:\n"
            "• कुल सकल राजस्व: R$ 15,419,773.75\n"
            "• डिलीवर किए गए ऑर्डर: 96,478\n"
            "• औसत ऑर्डर मूल्य (AOV): R$ 159.83\n"
            "• ग्राहक संतुष्टि (CSAT): 4.16"
        )
        is_grounded = verify_numeric_grounding(faithful_hindi_answer, evidence_data)
        self.assertTrue(is_grounded)

    def test_hindi_answer_fabricated_number_rejected(self):
        """Fabricated number in Hindi answer fails numeric grounding."""
        evidence_data = {
            "total_revenue": 1233131.72,
            "units_sold": 9670
        }
        # Injects a hallucinated revenue of R$ 9,999,999.00
        hallucinated_hindi_answer = (
            "PostgreSQL एनालिटिक्स के अनुसार, सबसे अधिक बिक्री R$ 9,999,999.00 रही।"
        )
        is_grounded = verify_numeric_grounding(hallucinated_hindi_answer, evidence_data)
        self.assertFalse(is_grounded)

    # ------------------------------------------------------------------------
    # 4. Level 4.1 Edge Tests (Noise, Silence, Corrupted, Short Audio, Decoded Duration)
    # ------------------------------------------------------------------------
    def test_transcribe_very_short_audio_rejected(self):
        """Audio under 32 bytes is rejected as too short for audio headers."""
        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("tiny.wav", io.BytesIO(b"RIFFtiny"), "audio/wav")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("too short", response.json()["detail"])

    def test_transcribe_corrupted_file_with_valid_extension(self):
        """Corrupted audio payload with valid extension is rejected by magic byte check."""
        corrupted_payload = b"THIS_IS_DEFINITELY_NOT_A_VALID_AUDIO_FILE_DATA_CORRUPT" * 5
        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("recording.wav", io.BytesIO(corrupted_payload), "audio/wav")}
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("does not match recognized audio signatures", response.json()["detail"])

    def test_transcribe_silence_graceful(self):
        """Silence audio yielding empty transcript from Gemini returns 200 without crashing."""
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "", "detected_language": "en", "confidence": 0.0}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("silence.webm", io.BytesIO(dummy_audio), "audio/webm")}
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "")
        self.assertEqual(data["confidence"], 0.0)

    def test_transcribe_non_speech_noise(self):
        """Non-speech noise yielding low confidence transcript is handled gracefully."""
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
        mock_gemini_resp = MagicMock()
        mock_gemini_resp.text = '{"text": "[noise]", "detected_language": "en", "confidence": 0.20}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp

        with patch("backend.app.config.settings.GEMINI_API_KEY", "dummy_key"):
            with patch("google.genai.Client", return_value=mock_client):
                response = self.client.post(
                    "/api/voice/transcribe",
                    files={"file": ("noise.webm", io.BytesIO(dummy_audio), "audio/webm")}
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "[noise]")
        self.assertEqual(data["confidence"], 0.20)

    def test_hindi_question_with_mixed_numbers_and_years(self):
        """Hindi questions with numbers/years route properly and pass metadata grounding."""
        q = "2017 में कुल कितने ऑर्डर सफलतापूर्वक डिलीवर हुए?"
        res = AIService.classify_intent_heuristic(q)
        self.assertEqual(res["intent"], "kpi_summary")

        evidence = {
            "total_delivered_orders": 96478,
            "total_gross_revenue": 15419773.75
        }
        answer = "2017 और पूरे डेटासेट में कुल 96,478 ऑर्डर सफलतापूर्वक डिलीवर किए गए।"
        # 2017 is common metadata number, 96,478 is grounded in evidence
        self.assertTrue(verify_numeric_grounding(answer, evidence))

    def test_hindi_question_expecting_state_name(self):
        """Hindi questions expecting state name route to state_analysis and verify SP revenue."""
        q = "साओ पाउलो राज्य से कुल कितना राजस्व प्राप्त हुआ?"
        res = AIService.classify_intent_heuristic(q)
        self.assertEqual(res["intent"], "state_analysis")

        evidence = {
            "state": "SP",
            "total_gross_revenue": 5769703.15,
            "revenue_share_percent": 38.33
        }
        answer = "साओ पाउलो (SP) राज्य से कुल राजस्व R$ 5,769,703.15 प्राप्त हुआ जो कुल बिक्री का 38.33% है।"
        self.assertTrue(verify_numeric_grounding(answer, evidence))

    def test_decoded_wav_duration_over_60s_rejected(self):
        """Decoded WAV audio longer than 60s is rejected with HTTP 400."""
        import wave
        buf = io.BytesIO()
        # 16000 Hz, 1 channel, 2 bytes per sample, 61 seconds = 61 * 16000 frames
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * (16000 * 61))

        long_wav_bytes = buf.getvalue()
        response = self.client.post(
            "/api/voice/transcribe",
            files={"file": ("long.wav", io.BytesIO(long_wav_bytes), "audio/wav")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds maximum limit of 60 seconds", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
