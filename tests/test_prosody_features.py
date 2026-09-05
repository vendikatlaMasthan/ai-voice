"""
Unit and Integration Tests for Prosody & Acoustic Anomaly Analysis Module.
Verifies deterministic feature extraction, edge case safety, anomaly scoring,
explainable diagnostic reasons, and risk engine integration.
"""

import math
import random
import unittest

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from app.audio.preprocessing import AudioPreprocessor, PreprocessedAudio
from app.audio.prosody import (
    ProsodyAnalysisResult,
    ProsodyAnalyzer,
    ProsodyAnalyzerConfig,
)
from app.risk.scoring import VoiceShieldRiskEngine, RiskSignals


def generate_synthetic_tone(
    freq_hz: float = 200.0,
    duration_sec: float = 3.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
    add_jitter: bool = False,
    add_pauses: bool = False,
) -> PreprocessedAudio:
    """Generates a synthetic tone/waveform for deterministic prosody testing."""
    n_samples = int(duration_sec * sample_rate)
    
    if NUMPY_AVAILABLE:
        t = np.linspace(0, duration_sec, n_samples, endpoint=False)
        if add_jitter:
            f_inst = freq_hz + 40.0 * np.sin(2 * np.pi * 3.0 * t) + 15.0 * np.sin(2 * np.pi * 7.5 * t)
            phase = 2 * np.pi * np.cumsum(f_inst) / sample_rate
            waveform = amplitude * np.sin(phase)
        else:
            waveform = amplitude * np.sin(2 * np.pi * freq_hz * t)

        if add_pauses:
            pause_len = int(0.25 * sample_rate)
            chunk_len = int(0.60 * sample_rate)
            for start in range(chunk_len, n_samples, chunk_len + pause_len):
                end = min(n_samples, start + pause_len)
                waveform[start:end] = 0.0

        waveform += np.random.normal(0, 0.002, n_samples)
        waveform = np.clip(waveform, -1.0, 1.0)
        samples_list = waveform.tolist()
    else:
        samples_list = []
        phase = 0.0
        for i in range(n_samples):
            t_sec = i / float(sample_rate)
            if add_jitter:
                f_inst = freq_hz + 40.0 * math.sin(2.0 * math.pi * 3.0 * t_sec) + 15.0 * math.sin(2.0 * math.pi * 7.5 * t_sec)
                phase += 2.0 * math.pi * f_inst / float(sample_rate)
                val = amplitude * math.sin(phase)
            else:
                val = amplitude * math.sin(2.0 * math.pi * freq_hz * t_sec)
            
            if add_pauses:
                chunk_period = int(0.85 * sample_rate)
                pause_len = int(0.25 * sample_rate)
                pos_in_period = i % chunk_period
                if pos_in_period >= (chunk_period - pause_len):
                    val = 0.0
            
            val += random.gauss(0.0, 0.002)
            val = max(-1.0, min(1.0, val))
            samples_list.append(val)

    return PreprocessedAudio(
        waveform=samples_list,
        sample_rate=sample_rate,
        original_duration_sec=duration_sec,
        processed_duration_sec=duration_sec,
        estimated_snr_db=32.0,
        rms_energy_db=-18.0,
        channels=1,
        metadata={"source": "synthetic_test_generator"},
    )



