"""
Prosody & Acoustic Anomaly Analysis Module for VoiceShield.

Provides lightweight, deterministic, CPU-friendly feature extraction and explainable
prosodic anomaly scoring on 16 kHz preprocessed audio waveforms without requiring heavy
neural model downloads.

Features extracted:
- Fundamental Frequency (F0) contour, mean, standard deviation, coefficient of variation (CV)
- Energy / RMS frame dynamics, dynamic range, and energy flatness
- Zero Crossing Rate (ZCR) mean and variation
- Spectral Centroid, Spectral Spread, and High-Frequency Energy Ratio
- Speech-to-Pause ratios and pause transition dynamics
- Speech Rate / Syllable burst proxy
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple

from app.audio.preprocessing import PreprocessedAudio


@dataclass
class ProsodyAnalyzerConfig:
    """Configuration thresholds and parameters for prosodic anomaly evaluation."""
    sample_rate: int = 16000
    frame_length_ms: float = 25.0       # 25 ms frame (400 samples at 16kHz)
    frame_hop_ms: float = 10.0          # 10 ms hop (160 samples at 16kHz)
    min_f0_hz: float = 60.0             # Lowest pitch search boundary (lag = 266 samples)
    max_f0_hz: float = 500.0            # Highest pitch search boundary (lag = 32 samples)
    voicing_threshold: float = 0.40     # Autocorrelation peak threshold to consider a frame voiced
    energy_silence_db: float = -42.0    # Frame energy threshold for silence / pause classification

    # Normative human speech bounds for anomaly scoring
    min_natural_f0_cv: float = 0.08     # Below this is robotic / monotonic flatline
    max_natural_f0_cv: float = 0.45     # Above this is erratic pitch jitter
    min_natural_energy_std: float = 0.020  # Below this is unnatural energy flatness
    max_natural_hf_ratio: float = 0.50  # High-frequency vocoder phase distortion threshold
    max_natural_centroid_hz: float = 3600.0
    min_natural_syllable_rate: float = 1.0  # Syllables per second
    max_natural_syllable_rate: float = 7.5


@dataclass
class ProsodyAnalysisResult:
    """
    Standardized result structure for deterministic prosodic & acoustic anomaly analysis.
    """
    acoustic_anomaly: float              # Calibrated anomaly score in [0.0, 1.0]
    features: Dict[str, float]          # Numerical feature dictionary
    anomaly_reasons: List[str]          # Human-readable explainable diagnostic reasons
    status: str = "DETERMINISTIC_PROSODY_ANALYSIS"
    metadata: Dict[str, Any] = field(default_factory=dict)
    inference_time_ms: float = 0.0

    @property
    def prosody_reasons(self) -> List[str]:
        return self.anomaly_reasons

    @property
    def metrics(self) -> Dict[str, Any]:
        return self.features

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acoustic_anomaly": round(float(self.acoustic_anomaly), 4),
            "features": {k: round(float(v), 4) for k, v in self.features.items()},
            "anomaly_reasons": self.anomaly_reasons,
            "prosody_reasons": self.anomaly_reasons,
            "prosody_metrics": {k: round(float(v), 4) for k, v in self.features.items()},
            "status": self.status,
            "metadata": self.metadata,
            "inference_time_ms": round(float(self.inference_time_ms), 2),
        }


# Backward-compatible alias
ProsodyResult = ProsodyAnalysisResult


class ProsodyAnalyzer:
    """
    Deterministic Acoustic & Prosody Feature Extractor and Anomaly Evaluator.
    Extracts acoustic feature moments from 16kHz mono audio and computes an explainable anomaly score.
    """

    def __init__(
        self,
        config: Optional[ProsodyAnalyzerConfig] = None,
        sample_rate: int = 16000,
        **kwargs,
    ):
        if config is not None:
            self.config = config
        else:
            self.config = ProsodyAnalyzerConfig(sample_rate=sample_rate)

    def _frame_audio(self, waveform: List[float], frame_len: int, hop_len: int) -> List[List[float]]:
        """Slices 1D waveform into overlapping analysis frames."""
        frames = []
        n_samples = len(waveform)
        for i in range(0, n_samples - frame_len + 1, hop_len):
            frames.append(waveform[i : i + frame_len])
        if not frames and n_samples > 0:
            # Pad short audio to at least one frame
            padded = waveform + [0.0] * (frame_len - n_samples)
            frames.append(padded)
        return frames

    def _compute_frame_energy(self, frame: List[float]) -> float:
        """Calculates RMS energy for a single frame."""
        if not frame:
            return 0.0
        sum_sq = sum(x * x for x in frame)
        return math.sqrt(sum_sq / len(frame))

    def _compute_zcr(self, frame: List[float]) -> float:
        """Calculates zero-crossing rate for a single frame."""
        if len(frame) < 2:
            return 0.0
        crossings = 0
        for i in range(1, len(frame)):
            if (frame[i] >= 0 and frame[i - 1] < 0) or (frame[i] < 0 and frame[i - 1] >= 0):
                crossings += 1
        return crossings / (len(frame) - 1)

    def _estimate_f0_autocorr(
        self, frame: List[float], sr: int, min_lag: int, max_lag: int, voicing_thresh: float
    ) -> Tuple[Optional[float], float]:
        """
        Estimates fundamental frequency (F0) using Normalized Autocorrelation (NACF) with Hanning window.
        Returns:
            Tuple[Optional[float], float]: (F0_hz, peak_autocorr_score)
        """
        n = len(frame)
        if n < max_lag + 2:
            return None, 0.0

        # Apply Hanning window
        windowed = [
            frame[i] * 0.5 * (1.0 - math.cos(2.0 * math.pi * i / (n - 1)))
            for i in range(n)
        ]

        energy = sum(x * x for x in windowed)
        if energy < 1e-7:
            return None, 0.0

        # Autocorrelation for candidate pitch lags
        best_lag = -1
        best_r = -1.0

        for lag in range(min_lag, min(max_lag + 1, n)):
            r_val = sum(windowed[i] * windowed[i + lag] for i in range(n - lag))
            norm_factor = math.sqrt(energy * (sum(windowed[i + lag] ** 2 for i in range(n - lag)) + 1e-9))
            norm_r = r_val / max(1e-9, norm_factor)

            if norm_r > best_r:
                best_r = norm_r
                best_lag = lag

        if best_r >= voicing_thresh and best_lag > 0:
            f0_hz = sr / float(best_lag)
            return f0_hz, best_r

        return None, best_r

    def _compute_spectral_features(
        self, waveform: List[float], sr: int
    ) -> Tuple[float, float, float]:
        """
        Computes spectral centroid, spectral spread, and high-frequency energy ratio.
        Uses numpy if available, with pure Python fallback.
        """
        if not waveform:
            return 1500.0, 800.0, 0.1

        try:
            import numpy as np
            sig = np.array(waveform, dtype=np.float32)
            n_fft = min(2048, len(sig))
            if n_fft < 64:
                return 1500.0, 800.0, 0.1

            # Windowed FFT magnitude
            window = np.hanning(n_fft)
            sig_chunk = sig[:n_fft] * window
            mag = np.abs(np.fft.rfft(sig_chunk))
            freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

            total_mag = np.sum(mag) + 1e-9
            centroid = float(np.sum(freqs * mag) / total_mag)
            spread = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * mag) / total_mag))

            # High Frequency (> 4000 Hz) ratio
            hf_mask = freqs >= 4000.0
            hf_energy = float(np.sum(mag[hf_mask] ** 2))
            total_energy = float(np.sum(mag ** 2)) + 1e-9
            hf_ratio = hf_energy / total_energy

            return centroid, spread, hf_ratio

        except ImportError:
            # Pure Python approximation using first difference and zero-crossing spectral proxy
            n = len(waveform)
            diff_energy = sum((waveform[i] - waveform[i - 1]) ** 2 for i in range(1, n))
            total_energy = sum(x * x for x in waveform) + 1e-9
            hf_ratio = min(1.0, max(0.0, diff_energy / total_energy))
            centroid = 1000.0 + (hf_ratio * 3500.0)
            spread = 600.0 + (hf_ratio * 1200.0)
            return centroid, spread, hf_ratio

    def _estimate_syllable_rate(self, frame_energies: List[float], duration_sec: float) -> float:
        """
        Estimates speech rate / syllable burst count proxy from local smoothed energy peaks.
        """
        if duration_sec <= 0.1 or len(frame_energies) < 5:
            return 3.0  # Safe default conversational syllables/sec

        # Smooth frame energies with a 5-point moving average
        smoothed = []
        w_size = 5
        for i in range(len(frame_energies)):
            start_idx = max(0, i - w_size // 2)
            end_idx = min(len(frame_energies), i + w_size // 2 + 1)
            smoothed.append(sum(frame_energies[start_idx:end_idx]) / (end_idx - start_idx))

        mean_energy = sum(smoothed) / len(smoothed) if smoothed else 0.0
        peak_threshold = max(0.01, mean_energy * 0.7)

        # Count energy peaks with minimum separation
        peaks = 0
        min_dist_frames = 12  # ~120 ms minimum syllable separation
        last_peak = -min_dist_frames

        for i in range(1, len(smoothed) - 1):
            if (
                smoothed[i] > smoothed[i - 1]
                and smoothed[i] > smoothed[i + 1]
                and smoothed[i] >= peak_threshold
                and (i - last_peak) >= min_dist_frames
            ):
                peaks += 1
                last_peak = i

        return peaks / duration_sec

    def extract_features(self, audio: PreprocessedAudio) -> Dict[str, float]:
        """
        Extracts comprehensive numerical acoustic and prosodic feature metrics.
        """
        waveform = audio.waveform
        sr = audio.sample_rate
        duration_sec = max(0.01, audio.processed_duration_sec)

        frame_len = int(sr * (self.config.frame_length_ms / 1000.0))
        hop_len = int(sr * (self.config.frame_hop_ms / 1000.0))
        min_lag = max(1, int(sr / self.config.max_f0_hz))
        max_lag = min(frame_len - 2, int(sr / self.config.min_f0_hz))

        frames = self._frame_audio(waveform, frame_len, hop_len)

        frame_energies: List[float] = []
        frame_zcrs: List[float] = []
        f0_list: List[float] = []
        voiced_count = 0
        active_speech_count = 0

        silence_thresh_linear = math.pow(10.0, self.config.energy_silence_db / 20.0)

        for frame in frames:
            # Energy & ZCR
            rms = self._compute_frame_energy(frame)
            frame_energies.append(rms)
            zcr = self._compute_zcr(frame)
            frame_zcrs.append(zcr)

            if rms >= silence_thresh_linear:
                active_speech_count += 1

            # Pitch estimation
            if rms >= silence_thresh_linear * 1.5:
                f0_val, r_score = self._estimate_f0_autocorr(
                    frame, sr, min_lag, max_lag, self.config.voicing_threshold
                )
                if f0_val is not None:
                    f0_list.append(f0_val)
                    voiced_count += 1

        total_frames = max(1, len(frames))
        speech_ratio = active_speech_count / total_frames
        voicing_ratio = voiced_count / total_frames

        # F0 moments
        if len(f0_list) >= 3:
            mean_f0 = sum(f0_list) / len(f0_list)
            var_f0 = sum((x - mean_f0) ** 2 for x in f0_list) / len(f0_list)
            std_f0 = math.sqrt(var_f0)
            f0_cv = std_f0 / max(1.0, mean_f0)
            f0_min = min(f0_list)
            f0_max = max(f0_list)
            f0_range = f0_max - f0_min
        else:
            mean_f0 = 0.0
            std_f0 = 0.0
            f0_cv = 0.0
            f0_min = 0.0
            f0_max = 0.0
            f0_range = 0.0

        # Energy moments
        mean_energy = sum(frame_energies) / total_frames
        var_energy = sum((x - mean_energy) ** 2 for x in frame_energies) / total_frames
        std_energy = math.sqrt(var_energy)
        energy_cv = std_energy / max(1e-6, mean_energy)

        # ZCR moments
        mean_zcr = sum(frame_zcrs) / total_frames
        var_zcr = sum((x - mean_zcr) ** 2 for x in frame_zcrs) / total_frames
        std_zcr = math.sqrt(var_zcr)

        # Spectral features
        centroid, spread, hf_ratio = self._compute_spectral_features(waveform, sr)

        # Syllable rate proxy
        syllable_rate = self._estimate_syllable_rate(frame_energies, duration_sec)

        return {
            "f0_mean_hz": mean_f0,
            "f0_std_hz": std_f0,
            "f0_cv": f0_cv,
            "f0_min_hz": f0_min,
            "f0_max_hz": f0_max,
            "f0_range_hz": f0_range,
            "voicing_ratio": voicing_ratio,
            "speech_ratio": speech_ratio,
            "energy_mean": mean_energy,
            "energy_std": std_energy,
            "energy_cv": energy_cv,
            "zcr_mean": mean_zcr,
            "zcr_std": std_zcr,
            "spectral_centroid_hz": centroid,
            "spectral_spread_hz": spread,
            "hf_energy_ratio": hf_ratio,
            "syllable_rate_hz": syllable_rate,
            "duration_sec": duration_sec,
        }

    def analyze(self, audio: PreprocessedAudio) -> ProsodyAnalysisResult:
        """
        Runs deterministic prosodic feature extraction and evaluates an explainable anomaly score.
        """
        features = self.extract_features(audio)
        reasons: List[str] = []

        # 1. Pitch Anomaly (s_pitch)
        # Normal conversational speech has F0 CV around 0.12 - 0.35.
        # Monotonic flatline (< 0.08 with high voicing) or extreme pitch jitter (> 0.45) indicate unnatural speech.
        f0_cv = features["f0_cv"]
        voicing_ratio = features["voicing_ratio"]
        s_pitch = 0.0

        if voicing_ratio >= 0.25 and features["f0_mean_hz"] > 0:
            if f0_cv < self.config.min_natural_f0_cv:
                severity = min(1.0, (self.config.min_natural_f0_cv - f0_cv) / self.config.min_natural_f0_cv)
                s_pitch = max(s_pitch, 0.4 + 0.5 * severity)
                reasons.append(
                    f"Robotic monotone pitch contour with minimal F0 variation (CV = {f0_cv:.3f}, Std = {features['f0_std_hz']:.1f} Hz)"
                )
            elif f0_cv > self.config.max_natural_f0_cv:
                severity = min(1.0, (f0_cv - self.config.max_natural_f0_cv) / 0.30)
                s_pitch = max(s_pitch, 0.3 + 0.5 * severity)
                reasons.append(
                    f"Erratic pitch perturbation / fundamental frequency instability (CV = {f0_cv:.3f})"
                )

        # 2. Energy Dynamics Anomaly (s_energy)
        # Robotic synthesis often has unnaturally uniform frame energy (std < 0.020).
        energy_std = features["energy_std"]
        energy_mean = features["energy_mean"]
        s_energy = 0.0

        if energy_mean > 0.05:
            if energy_std < self.config.min_natural_energy_std:
                severity = min(1.0, (self.config.min_natural_energy_std - energy_std) / self.config.min_natural_energy_std)
                s_energy = 0.35 + 0.55 * severity
                reasons.append(
                    f"Unnatural acoustic energy flatness / lack of syllabic dynamics (Energy Std = {energy_std:.4f})"
                )

        # 3. Spectral Anomaly (s_spec)
        # Vocoders and phase concatenation often produce elevated high-frequency energy ratio or shifted centroid.
        hf_ratio = features["hf_energy_ratio"]
        centroid = features["spectral_centroid_hz"]
        s_spec = 0.0

        if hf_ratio > self.config.max_natural_hf_ratio:
            severity = min(1.0, (hf_ratio - self.config.max_natural_hf_ratio) / 0.35)
            s_spec = max(s_spec, 0.3 + 0.6 * severity)
            reasons.append(
                f"Elevated high-frequency energy ratio indicative of vocoder artifacts (HF Ratio = {hf_ratio:.3f})"
            )

        if centroid > self.config.max_natural_centroid_hz:
            s_spec = max(s_spec, min(0.8, (centroid - self.config.max_natural_centroid_hz) / 1500.0))
            reasons.append(
                f"Unusual spectral centroid elevation ({centroid:.0f} Hz > {self.config.max_natural_centroid_hz:.0f} Hz)"
            )

        # 4. Speech/Pause Rhythm Anomaly (s_pause)
        # Human speech contains natural breathing pauses. Speech ratio > 0.98 in long audio or extreme fragmentation.
        speech_ratio = features["speech_ratio"]
        duration = features["duration_sec"]
        s_pause = 0.0

        if duration >= 2.5 and speech_ratio > 0.98:
            s_pause = 0.4
            reasons.append(
                f"Absence of natural pauses / continuous vocalization ({speech_ratio * 100:.1f}% active speech over {duration:.1f}s)"
            )

        # 5. Syllable Rate Anomaly (s_rate)
        syllable_rate = features["syllable_rate_hz"]
        s_rate = 0.0

        if duration >= 1.5 and (syllable_rate < self.config.min_natural_syllable_rate or syllable_rate > self.config.max_natural_syllable_rate):
            s_rate = 0.35
            reasons.append(
                f"Atypical speech rhythm / syllable rate proxy ({syllable_rate:.1f} syllables/sec)"
            )

        # Fusion of individual acoustic anomaly sub-scores
        # Weights: Pitch = 0.35, Energy = 0.25, Spectral = 0.20, Pause = 0.10, Rate = 0.10
        raw_anomaly = (
            (0.35 * s_pitch)
            + (0.25 * s_energy)
            + (0.20 * s_spec)
            + (0.10 * s_pause)
            + (0.10 * s_rate)
        )

        # Non-linear boost if multiple distinct anomaly signals co-occur
        active_subsignals = sum(1 for s in [s_pitch, s_energy, s_spec, s_pause, s_rate] if s > 0.3)
        if active_subsignals >= 2:
            raw_anomaly = min(1.0, raw_anomaly * 1.25 + 0.10)

        # Natural clean speech typically achieves 0.0 - 0.20
        calibrated_anomaly = round(max(0.0, min(1.0, raw_anomaly)), 4)

        return ProsodyAnalysisResult(
            acoustic_anomaly=calibrated_anomaly,
            features=features,
            anomaly_reasons=reasons,
            status="DETERMINISTIC_PROSODY_ANALYSIS",
            metadata={
                "method": "Multi-Feature Acoustic/Prosody Moments (F0, Energy, ZCR, Spectral, Syllable)",
                "sample_rate": audio.sample_rate,
                "duration_sec": audio.processed_duration_sec,
                "voiced_frames_evaluated": int(features["voicing_ratio"] * len(audio.waveform) / (audio.sample_rate * 0.01)),
            },
        )
