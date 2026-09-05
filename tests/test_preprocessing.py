"""
Unit Tests for Audio Preprocessing & Prediction Interface.
Tests duration bounds, silence rejection, corrupt file handling, and JSON response schema.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from app.audio.preprocessing import AudioPreprocessor
from app.config import AudioConfig, ModelConfig
from app.models.detector import BaselineSpectralDetector, PredictionResult, VoiceCloneDetector
from app.utils.audio_utils import (
    AudioSilentError,
    AudioTooShortError,
    CorruptAudioError,
    FileNotFoundAudioError,
    generate_test_wav,
)


class TestAudioPreprocessing(unittest.TestCase):
    """Test suite for audio loading, validation, and silence trimming."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = AudioConfig(
            sample_rate=16000,
            min_duration_sec=0.5,
            silence_threshold_db=-45.0,
            normalize_peak=True
        )
        self.preprocessor = AudioPreprocessor(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_valid_speech_preprocessing(self):
        """Test that a valid 3-second speech-like audio passes preprocessing cleanly."""
        wav_path = Path(self.temp_dir) / "valid.wav"
        generate_test_wav(wav_path, duration_sec=3.0, sample_rate=16000, sample_type="speech_like")

        result = self.preprocessor.process(wav_path)
        self.assertEqual(result.sample_rate, 16000)
        self.assertEqual(result.channels, 1)
        self.assertGreaterEqual(result.processed_duration_sec, 0.5)
        self.assertGreater(len(result.waveform), 0)
        # Peak normalization check
        max_amp = max(abs(x) for x in result.waveform)
        self.assertAlmostEqual(max_amp, 0.95, places=2)

    def test_short_audio_rejection(self):
        """Test that audio shorter than min_duration_sec raises AudioTooShortError."""
        short_path = Path(self.temp_dir) / "short.wav"
        generate_test_wav(short_path, duration_sec=0.2, sample_rate=16000, sample_type="short")

        with self.assertRaises(AudioTooShortError):
            self.preprocessor.process(short_path)

    def test_silence_rejection(self):
        """Test that pure silent audio raises AudioSilentError."""
        silent_path = Path(self.temp_dir) / "silent.wav"
        generate_test_wav(silent_path, duration_sec=2.0, sample_rate=16000, sample_type="silence")

        with self.assertRaises(AudioSilentError):
            self.preprocessor.process(silent_path)

    def test_missing_file_error(self):
        """Test that non-existent files raise FileNotFoundAudioError."""
        missing_path = Path(self.temp_dir) / "non_existent.wav"
        with self.assertRaises(FileNotFoundAudioError):
            self.preprocessor.process(missing_path)

    def test_corrupt_file_error(self):
        """Test that invalid binary files raise CorruptAudioError."""
        corrupt_path = Path(self.temp_dir) / "corrupt.wav"
        with open(corrupt_path, "wb") as f:
            f.write(b"INVALID_HEADER_DATA_12345")

        with self.assertRaises(CorruptAudioError):
            self.preprocessor.process(corrupt_path)

    def test_detector_prediction_contract(self):
        """Test that prediction returns the exact specified dictionary contract."""
        wav_path = Path(self.temp_dir) / "valid_contract.wav"
        generate_test_wav(wav_path, duration_sec=2.0, sample_rate=16000, sample_type="speech_like")

        preprocessed = self.preprocessor.process(wav_path)
        detector = BaselineSpectralDetector(ModelConfig())
        detector.load_model()
        result = detector.predict(preprocessed)

        self.assertIsInstance(result, PredictionResult)
        self.assertIn(result.prediction, ["REAL", "FAKE"])
        self.assertGreaterEqual(result.fake_probability, 0.0)
        self.assertLessEqual(result.fake_probability, 1.0)
        self.assertGreaterEqual(result.real_probability, 0.0)
        self.assertLessEqual(result.real_probability, 1.0)
        self.assertAlmostEqual(result.fake_probability + result.real_probability, 1.0, places=3)

        d = result.to_dict()
        self.assertIn("prediction", d)
        self.assertIn("fake_probability", d)
        self.assertIn("real_probability", d)

    def test_label_mapping_resolution_logic(self):
        """Test that detector correctly parses various Hugging Face id2label conventions."""
        from unittest.mock import MagicMock
        from app.models.detector import HuggingFaceTransformerDetector

        detector = HuggingFaceTransformerDetector()
        mock_model = MagicMock()
        detector.model = mock_model

        # Case 1: Standard {0: "real", 1: "fake"}
        mock_model.config.id2label = {0: "real", 1: "fake"}
        detector._parse_label_mapping()
        self.assertEqual(detector.real_class_idx, 0)
        self.assertEqual(detector.fake_class_idx, 1)

        # Case 2: Inverted ASVspoof {0: "spoof", 1: "bonafide"}
        mock_model.config.id2label = {0: "spoof", 1: "bonafide"}
        detector._parse_label_mapping()
        self.assertEqual(detector.real_class_idx, 1)
        self.assertEqual(detector.fake_class_idx, 0)

        # Case 3: Uppercase custom labels {0: "HUMAN_SPEECH", 1: "AI_SYNTHETIC"}
        mock_model.config.id2label = {0: "HUMAN_SPEECH", 1: "AI_SYNTHETIC"}
        detector._parse_label_mapping()
        self.assertEqual(detector.real_class_idx, 0)
        self.assertEqual(detector.fake_class_idx, 1)


if __name__ == "__main__":
    unittest.main()
