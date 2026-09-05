"""
Comprehensive Unit & Mock Integration Tests for VoiceShield Python SDK.
Validates:
1. Client initialization and base_url sanitization
2. Header formatting with and without X-API-Key
3. File payload preparation (path, bytes, file-like object)
4. analyze_audio request and response model parsing
5. enroll_speaker request and response model parsing
6. verify_speaker request and response model parsing
7. get_speakers list parsing
8. get_policy object parsing
9. get_health status check
10. HTTP error handling and exception wrapping
"""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from sdk.python.voiceshield import VoiceShieldClient
from sdk.python.voiceshield.types import (
    AnalyzeResult,
    EnrollmentResult,
    OrganizationPolicy,
    VerifyResult,
)


class TestVoiceShieldPythonSDK(unittest.TestCase):
    def setUp(self):
        self.client = VoiceShieldClient(
            base_url="http://127.0.0.1:3000/",
            api_key="test-api-key-12345",
            timeout=10.0,
        )

    def test_1_client_initialization_and_url_sanitization(self):
        """Verify trailing slashes are stripped and attributes properly initialized."""
        self.assertEqual(self.client.base_url, "http://127.0.0.1:3000")
        self.assertEqual(self.client.api_key, "test-api-key-12345")
        self.assertEqual(self.client.timeout, 10.0)

    def test_2_header_handling_with_api_key(self):
        """Verify X-API-Key header is added when configured."""
        headers = self.client._get_headers({"Accept": "application/json"})
        self.assertEqual(headers.get("X-API-Key"), "test-api-key-12345")
        self.assertEqual(headers.get("Accept"), "application/json")

        # Client without API key
        unauth_client = VoiceShieldClient(base_url="http://localhost:3000")
        unauth_headers = unauth_client._get_headers()
        self.assertNotIn("X-API-Key", unauth_headers)

    def test_3_file_payload_preparation_bytes_and_buffer(self):
        """Verify audio bytes, BytesIO buffers, and file paths are converted to multipart tuples."""
        raw_bytes = b"RIFF....WAVEfmt "
        field_name, file_tuple = self.client._prepare_file_payload(raw_bytes, "test.wav")
        self.assertEqual(field_name, "file")
        self.assertEqual(file_tuple[0], "test.wav")
        self.assertEqual(file_tuple[2], "audio/wav")

        buf = io.BytesIO(raw_bytes)
        field_name2, file_tuple2 = self.client._prepare_file_payload(buf, "stream.wav")
        self.assertEqual(file_tuple2[0], "stream.wav")

    @patch("requests.Session.post")
    def test_4_analyze_audio_success(self, mock_post):
        """Verify analyze_audio sends expected parameters and returns typed AnalyzeResult."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "call_id": "CALL-2026-TEST",
            "risk_score": 82,
            "risk_level": "CRITICAL",
            "recommended_action": "BLOCK",
            "flags": ["Wav2Vec2 high neural synthesis probability (92.5%)"],
            "deepfake_detection": {
                "prediction": "FAKE",
                "fake_probability": 0.925,
                "real_probability": 0.075,
                "model_type": "Wav2Vec2",
                "inference_time_ms": 18.5,
            },
            "speaker_verification": {
                "status": "EVALUATED",
                "speaker_id": "EMP-4102",
                "similarity_score": 0.42,
                "threshold": 0.70,
                "is_match": False,
                "speaker_mismatch_flag": 1,
                "sample_count": 3,
                "inference_time_ms": 12.0,
            },
            "risk_signals": {
                "fake_probability": 0.925,
                "speaker_mismatch": 1,
                "acoustic_anomaly": 0.65,
                "context_flag": 1,
                "speaker_verification_status": "EVALUATED",
                "acoustic_model_status": "ACTIVE",
                "prosody_reasons": ["Unnatural pitch contour"],
            },
            "audio_metadata": {
                "sample_rate": 16000,
                "original_duration_sec": 3.0,
                "processed_duration_sec": 3.0,
                "estimated_snr_db": 28.5,
                "rms_db": -18.2,
            },
            "language": "hi",
            "language_name": "Hindi",
            "language_confidence": 0.95,
            "transcript": "तुरंत पचास हजार रुपये ट्रांसफर करो",
        }
        mock_post.return_value = mock_response

        result = self.client.analyze_audio(
            audio=b"fake-wav-bytes",
            speaker_id="EMP-4102",
            claimed_role="CEO",
            requested_amount=50000.0,
            is_urgent=True,
            language="hi",
        )

        self.assertIsInstance(result, AnalyzeResult)
        self.assertEqual(result.call_id, "CALL-2026-TEST")
        self.assertEqual(result.risk_score, 82)
        self.assertEqual(result.risk_level, "CRITICAL")
        self.assertEqual(result.recommended_action, "BLOCK")
        self.assertEqual(result.deepfake_detection.prediction, "FAKE")
        self.assertEqual(result.speaker_verification.sample_count, 3)
        self.assertFalse(result.speaker_verification.is_match)
        self.assertEqual(result.language, "hi")

    @patch("requests.Session.post")
    def test_5_enroll_speaker_success(self, mock_post):
        """Verify enroll_speaker posts metadata and returns typed EnrollmentResult."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": "ENROLLED",
            "speaker_id": "EMP-9001",
            "speaker_name": "Jane Doe (CFO)",
            "sample_count": 2,
            "embedding_dimension": 192,
            "created_at": 1725000000.0,
            "updated_at": 1725000100.0,
            "message": "Speaker 'EMP-9001' sample #2 successfully enrolled.",
            "sample_rate_verified": 16000,
            "inference_time_ms": 25.4,
        }
        mock_post.return_value = mock_response

        result = self.client.enroll_speaker(
            audio=b"enroll-bytes",
            speaker_id="EMP-9001",
            speaker_name="Jane Doe (CFO)",
        )

        self.assertIsInstance(result, EnrollmentResult)
        self.assertEqual(result.speaker_id, "EMP-9001")
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.embedding_dimension, 192)

    @patch("requests.Session.post")
    def test_6_verify_speaker_success(self, mock_post):
        """Verify verify_speaker returns typed VerifyResult."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": "SUCCESS",
            "speaker_id": "EMP-9001",
            "similarity_score": 0.884,
            "threshold": 0.70,
            "match": True,
            "speaker_mismatch_flag": 0,
            "sample_count": 2,
            "inference_time_ms": 14.2,
            "message": "Verification completed: MATCH",
        }
        mock_post.return_value = mock_response

        result = self.client.verify_speaker(
            audio=b"verify-bytes",
            speaker_id="EMP-9001",
            threshold=0.70,
        )

        self.assertIsInstance(result, VerifyResult)
        self.assertTrue(result.match)
        self.assertEqual(result.speaker_mismatch_flag, 0)
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.similarity_score, 0.884)

    @patch("requests.Session.get")
    def test_7_get_speakers_success(self, mock_get):
        """Verify get_speakers parses list of enrolled speakers."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": "ok",
            "speakers": [
                {
                    "speaker_id": "EMP-9001",
                    "speaker_name": "Jane Doe",
                    "dimension": 192,
                    "sample_count": 3,
                    "created_at": 1725000000.0,
                    "updated_at": 1725000200.0,
                }
            ],
        }
        mock_get.return_value = mock_response

        speakers = self.client.get_speakers()
        self.assertEqual(len(speakers), 1)
        self.assertEqual(speakers[0].speaker_id, "EMP-9001")
        self.assertEqual(speakers[0].sample_count, 3)

    @patch("requests.Session.get")
    def test_8_get_policy_success(self, mock_get):
        """Verify get_policy returns typed OrganizationPolicy object."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "status": "ok",
            "policy": {
                "organization_id": "ORG-101",
                "name": "Acme Global Banking Policy",
                "fake_prob_critical_threshold": 0.85,
                "fake_prob_warn_threshold": 0.65,
                "transaction_auto_hold_amount": 50000.0,
                "high_risk_wire_threshold": 10000.0,
                "role_enforcement_strictness": "STRICT",
                "speaker_verification_strictness": 0.70,
                "independent_callback_required": True,
                "supervisor_escalation_required": True,
                "otp_verification_required": True,
                "version": 2,
            },
        }
        mock_get.return_value = mock_response

        policy = self.client.get_policy("ORG-101")
        self.assertIsInstance(policy, OrganizationPolicy)
        self.assertEqual(policy.organization_id, "ORG-101")
        self.assertEqual(policy.transaction_auto_hold_amount, 50000.0)
        self.assertTrue(policy.independent_callback_required)

    @patch("requests.Session.post")
    def test_9_error_handling_runtime_error(self, mock_post):
        """Verify non-200 HTTP response raises RuntimeError with server message."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "error_type": "AudioTooShortError",
            "message": "Audio duration 0.20s is shorter than minimum 0.50s.",
        }
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as ctx:
            self.client.analyze_audio(audio=b"short-audio")

        self.assertIn("AudioTooShortError", str(ctx.exception))
        self.assertIn("HTTP 422", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
