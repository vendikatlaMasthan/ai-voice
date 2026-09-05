"""
Unit tests for VoiceShield Prosody & Acoustic Anomaly Analyzer.
"""

import unittest
from app.audio.preprocessing import PreprocessedAudio
from app.audio.prosody import ProsodyAnalyzer, ProsodyResult
from app.utils.audio_utils import generate_synthetic_tone, calculate_rms, linear_to_db


class TestProsodyAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = ProsodyAnalyzer(sample_rate=16000)

    def _create_audio(self, waveform: list) -> PreprocessedAudio:
        dur = len(waveform) / 16000.0
        rms = calculate_rms(waveform)
        rms_db = linear_to_db(rms)
        return PreprocessedAudio(
            waveform=waveform,
            sample_rate=16000,
            original_duration_sec=dur,
            processed_duration_sec=dur,
            rms_energy_db=rms_db,
            estimated_snr_db=35.0,
            channels=1,
            metadata={},
        )

    def test_1_pure_sine_tone_detects_monotone(self):
        """Pure single-frequency sine tone has 0 pitch variance -> triggers monotone anomaly."""
        waveform = generate_synthetic_tone(frequency=220.0, duration_sec=1.5, sample_rate=16000)
        audio = self._create_audio(waveform)
        result = self.analyzer.analyze(audio)

        self.assertIsInstance(result, ProsodyResult)
        self.assertGreater(result.acoustic_anomaly, 0.20)
        self.assertTrue(any("monotone" in r.lower() or "jitter" in r.lower() for r in result.prosody_reasons))
        self.assertAlmostEqual(result.metrics["f0_mean_hz"], 220.0, delta=10.0)

    def test_2_pitch_modulated_speech_like_audio(self):
        """Speech-like audio with natural dynamic pitch variance produces lower anomaly."""
        import math
        samples = []
        sr = 16000
        phase = 0.0
        for i in range(int(1.5 * sr)):
            t = i / sr
            # F0 modulates smoothly between 130 and 170 Hz
            f0 = 150.0 + 20.0 * math.sin(2.0 * math.pi * 2.0 * t)
            phase += 2.0 * math.pi * f0 / sr
            s = 0.5 * math.sin(phase) + 0.2 * math.sin(2.0 * phase)
            samples.append(s)

        audio = self._create_audio(samples)
        result = self.analyzer.analyze(audio)

        self.assertIsInstance(result, ProsodyResult)
        self.assertLess(result.acoustic_anomaly, 0.50)
        self.assertGreater(result.metrics["f0_std_hz"], 8.0)

    def test_3_short_or_empty_frame(self):
        """Very short audio returns safe default without crashing."""
        audio = self._create_audio([0.0] * 100)
        result = self.analyzer.analyze(audio)
        self.assertIsInstance(result, ProsodyResult)
        self.assertEqual(result.acoustic_anomaly, 0.0)


if __name__ == "__main__":
    unittest.main()
