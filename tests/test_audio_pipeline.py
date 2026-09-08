"""
Integration tests for the VoiceShield end-to-end audio pipeline.
Validates:
- Stage 1: Microphone/file audio capture & preprocessing
- Stage 2: WebM/Opus -> 16kHz mono PCM conversion
- Stage 3: Duration & SNR validation
- Stage 4: Specialist detector inference (AASIST / spectral fallback)
- Stage 5: Structured output schema with detection_source
"""

import os
from pathlib import Path
import unittest
import numpy as np

from app.audio.preprocessing import AudioPreprocessor
from app.audio.ingestion import convert_and_decode_to_16k_mono
from app.config import AudioConfig, ModelConfig
from app.models.detector import VoiceCloneDetector
from app.utils.audio_utils import (
    AudioTooShortError,
    CorruptAudioError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "test_samples"


class TestAudioPipeline(unittest.TestCase):
    """Verifies audio pipeline stages end to end."""

    @classmethod
    def setUpClass(cls):
        cls.audio_config = AudioConfig(
            sample_rate=16000,
            min_duration_sec=0.5,
            max_duration_sec=30.0,
            silence_threshold_db=-45.0,
            normalize_peak=True,
        )
        cls.preprocessor = AudioPreprocessor(cls.audio_config)
        cls.model_config = ModelConfig(
            device="cpu",
            hf_offline_mode=True,
        )
        cls.detector = VoiceCloneDetector(cls.model_config)

    def test_clean_human_audio_pipeline(self):
        """Clean human voice should be preprocessed correctly and classified with low fake probability."""
        real_wav = SAMPLES_DIR / "human" / "real_01.wav"
        if not real_wav.exists():
            self.skipTest(f"Sample not found: {real_wav}")

        preprocessed = self.preprocessor.process(real_wav)
        self.assertEqual(preprocessed.sample_rate, 16000)
        self.assertEqual(preprocessed.channels, 1)
        self.assertGreater(preprocessed.processed_duration_sec, 0.5)
        self.assertGreater(preprocessed.estimated_snr_db, 0.0)

        prediction = self.detector.predict(preprocessed)
        self.assertIn(prediction.detection_source, ["aasist", "wav2vec2", "spectral_heuristic"])
        self.assertLess(
            prediction.fake_probability,
            0.4,
            f"Human audio got unexpectedly high fake probability: {prediction.fake_probability}",
        )
        self.assertFalse(prediction.is_synthetic)

    def test_ai_generated_audio_pipeline(self):
        """Synthetic AI voice should be detected with high fake probability."""
        fake_wav = SAMPLES_DIR / "ai" / "fake_01.wav"
        if not fake_wav.exists():
            self.skipTest(f"Sample not found: {fake_wav}")

        preprocessed = self.preprocessor.process(fake_wav)
        self.assertEqual(preprocessed.sample_rate, 16000)
        self.assertEqual(preprocessed.channels, 1)

        prediction = self.detector.predict(preprocessed)
        self.assertIn(prediction.detection_source, ["aasist", "wav2vec2", "spectral_heuristic"])
        self.assertGreater(
            prediction.fake_probability,
            0.6,
            f"AI audio got unexpectedly low fake probability: {prediction.fake_probability}",
        )
        self.assertTrue(prediction.is_synthetic)

    def test_webm_conversion_and_detection(self):
        """WebM/Opus audio converts to 16kHz mono and processes through detector."""
        fake_webm = SAMPLES_DIR / "ai" / "fake_01.webm"
        if not fake_webm.exists():
            self.skipTest(f"Sample not found: {fake_webm}")

        with open(fake_webm, "rb") as f:
            webm_bytes = f.read()

        waveform, sr, _ = convert_and_decode_to_16k_mono(webm_bytes, original_filename="fake_01.webm")
        self.assertEqual(sr, 16000)
        self.assertGreater(len(waveform), 0)

        # Also verify preprocessor.process handles .webm directly
        preprocessed = self.preprocessor.process(fake_webm)
        self.assertEqual(preprocessed.sample_rate, 16000)
        self.assertEqual(preprocessed.channels, 1)

        prediction = self.detector.predict(preprocessed)
        self.assertGreater(prediction.fake_probability, 0.6)

    def test_short_audio_rejection(self):
        """Audio under 0.5s should raise AudioTooShortError."""
        short_wav = SAMPLES_DIR / "short_04s.wav"
        if not short_wav.exists():
            self.skipTest(f"Sample not found: {short_wav}")

        with self.assertRaises(AudioTooShortError):
            self.preprocessor.process(short_wav)

    def test_corrupt_empty_audio_rejection(self):
        """Empty audio bytes should raise Ingestion or Corrupt error."""
        with self.assertRaises(Exception):
            convert_and_decode_to_16k_mono(b"", original_filename="empty.wav")

    def test_detection_source_attribution(self):
        """Detection results must attribute source detector (aasist, wav2vec2, or spectral fallback)."""
        real_wav = SAMPLES_DIR / "human" / "real_01.wav"
        if not real_wav.exists():
            self.skipTest(f"Sample not found: {real_wav}")

        preprocessed = self.preprocessor.process(real_wav)
        prediction = self.detector.predict(preprocessed)

        self.assertTrue(hasattr(prediction, "detection_source"))
        self.assertIn(prediction.detection_source, ["aasist", "wav2vec2", "spectral_heuristic"])


if __name__ == "__main__":
    unittest.main()
