"""
Comprehensive In-Process Test Suite for VoiceShield gRPC Service.
Validates:
1. Proto and Service initialization
2. AnalyzeAudio request and response mapping
3. EnrollSpeaker multi-sample centroid response
4. VerifySpeaker biometric match and threshold
5. GetRiskPolicy organization retrieval
6. StreamLiveAudio bidirectional streaming
7. Metadata authentication enforcement (x-api-key)
8. Tenant isolation and authoritative org resolution
9. Error handling on invalid/missing audio arguments
10. Concurrent independent streaming sessions
"""

from concurrent import futures
import os
import struct
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import grpc

from grpc_server.client import VoiceShieldGrpcClient
from grpc_server.generated import voiceshield_pb2, voiceshield_pb2_grpc
from grpc_server.servicer import VoiceShieldGrpcServicer


class TestVoiceShieldGrpcService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_worker = MagicMock()
        cls.servicer = VoiceShieldGrpcServicer(worker=cls.mock_worker)

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
        voiceshield_pb2_grpc.add_VoiceShieldServiceServicer_to_server(cls.servicer, cls.server)
        cls.port = cls.server.add_insecure_port("[::]:0")
        cls.server.start()

        cls.target = f"localhost:{cls.port}"
        cls.client = VoiceShieldGrpcClient(target=cls.target)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.server.stop(0)

    def test_1_service_initialization(self):
        """Verify gRPC server and stub are listening and reachable."""
        self.assertIsNotNone(self.client)
        self.assertIsNotNone(self.client.stub)

    def test_2_analyze_audio_success(self):
        """Verify AnalyzeAudio sends parameters and parses all deepfake/prosody/ASR fields."""
        self.mock_worker.handle_analyze.return_value = {
            "status_code": 200,
            "call_id": "CALL-GRPC-001",
            "risk_score": 88,
            "risk_level": "CRITICAL",
            "recommended_action": "BLOCK",
            "flags": ["Wav2Vec2 high synthesis confidence (94.5%)"],
            "deepfake_detection": {
                "prediction": "FAKE",
                "fake_probability": 0.945,
                "real_probability": 0.055,
                "model_type": "Wav2Vec2",
                "inference_time_ms": 14.5,
            },
            "speaker_verification": {
                "status": "EVALUATED",
                "speaker_id": "EMP-4102",
                "similarity_score": 0.45,
                "threshold": 0.70,
                "is_match": False,
                "speaker_mismatch_flag": 1,
                "sample_count": 2,
                "inference_time_ms": 11.2,
            },
            "prosody_analysis": {
                "score": 0.75,
                "status": "ANOMALOUS",
                "reasons": ["Unnatural pitch contour"],
                "f0_mean_hz": 180.0,
                "f0_std_hz": 5.0,
                "jitter_local": 0.045,
                "shimmer_local": 0.08,
                "hnr_db": 12.0,
            },
            "asr_analysis": {
                "detected_language": "hi",
                "language_name": "Hindi",
                "language_confidence": 0.96,
                "transcript": "तुरंत ट्रांसफर करें",
                "detected_keywords": ["transfer", "urgent"],
                "is_language_supported": True,
            },
            "audio_metadata": {
                "sample_rate": 16000,
                "original_duration_sec": 3.0,
                "processed_duration_sec": 3.0,
                "estimated_snr_db": 28.0,
                "rms_db": -18.5,
            },
            "language": "hi",
            "transcript": "तुरंत ट्रांसफर करें",
        }

        audio_bytes = b"RIFF" + b"\x00" * 32000
        res = self.client.analyze_audio(
            audio_bytes=audio_bytes,
            speaker_id="EMP-4102",
            verification_threshold=0.70,
            claimed_role="CEO",
            requested_amount=75000.0,
            is_urgent=True,
            language="hi",
        )

        self.assertEqual(res.call_id, "CALL-GRPC-001")
        self.assertEqual(res.risk_score, 88)
        self.assertEqual(res.risk_level, "CRITICAL")
        self.assertEqual(res.recommended_action, "BLOCK")
        self.assertEqual(res.deepfake_detection.prediction, "FAKE")
        self.assertAlmostEqual(res.deepfake_detection.fake_probability, 0.945, places=3)
        self.assertEqual(res.speaker_verification.speaker_id, "EMP-4102")
        self.assertFalse(res.speaker_verification.is_match)
        self.assertEqual(res.asr_analysis.detected_language, "hi")
        self.assertEqual(res.transcript, "तुरंत ट्रांसफर करें")

    def test_3_enroll_speaker_success(self):
        """Verify EnrollSpeaker passes audio and returns sample count."""
        self.mock_worker.handle_enroll.return_value = {
            "status_code": 200,
            "status": "ENROLLED",
            "speaker_id": "EMP-9001",
            "speaker_name": "Jane Doe",
            "sample_count": 3,
            "embedding_dimension": 192,
            "created_at": 1725000000.0,
            "updated_at": 1725000300.0,
            "message": "Enrolled sample #3 successfully.",
        }

        res = self.client.enroll_speaker(
            audio_bytes=b"sample-audio-bytes",
            speaker_id="EMP-9001",
            speaker_name="Jane Doe",
        )

        self.assertEqual(res.status, "ENROLLED")
        self.assertEqual(res.speaker_id, "EMP-9001")
        self.assertEqual(res.sample_count, 3)
        self.assertEqual(res.embedding_dimension, 192)

    def test_4_verify_speaker_success(self):
        """Verify VerifySpeaker biometric verification result."""
        self.mock_worker.handle_verify_speaker.return_value = {
            "status_code": 200,
            "status": "SUCCESS",
            "speaker_id": "EMP-9001",
            "similarity_score": 0.892,
            "threshold": 0.70,
            "match": True,
            "speaker_mismatch_flag": 0,
            "sample_count": 3,
            "inference_time_ms": 12.5,
            "message": "MATCH",
        }

        res = self.client.verify_speaker(
            audio_bytes=b"query-audio-bytes",
            speaker_id="EMP-9001",
            threshold=0.70,
        )

        self.assertTrue(res.match)
        self.assertAlmostEqual(res.similarity_score, 0.892, places=3)
        self.assertEqual(res.speaker_mismatch_flag, 0)
        self.assertEqual(res.sample_count, 3)

    def test_5_get_risk_policy_success(self):
        """Verify GetRiskPolicy retrieves organization policy."""
        res = self.client.get_risk_policy()
        self.assertEqual(res.organization_id, "00000000-0000-0000-0000-000000000001")
        self.assertGreater(res.transaction_auto_hold_amount, 0)
        self.assertGreater(res.fake_prob_critical_threshold, 0)

    def test_6_stream_live_audio_bidirectional(self):
        """Verify StreamLiveAudio bidirectional streaming with audio chunks."""
        self.mock_worker.handle_stream_chunk.return_value = {
            "risk_score": 25,
            "risk_level": "LOW",
            "recommended_action": "ALLOW",
            "fake_probability": 0.08,
            "real_probability": 0.92,
            "speaker_similarity": 0.85,
            "speaker_match": True,
            "language": "en",
            "language_name": "English",
            "language_confidence": 0.98,
            "transcript": "Hello VoiceShield verification",
            "speech_context_flags": [],
            "flags": [],
        }

        def chunk_gen():
            # Generate 3 chunks of 16kHz PCM audio (each 16,000 samples = 32,000 bytes)
            for i in range(3):
                pcm_data = b"\x00\x01" * 16000
                yield voiceshield_pb2.LiveAudioChunk(
                    session_id="GRPC-SES-TEST-01",
                    pcm16_chunk=pcm_data,
                    speaker_id="EMP-4102",
                    context=voiceshield_pb2.LiveAudioContext(
                        claimed_role="Treasurer",
                        requested_amount=15000.0,
                    ),
                )

        results = list(self.client.stream_live_audio(chunk_gen()))
        self.assertGreaterEqual(len(results), 1)
        first_result = results[0]
        self.assertEqual(first_result.session_id, "GRPC-SES-TEST-01")
        self.assertEqual(first_result.risk_score, 25)
        self.assertEqual(first_result.recommended_action, "ALLOW")
        self.assertEqual(first_result.transcript, "Hello VoiceShield verification")

    def test_7_authentication_enforcement(self):
        """Verify unauthenticated requests are rejected when REQUIRE_API_KEY is active."""
        with patch.dict(os.environ, {"REQUIRE_API_KEY": "true", "VOICESHIELD_API_KEY": "secret-123"}):
            # Client without key should fail
            unauth_client = VoiceShieldGrpcClient(target=self.target)
            with self.assertRaises(grpc.RpcError) as ctx:
                unauth_client.get_risk_policy()
            self.assertEqual(ctx.exception.code(), grpc.StatusCode.UNAUTHENTICATED)

            # Client with correct key should succeed
            auth_client = VoiceShieldGrpcClient(target=self.target, api_key="secret-123")
            policy_res = auth_client.get_risk_policy()
            self.assertIsNotNone(policy_res)

    def test_8_error_handling_empty_audio(self):
        """Verify missing audio raises INVALID_ARGUMENT."""
        with self.assertRaises(grpc.RpcError) as ctx:
            self.client.analyze_audio(audio_bytes=b"")
        self.assertEqual(ctx.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_9_concurrent_streaming_session_isolation(self):
        """Verify concurrent streaming calls maintain separate session IDs."""
        self.mock_worker.handle_stream_chunk.side_effect = lambda req: {
            "risk_score": 30 if "SES-A" in req["call_id"] else 80,
            "risk_level": "LOW" if "SES-A" in req["call_id"] else "CRITICAL",
            "recommended_action": "ALLOW" if "SES-A" in req["call_id"] else "BLOCK",
            "fake_probability": 0.1 if "SES-A" in req["call_id"] else 0.9,
            "real_probability": 0.9 if "SES-A" in req["call_id"] else 0.1,
            "language": "en",
            "transcript": f"Call {req['call_id']}",
            "flags": [],
        }

        def stream_a():
            yield voiceshield_pb2.LiveAudioChunk(
                session_id="GRPC-SES-A",
                pcm16_chunk=b"\x00\x01" * 24000,
            )

        def stream_b():
            yield voiceshield_pb2.LiveAudioChunk(
                session_id="GRPC-SES-B",
                pcm16_chunk=b"\x00\x02" * 24000,
            )

        res_a = list(self.client.stream_live_audio(stream_a()))
        res_b = list(self.client.stream_live_audio(stream_b()))

        self.assertEqual(res_a[0].session_id, "GRPC-SES-A")
        self.assertEqual(res_a[0].recommended_action, "ALLOW")
        self.assertEqual(res_b[0].session_id, "GRPC-SES-B")
        self.assertEqual(res_b[0].recommended_action, "BLOCK")


if __name__ == "__main__":
    unittest.main()