class TestProsodyFeatures(unittest.TestCase):
    """Test suite for ProsodyAnalyzer feature extraction and anomaly scoring."""

    def setUp(self):
        self.analyzer = ProsodyAnalyzer()

    def test_1_valid_speech_produces_score_in_bounds(self):
        """1. Test that valid speech produces a score strictly bounded in [0.0, 1.0]."""
        audio = generate_synthetic_tone(freq_hz=180.0, duration_sec=3.0, add_jitter=True, add_pauses=True)
        result = self.analyzer.analyze(audio)

        self.assertIsInstance(result, ProsodyAnalysisResult)
        self.assertGreaterEqual(result.acoustic_anomaly, 0.0)
        self.assertLessEqual(result.acoustic_anomaly, 1.0)
        self.assertEqual(result.status, "DETERMINISTIC_PROSODY_ANALYSIS")
        self.assertIn("f0_mean_hz", result.features)
        self.assertIn("energy_std", result.features)
        self.assertIn("spectral_centroid_hz", result.features)
        self.assertIn("hf_energy_ratio", result.features)

    def test_2_deterministic_output_for_same_input(self):
        """2. Test that identical audio waveforms produce bitwise identical anomaly scores."""
        audio = generate_synthetic_tone(freq_hz=220.0, duration_sec=2.5, add_jitter=False)
        res_1 = self.analyzer.analyze(audio)
        res_2 = self.analyzer.analyze(audio)

        self.assertEqual(res_1.acoustic_anomaly, res_2.acoustic_anomaly)
        self.assertEqual(res_1.features["f0_mean_hz"], res_2.features["f0_mean_hz"])
        self.assertEqual(res_1.features["energy_mean"], res_2.features["energy_mean"])
        self.assertEqual(res_1.anomaly_reasons, res_2.anomaly_reasons)

    def test_3_short_valid_audio_does_not_crash(self):
        """3. Test that short valid audio (1.0s) extracts features gracefully without crashing."""
        short_audio = generate_synthetic_tone(freq_hz=150.0, duration_sec=1.0)
        result = self.analyzer.analyze(short_audio)

        self.assertGreaterEqual(result.acoustic_anomaly, 0.0)
        self.assertLessEqual(result.acoustic_anomaly, 1.0)
        self.assertGreater(result.features["duration_sec"], 0.0)

    def test_4_low_energy_audio_handled_safely(self):
        """4. Test that near-silent or very low energy waveforms do not throw division-by-zero."""
        n_samples = 16000 * 2
        if NUMPY_AVAILABLE:
            low_energy_wave = (np.random.normal(0, 0.0001, n_samples)).tolist()
        else:
            low_energy_wave = [random.gauss(0, 0.0001) for _ in range(n_samples)]
        audio = PreprocessedAudio(
            waveform=low_energy_wave,
            sample_rate=16000,
            original_duration_sec=2.0,
            processed_duration_sec=2.0,
            estimated_snr_db=5.0,
            rms_energy_db=-48.0,
            channels=1,
            metadata={"source": "low_energy_test"},
        )


        result = self.analyzer.analyze(audio)
        self.assertIsInstance(result.acoustic_anomaly, float)
        self.assertGreaterEqual(result.acoustic_anomaly, 0.0)
        self.assertLessEqual(result.acoustic_anomaly, 1.0)

    def test_5_different_acoustic_characteristics_produce_different_scores(self):
        """5. Test that monotonic flat tone vs pitch-modulated dynamic speech produce distinct anomaly scores."""
        # Flat robotic monotone (constant 250Hz, constant amplitude)
        robotic_audio = generate_synthetic_tone(freq_hz=250.0, duration_sec=3.0, add_jitter=False, add_pauses=False)
        # Expressive speech-like tone (frequency jitter + natural pauses)
        expressive_audio = generate_synthetic_tone(freq_hz=200.0, duration_sec=3.0, add_jitter=True, add_pauses=True)

        res_robotic = self.analyzer.analyze(robotic_audio)
        res_expressive = self.analyzer.analyze(expressive_audio)

        # Robotic audio should have higher anomaly score than natural expressive speech
        self.assertGreater(res_robotic.acoustic_anomaly, res_expressive.acoustic_anomaly)
        self.assertLess(res_robotic.features["f0_cv"], 0.05)
        self.assertGreater(res_expressive.features["f0_cv"], 0.08)

    def test_6_explainable_reasons_returned_on_anomalies(self):
        """6. Test that human-readable diagnostic reasons are populated when thresholds are crossed."""
        # Unnatural monotonic flat tone with high continuous voicing
        flat_audio = generate_synthetic_tone(freq_hz=160.0, duration_sec=3.0, add_jitter=False, add_pauses=False)
        result = self.analyzer.analyze(flat_audio)

        self.assertGreater(len(result.anomaly_reasons), 0)
        reasons_text = " ".join(result.anomaly_reasons).lower()
        self.assertTrue(
            "monotone" in reasons_text or "flatness" in reasons_text or "pauses" in reasons_text
        )

    def test_7_risk_engine_integrates_prosody_signal(self):
        """7. Verify that VoiceShieldRiskEngine dynamically receives and weights real acoustic_anomaly."""
        risk_engine = VoiceShieldRiskEngine()

        # Baseline: P_fake=0.0, M=0, C=0, A=0.0 -> Score = 0
        res_zero = risk_engine.evaluate(fake_probability=0.0, speaker_mismatch=0, acoustic_anomaly=0.0)
        self.assertEqual(res_zero.risk_score, 0)

        # When acoustic anomaly = 0.80 -> w3 * 50 * A = 0.1 * 50 * 0.80 = +4 points
        res_prosody = risk_engine.evaluate(
            fake_probability=0.0,
            speaker_mismatch=0,
            acoustic_anomaly=0.80,
            prosody_reasons=["Robotic monotone pitch contour with minimal F0 variation"],
        )
        self.assertEqual(res_prosody.risk_score, 4)
        self.assertEqual(res_prosody.signals["acoustic_anomaly"], 0.80)
        self.assertIn("Robotic monotone pitch contour with minimal F0 variation", res_prosody.flags)


if __name__ == "__main__":
    unittest.main()
