"""
Unit and Integration Tests for VoiceShield Local Multilingual ASR & Language Identification.
Validates:
1. Whisper-Tiny local model initialization and singleton reuse
2. Silent and short audio handling
3. Real English speech detection and transcription
4. Multilingual fraud keyword extraction (Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, English)
5. ASR failure isolation
6. PipelineWorker integration and streaming WebSocket response contract
"""

import math
import os
import struct
import base64
import unittest
import numpy as np

from app.audio.preprocessing import PreprocessedAudio
from app.models.asr import SpeechRecognizer, ASRResult, MULTILINGUAL_FRAUD_KEYWORDS
from scripts.run_pipeline import PipelineWorker


class TestSpeechRecognizerASR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = SpeechRecognizer.get_instance()
        cls.worker = PipelineWorker()

    def test_1_asr_initialization_and_timing(self):
        """Test Whisper-Tiny initializes and records load metrics."""
        self.assertTrue(self.recognizer.is_loaded)
        self.assertIsNotNone(self.recognizer.model)
        self.assertIsNotNone(self.recognizer.processor)
        self.assertGreaterEqual(self.recognizer.load_time_sec, 0.0)

    def test_2_silent_audio_returns_empty_transcript(self):
        """Test pure silence audio returns safe empty transcript and unknown language."""
        silent_samples = [0.0] * 32000  # 2.0s silence @ 16kHz
        res = self.recognizer.transcribe(silent_samples, sample_rate=16000)
        self.assertIsInstance(res, ASRResult)
        self.assertFalse(res.is_speech)
        self.assertEqual(res.transcript, "")
        self.assertEqual(res.language, "unknown")

    def test_3_short_audio_handled_gracefully(self):
        """Test sub-minimum audio (<0.4s) does not crash and returns safe structure."""
        short_samples = [0.1 * math.sin(2 * math.pi * 300 * i / 16000) for i in range(2000)]  # 0.125s
        res = self.recognizer.transcribe(short_samples, sample_rate=16000)
        self.assertIsInstance(res, ASRResult)
        self.assertFalse(res.is_speech)
        self.assertEqual(res.transcript, "")
        self.assertEqual(res.language, "unknown")

    def test_4_english_speech_detection_and_transcription(self):
        """Test real speech audio produces detected language and non-empty transcript."""
        sample_path = "data/samples/fake_01.wav"
        if os.path.exists(sample_path):
            prep = self.worker.preprocessor.process(sample_path)
            res = self.recognizer.transcribe(prep.waveform, sample_rate=16000)
            self.assertIsInstance(res, ASRResult)
            self.assertTrue(res.is_speech)
            self.assertIn(res.language, ["en", "unknown"])
            self.assertTrue(len(res.transcript) > 0)
            self.assertGreater(res.inference_time_ms, 0.0)

    def test_5_fraud_keyword_extraction_english(self):
        """Test extracting OTP and wire transfer fraud keywords from English text."""
        text = "Please provide the OTP and security code to authorize the wire transfer immediately."
        keywords, flags = self.recognizer.extract_fraud_keywords(text)
        self.assertIn("otp", [k.lower() for k in keywords])
        self.assertIn("SPEECH_OTP_DEMAND", flags)
        self.assertIn("SPEECH_URGENT_TRANSFER", flags)

    def test_6_fraud_keyword_extraction_indian_languages(self):
        """Test extracting fraud keywords across Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi."""
        test_cases = [
            ("तुरंत पैसे भेजो वरना खाता ब्लॉक हो जाएगा", "Hindi", ["SPEECH_URGENT_TRANSFER", "SPEECH_ACCOUNT_THREAT"]),
            ("మీ ఓటీపీ చెప్పండి లేకపోతే ఖాతా బ్లాక్ అవుతుంది", "Telugu", ["SPEECH_OTP_DEMAND", "SPEECH_ACCOUNT_THREAT"]),
            ("உடனடியாக பணத்தை மாற்றுங்கள்", "Tamil", ["SPEECH_URGENT_TRANSFER"]),
            ("ತಕ್ಷಣ ಹಣ ಕಳುಹಿಸಿ", "Kannada", ["SPEECH_URGENT_TRANSFER"]),
            ("ഉടൻ പണം അയക്കുക", "Malayalam", ["SPEECH_URGENT_TRANSFER"]),
            ("টাকা পাঠান অবিলম্বে", "Bengali", ["SPEECH_URGENT_TRANSFER"]),
            ("तातडीने पैसे पाठवा", "Marathi", ["SPEECH_URGENT_TRANSFER"]),
        ]

        for text, lang_name, expected_flags in test_cases:
            keywords, flags = self.recognizer.extract_fraud_keywords(text)
            for expected_flag in expected_flags:
                self.assertIn(
                    expected_flag,
                    flags,
                    f"Expected flag '{expected_flag}' for {lang_name} phrase: '{text}'"
                )

    def test_7_asr_failure_isolation(self):
        """Test unsupported audio object does not throw unhandled exception."""
        res = self.recognizer.transcribe(None)
        self.assertIsInstance(res, ASRResult)
        self.assertFalse(res.is_speech)
        self.assertEqual(res.language, "unknown")

    def test_8_pipeline_worker_stream_chunk_includes_asr_fields(self):
        """Test PipelineWorker stream-chunk returns structured ASR fields in WebSocket contract."""
        # 1.5s PCM16 sine wave
        samples = [int(0.2 * 32767.0 * math.sin(2.0 * math.pi * 250.0 * i / 16000.0)) for i in range(24000)]
        raw_bytes = struct.pack(f"<{len(samples)}h", *samples)
        pcm_b64 = base64.b64encode(raw_bytes).decode("utf-8")

        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 1,
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})

        # Verify ASR contract keys
        self.assertIn("language", data)
        self.assertIn("language_name", data)
        self.assertIn("language_confidence", data)
        self.assertIn("transcript", data)
        self.assertIn("speech_context_flags", data)
        self.assertIn("asr_analysis", data)

    def test_9_transcript_to_fraud_risk_context_integration(self):
        """Test speech transcript keywords feed directly into ContextAnalyzer and RiskEngine."""
        sample_path = "data/samples/fake_01.wav"
        if os.path.exists(sample_path):
            req = {
                "command": "analyze",
                "args": {
                    "file": sample_path,
                    "context": {
                        "caller_id": "+91-9876543210",
                        "is_urgent": True,
                        "urgency_reason": "Executive emergency",
                    },
                },
            }
            res = self.worker.dispatch(req)
            self.assertEqual(res.get("status"), 200)
            data = res.get("data", {})
            self.assertIn("language", data)
            self.assertIn("transcript", data)
            self.assertIn("risk_score", data)
            self.assertGreaterEqual(data["risk_score"], 0)


if __name__ == "__main__":
    unittest.main()
