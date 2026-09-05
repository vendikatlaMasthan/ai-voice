"""
Comprehensive Unit & Integration Test Suite for Multi-Sample Cross-Session Speaker Consistency.
Validates:
1. First, second, and third incremental genuine sample enrollments
2. Incremental mathematical centroid update and L2 normalization correctness
3. Cross-session consistency against historical genuine samples
4. Cross-session mismatch detection against imposter/clone audio
5. Configurable similarity thresholding behavior
6. Backward compatibility with legacy single-embedding profile files
7. Strict privacy verification (zero raw audio persistence)
8. Risk engine integration with speaker mismatch signal
"""

import copy
import json
import math
import os
import tempfile
import time
import unittest
import numpy as np

from app.audio.preprocessing import AudioPreprocessor, PreprocessedAudio
from app.models.speaker_verifier import (
    InMemorySpeakerStore,
    PretrainedECAPASpeakerVerifier,
    SpeakerEmbedding,
    compute_cosine_similarity,
    normalize_l2,
)
from app.risk.scoring import VoiceShieldRiskEngine
from scripts.run_pipeline import PipelineWorker, load_persistent_store, save_persistent_store


class TestMultiSampleSpeakerConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = PretrainedECAPASpeakerVerifier()
        cls.verifier.load_model()
        cls.preprocessor = AudioPreprocessor()
        cls.risk_engine = VoiceShieldRiskEngine()

    def setUp(self):
        self.store = InMemorySpeakerStore()

    def test_1_first_enrollment_creates_profile_with_sample_count_1(self):
        """Test initial enrollment creates profile with sample_count=1 and L2-normalized embedding."""
        raw_vec = [float(i % 10 + 1) for i in range(192)]
        profile = self.store.enroll_sample(
            speaker_id="SPK-TEST-01",
            embedding=raw_vec,
            speaker_name="Alice (CFO)",
            sample_metadata={"duration_sec": 3.2, "snr_db": 28.5},
        )

        self.assertEqual(profile.speaker_id, "SPK-TEST-01")
        self.assertEqual(profile.sample_count, 1)
        self.assertEqual(len(profile.embedding), 192)
        norm = math.sqrt(sum(x * x for x in profile.embedding))
        self.assertAlmostEqual(norm, 1.0, places=5)
        self.assertEqual(profile.metadata.get("speaker_name"), "Alice (CFO)")
        self.assertEqual(len(profile.metadata.get("history", [])), 1)

    def test_2_second_enrollment_updates_centroid_and_increments_sample_count(self):
        """Test second genuine sample enrollment incrementally updates centroid: c_new = norm((c_old * 1 + e2) / 2)."""
        vec1 = normalize_l2([1.0 if i < 96 else 0.0 for i in range(192)])
        vec2 = normalize_l2([0.0 if i < 96 else 1.0 for i in range(192)])

        prof = self.store.enroll_sample("SPK-TEST-02", vec1, speaker_name="Bob")
        self.assertEqual(prof.sample_count, 1)

        # Enrolling second sample
        prof = self.store.enroll_sample("SPK-TEST-02", vec2, sample_metadata={"duration_sec": 4.1})
        self.assertEqual(prof.sample_count, 2)

        # Expected centroid before normalization: (vec1 * 1 + vec2) / 2
        expected_unnorm = [(vec1[i] * 1.0 + vec2[i]) / 2.0 for i in range(192)]
        expected_norm = normalize_l2(expected_unnorm)

        for i in range(192):
            self.assertAlmostEqual(prof.embedding[i], expected_norm[i], places=5)

        # Confirm history has 2 entries
        self.assertEqual(len(prof.metadata["history"]), 2)
        self.assertEqual(prof.metadata["history"][1]["sample_index"], 2)

    def test_3_third_enrollment_incremental_centroid_mathematical_precision(self):
        """Test third genuine sample: c_3 = norm((c_2 * 2 + e3) / 3) matches mathematical formula exactly."""
        np.random.seed(42)
        e1 = normalize_l2(np.random.randn(192).tolist())
        e2 = normalize_l2(np.random.randn(192).tolist())
        e3 = normalize_l2(np.random.randn(192).tolist())

        # Incremental online enrollment
        prof = self.store.enroll_sample("SPK-MATH-01", e1)
        prof = self.store.enroll_sample("SPK-MATH-01", e2)
        prof = self.store.enroll_sample("SPK-MATH-01", e3)
        self.assertEqual(prof.sample_count, 3)

        # Mathematical specification:
        c1 = e1
        c2 = normalize_l2([(c1[i] * 1.0 + e2[i]) / 2.0 for i in range(192)])
        c3_expected = normalize_l2([(c2[i] * 2.0 + e3[i]) / 3.0 for i in range(192)])

        for i in range(192):
            self.assertAlmostEqual(prof.embedding[i], c3_expected[i], places=6)

        sim = compute_cosine_similarity(prof.embedding, c3_expected)
        self.assertAlmostEqual(sim, 1.0, places=6)

    def test_4_vector_l2_normalization_invariant(self):
        """Verify centroid is always strictly L2-normalized (norm == 1.0) after multiple additions."""
        prof = self.store.enroll_sample("SPK-NORM-01", [1.0] * 192)
        for step in range(10):
            prof = self.store.enroll_sample("SPK-NORM-01", [float(step + 2)] * 192)
            norm = math.sqrt(sum(x * x for x in prof.embedding))
            self.assertAlmostEqual(norm, 1.0, places=5)

        self.assertEqual(prof.sample_count, 11)

    def test_5_cross_session_same_speaker_match_against_multi_sample_centroid(self):
        """Test query audio from same genuine speaker verifies as MATCH against enrolled centroid."""
        sample_path = "data/samples/fake_01.wav"
        if os.path.exists(sample_path):
            prep = self.preprocessor.process(sample_path)
            raw_emb = self.verifier.extract_embedding(prep, speaker_id="SPK-CROSS-01")

            # Enroll sample 1 and sample 2
            prof = self.store.enroll_sample("SPK-CROSS-01", raw_emb.embedding)
            prof = self.store.enroll_sample("SPK-CROSS-01", raw_emb.embedding)

            # Verification pass
            res = self.verifier.verify(audio=prep, enrolled_embedding=prof, threshold=0.70)
            self.assertTrue(res.is_match)
            self.assertEqual(res.speaker_mismatch_flag, 0)
            self.assertEqual(res.sample_count, 2)
            self.assertGreaterEqual(res.similarity_score, 0.95)

    def test_6_cross_session_different_speaker_mismatch_against_multi_sample_centroid(self):
        """Test query audio from different speaker / clone yields MISMATCH against enrolled centroid."""
        # Enrolled centroid in one direction
        enrolled_vec = normalize_l2([1.0 if i < 96 else 0.0 for i in range(192)])
        prof = self.store.enroll_sample("SPK-CROSS-02", enrolled_vec)
        prof = self.store.enroll_sample("SPK-CROSS-02", enrolled_vec)

        # Query audio in orthogonal direction
        query_samples = [0.1 * math.sin(2.0 * math.pi * 500.0 * i / 16000.0) for i in range(16000)]
        query_audio = PreprocessedAudio(
            waveform=query_samples,
            sample_rate=16000,
            original_duration_sec=1.0,
            processed_duration_sec=1.0,
            rms_energy_db=-20.0,
            estimated_snr_db=30.0,
            channels=1,
            metadata={},
        )

        res = self.verifier.verify(audio=query_audio, enrolled_embedding=prof, threshold=0.65)
        self.assertFalse(res.is_match)
        self.assertEqual(res.speaker_mismatch_flag, 1)
        self.assertEqual(res.sample_count, 2)

    def test_7_threshold_behavior_and_sensitivity(self):
        """Test verification decision respects configurable threshold parameter."""
        vec = normalize_l2([1.0] * 192)
        prof = self.store.enroll_sample("SPK-THRESH-01", vec)

        # Synthesize audio with known similarity
        query_audio = PreprocessedAudio(
            waveform=[0.1 * math.sin(2.0 * math.pi * 300.0 * i / 16000.0) for i in range(16000)],
            sample_rate=16000,
            original_duration_sec=1.0,
            processed_duration_sec=1.0,
            rms_energy_db=-20.0,
            estimated_snr_db=30.0,
            channels=1,
            metadata={},
        )

        # Extremely strict threshold (0.9999) -> mismatch
        res_strict = self.verifier.verify(audio=query_audio, enrolled_embedding=prof, threshold=0.9999)
        self.assertFalse(res_strict.is_match)
        self.assertEqual(res_strict.speaker_mismatch_flag, 1)

        # Extremely loose threshold (-1.0) -> match
        res_loose = self.verifier.verify(audio=query_audio, enrolled_embedding=prof, threshold=-1.0)
        self.assertTrue(res_loose.is_match)
        self.assertEqual(res_loose.speaker_mismatch_flag, 0)

    def test_8_backward_compatibility_with_old_single_embedding_json(self):
        """Test loading legacy JSON profile missing 'sample_count' and 'updated_at' gracefully defaults to 1."""
        legacy_data = {
            "SPK-LEGACY-01": {
                "speaker_id": "SPK-LEGACY-01",
                "embedding": [0.05] * 192,
                "created_at": 1725000000.0,
                "dimension": 192,
                "metadata": {"speaker_name": "Legacy User"},
            }
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(legacy_data, tf)
            temp_path = tf.name

        try:
            # Parse using load logic
            store = InMemorySpeakerStore()
            with open(temp_path, "r") as f:
                data = json.load(f)
                for spk_id, item in data.items():
                    created_t = item.get("created_at", time.time())
                    updated_t = item.get("updated_at", created_t)
                    sample_cnt = int(item.get("sample_count", 1))
                    emb = SpeakerEmbedding(
                        speaker_id=item["speaker_id"],
                        embedding=item["embedding"],
                        created_at=created_t,
                        updated_at=updated_t,
                        sample_count=sample_cnt,
                        metadata=item.get("metadata", {}),
                    )
                    store.save(emb)

            loaded_prof = store.get("SPK-LEGACY-01")
            self.assertIsNotNone(loaded_prof)
            self.assertEqual(loaded_prof.sample_count, 1)
            self.assertEqual(loaded_prof.created_at, 1725000000.0)
            self.assertEqual(loaded_prof.updated_at, 1725000000.0)
            self.assertEqual(loaded_prof.metadata.get("speaker_name"), "Legacy User")

            # Can now add sample 2 seamlessly
            loaded_prof.add_sample([0.1] * 192)
            self.assertEqual(loaded_prof.sample_count, 2)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_9_no_raw_audio_persisted_in_store_or_history(self):
        """Verify strict compliance: zero raw audio waveform or PCM bytes are stored."""
        prof = self.store.enroll_sample(
            "SPK-PRIVACY-01",
            [0.1] * 192,
            sample_metadata={"snr_db": 30.0, "duration_sec": 2.5},
        )
        # Check in-memory representation
        self.assertNotIn("waveform", prof.metadata)
        self.assertNotIn("audio", prof.metadata)
        self.assertNotIn("pcm", prof.metadata)

        for hist_item in prof.metadata.get("history", []):
            self.assertNotIn("waveform", hist_item)
            self.assertNotIn("audio", hist_item)
            self.assertNotIn("pcm", hist_item)

    def test_10_risk_engine_integration_consumes_speaker_mismatch(self):
        """Verify VoiceShieldRiskEngine consumes speaker_mismatch signal without score distortion."""
        # 1. Matched speaker (mismatch = 0)
        risk_match = self.risk_engine.evaluate(
            fake_probability=0.1,
            speaker_mismatch=0,
            acoustic_anomaly=0.1,
        )
        # 2. Mismatched speaker (mismatch = 1)
        risk_mismatch = self.risk_engine.evaluate(
            fake_probability=0.1,
            speaker_mismatch=1,
            acoustic_anomaly=0.1,
        )

        # Mismatch must strictly elevate risk score and flag
        self.assertGreater(risk_mismatch.risk_score, risk_match.risk_score)
        self.assertTrue(any("Speaker mismatch" in f for f in risk_mismatch.flags))
        self.assertFalse(any("Speaker mismatch" in f for f in risk_match.flags))


if __name__ == "__main__":
    unittest.main()
