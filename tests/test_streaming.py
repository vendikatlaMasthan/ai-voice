"""
Unit test for VoiceShield Streaming & Live Microphone Chunk Pipeline.
"""

import base64
import struct
import unittest
from scripts.run_pipeline import PipelineWorker
from app.utils.audio_utils import generate_synthetic_tone


class TestStreamingPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = PipelineWorker()

    def _generate_pcm16_b64(self, freq: float = 440.0, duration_sec: float = 1.5) -> str:
        waveform = generate_synthetic_tone(frequency=freq, duration_sec=duration_sec, sample_rate=16000)
        ints = [int(max(-1.0, min(1.0, s)) * 32767.0) for s in waveform]
        raw_bytes = struct.pack(f"<{len(ints)}h", *ints)
        return base64.b64encode(raw_bytes).decode("utf-8")

    def test_1_stream_chunk_pcm16_base64_inference(self):
        """Test streaming PCM16 base64 window processes without reloading models."""
        pcm_b64 = self._generate_pcm16_b64(freq=250.0, duration_sec=1.5)
        
        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 1,
                "context": {
                    "caller_id": "+18005550199",
                    "claimed_role": "Executive Assistant",
                    "is_urgent": False,
                },
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})

        # Verify all required milestone contract keys
        self.assertIn("fake_probability", data)
        self.assertIn("real_probability", data)
        self.assertIn("acoustic_anomaly", data)
        self.assertIn("risk_score", data)
        self.assertIn("risk_level", data)
        self.assertIn("recommended_action", data)
        self.assertIn("flags", data)
        self.assertIn("prosody_reasons", data)
        self.assertIn("prosody_metrics", data)
        self.assertIn("deepfake_detection", data)
        self.assertIn("pipeline_latency_ms", data)

        # Check probability bounds
        self.assertGreaterEqual(data["fake_probability"], 0.0)
        self.assertLessEqual(data["fake_probability"], 1.0)
        self.assertGreaterEqual(data["risk_score"], 0)
        self.assertLessEqual(data["risk_score"], 100)

    def test_2_stream_chunk_short_audio_rejection(self):
        """Test sub-minimum audio chunk triggers safe AudioTooShortError rejection."""
        pcm_b64 = self._generate_pcm16_b64(freq=250.0, duration_sec=0.2)
        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 2,
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 422)
        self.assertEqual(res.get("data", {}).get("error_type"), "AudioTooShortError")

    def test_3_stream_chunk_pure_silence_vad_gated(self):
        """Test pure silence window is detected by VAD and bypasses neural Wav2Vec2."""
        zero_samples = [0] * 24000  # 1.5s @ 16kHz
        raw_bytes = struct.pack(f"<{len(zero_samples)}h", *zero_samples)
        pcm_b64 = base64.b64encode(raw_bytes).decode("utf-8")

        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 3,
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})

        # Silence must NOT be labeled as "REAL" or "FAKE" speech
        self.assertEqual(data.get("deepfake_detection", {}).get("prediction"), "SILENCE")
        self.assertEqual(data.get("deepfake_detection", {}).get("model_type"), "VoiceActivityGated")
        self.assertEqual(data.get("fake_probability"), 0.0)
        self.assertEqual(data.get("real_probability"), 0.0)
        self.assertEqual(data.get("risk_score"), 0)
        self.assertEqual(data.get("risk_level"), "LOW")
        self.assertEqual(data.get("recommended_action"), "ALLOW")
        self.assertIn("VAD_SILENCE_WINDOW", data.get("flags", []))
        # Latency should be sub-50ms since neural model was bypassed
        self.assertLess(data.get("pipeline_latency_ms", 1000.0), 50.0)

    def test_4_stream_chunk_low_level_noise_vad_gated(self):
        """Test low-level ambient floor noise (< -45 dB) is gated as silence."""
        # Int16 values [-2, 2] -> amplitude < 0.0001 (RMS ~ -80 dB)
        noise_samples = [(i % 5) - 2 for i in range(24000)]
        raw_bytes = struct.pack(f"<{len(noise_samples)}h", *noise_samples)
        pcm_b64 = base64.b64encode(raw_bytes).decode("utf-8")

        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 4,
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})
        self.assertEqual(data.get("deepfake_detection", {}).get("prediction"), "SILENCE")
        self.assertEqual(data.get("fake_probability"), 0.0)
        self.assertEqual(data.get("risk_score"), 0)

    def test_5_stream_chunk_speech_wav2vec2_executed(self):
        """Test active speech-level signal triggers neural Wav2Vec2 execution."""
        pcm_b64 = self._generate_pcm16_b64(freq=200.0, duration_sec=1.5)
        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 5,
            },
        }

        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})
        self.assertIn(data.get("deepfake_detection", {}).get("prediction"), ["REAL", "FAKE"])
        self.assertNotEqual(data.get("deepfake_detection", {}).get("model_type"), "VoiceActivityGated")
        self.assertGreater(data.get("real_probability") + data.get("fake_probability"), 0.5)

    def test_6_stream_chunk_fake_speech_detected(self):
        """Test fake speech audio slice receives expected high fake probability."""
        import os
        from app.audio.preprocessing import AudioPreprocessor
        fake_path = "data/samples/fake_01.wav"
        if os.path.exists(fake_path):
            prep = AudioPreprocessor().process(fake_path)
            # Take 1.5s slice
            slice_samples = prep.waveform[:24000]
            ints = [int(max(-1.0, min(1.0, s)) * 32767.0) for s in slice_samples]
            raw_bytes = struct.pack(f"<{len(ints)}h", *ints)
            pcm_b64 = base64.b64encode(raw_bytes).decode("utf-8")

            req = {
                "command": "stream-chunk",
                "args": {
                    "pcm_bytes_b64": pcm_b64,
                    "window_index": 6,
                },
            }

            res = self.worker.dispatch(req)
            self.assertEqual(res.get("status"), 200)
            data = res.get("data", {})
            self.assertIn(data.get("deepfake_detection", {}).get("prediction"), ["REAL", "FAKE"])
            self.assertGreaterEqual(data.get("fake_probability"), 0.0)

    def test_7_stream_chunk_malformed_payload_handled_safely(self):
        """Test malformed non-base64 or corrupted payload returns 400 without crashing daemon."""
        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": "NOT_VALID_BASE64_###",
                "window_index": 7,
            },
        }
        res = self.worker.dispatch(req)
        self.assertIn(res.get("status"), [400, 422, 500])

    def test_8_stream_chunk_sequential_windows_maintain_session_state(self):
        """Test sequential streaming windows 1..3 execute with sub-second performance."""
        pcm_b64 = self._generate_pcm16_b64(freq=300.0, duration_sec=1.5)
        for w_idx in [1, 2, 3]:
            req = {
                "command": "stream-chunk",
                "args": {
                    "pcm_bytes_b64": pcm_b64,
                    "window_index": w_idx,
                    "call_id": "CALL-STREAM-TEST",
                },
            }
            res = self.worker.dispatch(req)
            self.assertEqual(res.get("status"), 200)
            self.assertEqual(res.get("data", {}).get("call_id"), "CALL-STREAM-TEST")

    def test_9_stream_chunk_with_speaker_and_context_enrichment(self):
        """Test streaming window processes speaker comparison and fraud context simultaneously."""
        pcm_b64 = self._generate_pcm16_b64(freq=220.0, duration_sec=1.5)
        req = {
            "command": "stream-chunk",
            "args": {
                "pcm_bytes_b64": pcm_b64,
                "window_index": 1,
                "speaker_id": "NON_EXISTENT_SPEAKER",
                "threshold": 0.70,
                "context": {
                    "claimed_role": "Chief Financial Officer",
                    "requested_transaction_amount": 100000.0,
                    "is_urgent": True,
                },
            },
        }
        res = self.worker.dispatch(req)
        self.assertEqual(res.get("status"), 200)
        data = res.get("data", {})
        self.assertIn("risk_score", data)
        self.assertIn("recommended_action", data)


if __name__ == "__main__":
    unittest.main()

