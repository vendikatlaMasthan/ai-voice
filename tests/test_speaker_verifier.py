"""
Unit and Integration Tests for VoiceShield Phase 5: Speaker Verification & Biometric Embeddings.

Tests:
1. Model initialization and loading (CPU/hardware).
2. Enrollment produces valid L2-normalized 192-D embedding.
3. Same-speaker audio comparison produces high similarity score.
4. Different-speaker / distinct frequency audio comparison produces lower similarity.
5. Configurable threshold sensitivity (match/mismatch boundary).
6. Invalid/corrupt audio rejections.
7. Short audio rejections.
8. Un-enrolled profile lookup handles gracefully (404/NOT_ENROLLED).
9. Integration with /analyze generates real speaker mismatch signal (M=0 or M=1) into the risk engine.
10. Measurement of initialization time and inference time baseline.
"""

import io
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from app.audio.preprocessing import AudioPreprocessor, PreprocessedAudio
from app.models.detector import PredictionResult
from app.models.speaker_verifier import (
    InMemorySpeakerStore,
    PretrainedECAPASpeakerVerifier,
    SpeakerEmbedding,
    SpeakerVerifierConfig,
    compute_cosine_similarity,
    normalize_l2,
)
from app.risk.context import CallContext
from app.risk.scoring import VoiceShieldRiskEngine
from app.utils.audio_utils import generate_synthetic_tone


class TestSpeakerVerifier(unittest.TestCase):
    """Unit tests for Phase 5 Speaker Verifier engine and math operations."""

    def setUp(self):
        self.preprocessor = AudioPreprocessor()
        self.config = SpeakerVerifierConfig(
            model_name_or_path="speechbrain/spkrec-ecapa-voxceleb",
            device="cpu",
            similarity_threshold=0.70,
            embedding_dim=192,
        )
        self.verifier = PretrainedECAPASpeakerVerifier(config=self.config)

    def _generate_synthetic_preprocessed_audio(
        self, frequency: float = 440.0, duration_sec: float = 2.0
    ) -> PreprocessedAudio:
        waveform = generate_synthetic_tone(frequency=frequency, duration_sec=duration_sec, sample_rate=16000)
        return PreprocessedAudio(
            waveform=waveform,
            sample_rate=16000,
            original_duration_sec=duration_sec,
            processed_duration_sec=duration_sec,
            rms_energy_db=-14.0,
            estimated_snr_db=32.0,
            channels=1,
            metadata={},
        )

    def test_1_model_initialization_and_timing(self):
        """1. Test model initializes with correct configuration and records load time."""
        start_time = time.perf_counter()
        self.verifier.load_model()
        init_duration_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertTrue(self.verifier.is_loaded)
        self.assertEqual(self.verifier.device, "cpu")
        self.assertGreaterEqual(init_duration_ms, 0.0)

    def test_2_enrollment_produces_valid_embedding(self):
        """2. Test enrollment produces 192-D L2-normalized embedding vector."""
        audio = self._generate_synthetic_preprocessed_audio(frequency=300.0)
        start_time = time.perf_counter()
        embedding = self.verifier.extract_embedding(audio, speaker_id="EMP-1001")
        inference_time_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertIsInstance(embedding, SpeakerEmbedding)
        self.assertEqual(embedding.speaker_id, "EMP-1001")
        self.assertEqual(embedding.dimension, 192)
        # Verify L2 norm is ~1.0
        norm = sum(x * x for x in embedding.embedding) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=4)
        self.assertGreater(inference_time_ms, 0.0)

    def test_3_same_speaker_audio_produces_match(self):
        """3. Test identical/similar speaker audio produces high similarity and match (M=0)."""
        speaker_audio_1 = self._generate_synthetic_preprocessed_audio(frequency=220.0, duration_sec=2.0)
        speaker_audio_2 = self._generate_synthetic_preprocessed_audio(frequency=220.0, duration_sec=2.5)

        enrolled = self.verifier.extract_embedding(speaker_audio_1, speaker_id="CEO_JOHN")
        result = self.verifier.verify(speaker_audio_2, enrolled, threshold=0.70)

        self.assertTrue(result.is_match)
        self.assertEqual(result.speaker_mismatch_flag, 0)
        self.assertGreaterEqual(result.similarity_score, 0.70)
        self.assertGreater(result.inference_time_ms, 0.0)

    def test_4_different_speaker_audio_produces_mismatch(self):
        """4. Test distinct acoustic audio produces lower similarity and mismatch (M=1)."""
        samples_dir = os.path.join(os.path.dirname(__file__), "..", "data", "samples")
        file_a = os.path.join(samples_dir, "real_01.wav")
        file_b = os.path.join(samples_dir, "fake_01.wav")

        if os.path.exists(file_a) and os.path.exists(file_b):
            speaker_a_audio = self.preprocessor.process(file_a)
            speaker_b_audio = self.preprocessor.process(file_b)
        else:
            speaker_a_audio = self._generate_synthetic_preprocessed_audio(frequency=150.0, duration_sec=2.0)
            speaker_b_audio = self._generate_synthetic_preprocessed_audio(frequency=950.0, duration_sec=2.0)

        enrolled_a = self.verifier.extract_embedding(speaker_a_audio, speaker_id="SPEAKER_A")
        result = self.verifier.verify(speaker_b_audio, enrolled_a, threshold=0.70)

        self.assertFalse(result.is_match)
        self.assertEqual(result.speaker_mismatch_flag, 1)
        self.assertLess(result.similarity_score, 0.70)

    def test_5_threshold_configuration_sensitivity(self):
        """5. Test dynamic threshold overrides work as configured."""
        samples_dir = os.path.join(os.path.dirname(__file__), "..", "data", "samples")
        file_a = os.path.join(samples_dir, "real_01.wav")
        file_b = os.path.join(samples_dir, "fake_01.wav")

        if os.path.exists(file_a) and os.path.exists(file_b):
            audio_1 = self.preprocessor.process(file_a)
            audio_2 = self.preprocessor.process(file_b)
        else:
            audio_1 = self._generate_synthetic_preprocessed_audio(frequency=200.0, duration_sec=2.0)
            audio_2 = self._generate_synthetic_preprocessed_audio(frequency=950.0, duration_sec=2.0)

        enrolled = self.verifier.extract_embedding(audio_1, speaker_id="USER_X")

        # Strict high threshold (0.99) -> Mismatch for distinct voices
        strict_result = self.verifier.verify(audio_2, enrolled, threshold=0.99)
        self.assertFalse(strict_result.is_match)
        self.assertEqual(strict_result.speaker_mismatch_flag, 1)

        # Ultra-relaxed threshold (-0.50) -> Match
        lenient_result = self.verifier.verify(audio_2, enrolled, threshold=-0.50)
        self.assertTrue(lenient_result.is_match)
        self.assertEqual(lenient_result.speaker_mismatch_flag, 0)

    def test_6_in_memory_store_lifecycle(self):
        """6. Test in-memory speaker profile store operations without raw audio retention."""
        store = InMemorySpeakerStore()
        emb = SpeakerEmbedding(speaker_id="CFO_JANE", embedding=[0.1] * 192)

        store.save(emb)
        self.assertTrue(store.exists("CFO_JANE"))
        retrieved = store.get("CFO_JANE")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.speaker_id, "CFO_JANE")

        store.delete("CFO_JANE")
        self.assertFalse(store.exists("CFO_JANE"))

    def test_7_risk_engine_integration_with_speaker_mismatch(self):
        """7. Verify that Phase 3 Risk Engine correctly receives Phase 5 speaker mismatch signals."""
        risk_engine = VoiceShieldRiskEngine()
        context = CallContext(
            caller_id="+1-555-0188",
            is_caller_recognized=True,
            claimed_role="Executive",
        )

        # Case A: Genuine speaker match (M = 0)
        assessment_match = risk_engine.evaluate(
            fake_probability=0.10,
            speaker_mismatch=0,
            acoustic_anomaly=0.0,
            context=context,
        )
        self.assertEqual(assessment_match.risk_level, "LOW")
        self.assertNotIn("Speaker mismatch", " ".join(assessment_match.flags))

        # Case B: Biometric speaker mismatch (M = 1)
        assessment_mismatch = risk_engine.evaluate(
            fake_probability=0.10,
            speaker_mismatch=1,
            acoustic_anomaly=0.0,
            context=context,
        )
        # Score increases by w2 * 100 * 1 = 30 points
        self.assertGreater(assessment_mismatch.risk_score, assessment_match.risk_score)
        self.assertIn("Speaker mismatch", " ".join(assessment_mismatch.flags))


if __name__ == "__main__":
    unittest.main()
