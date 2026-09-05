"""
Audio utilities: validation, metrics, synthetic test audio generation, and custom exceptions.
Designed to be robust and self-contained with minimal external dependencies.
"""

import math
import os
import struct
import wave
from pathlib import Path
from typing import List, Tuple, Union


# ==========================================
# Custom Audio Domain Exceptions
# ==========================================

class AudioError(Exception):
    """Base exception for all audio processing errors."""
    pass


class FileNotFoundAudioError(AudioError):
    """Raised when the requested audio file does not exist."""
    pass


class CorruptAudioError(AudioError):
    """Raised when an audio file cannot be decoded or has an invalid header."""
    pass


class AudioTooShortError(AudioError):
    """Raised when the audio duration is below the minimum required length."""
    def __init__(self, duration_sec: float, min_required_sec: float):
        super().__init__(
            f"Audio duration {duration_sec:.2f}s is too short. Minimum required is {min_required_sec:.2f}s."
        )
        self.duration_sec = duration_sec
        self.min_required_sec = min_required_sec


class AudioTooLongError(AudioError):
    """Raised when the audio duration exceeds the maximum limit."""
    def __init__(self, duration_sec: float, max_allowed_sec: float):
        super().__init__(
            f"Audio duration {duration_sec:.2f}s exceeds maximum allowed {max_allowed_sec:.2f}s."
        )
        self.duration_sec = duration_sec
        self.max_allowed_sec = max_allowed_sec


class AudioSilentError(AudioError):
    """Raised when the audio has insufficient energy (silence or background hum only)."""
    def __init__(self, energy_db: float, threshold_db: float):
        super().__init__(
            f"Audio energy {energy_db:.2f} dB is below speech threshold {threshold_db:.2f} dB. No usable speech detected."
        )
        self.energy_db = energy_db
        self.threshold_db = threshold_db


# Compatibility aliases
AudioCorruptError = CorruptAudioError
UnsupportedFormatError = CorruptAudioError


# ==========================================
# Audio Metric & Signal Calculations
# ==========================================

def calculate_rms(samples: Union[List[float], Tuple[float, ...]]) -> float:
    """
    Calculate the Root Mean Square (RMS) amplitude of audio samples.
    
    Args:
        samples: Sequence of float samples normalized to [-1.0, 1.0].
        
    Returns:
        float: RMS energy in linear scale [0.0, 1.0].
    """
    if not samples:
        return 0.0
    sum_squares = sum(x * x for x in samples)
    return math.sqrt(sum_squares / len(samples))


def linear_to_db(value: float, eps: float = 1e-9) -> float:
    """Convert linear amplitude or energy to decibels (dB)."""
    safe_val = max(value, eps)
    return 20.0 * math.log10(safe_val)


def calculate_snr_estimate(samples: List[float], noise_floor_percentile: float = 0.10) -> float:
    """
    Estimate Signal-to-Noise Ratio (SNR) in dB using a simple energy quantile estimation.
    Useful for filtering out poor-quality microphone captures.
    
    Args:
        samples: List of audio samples.
        noise_floor_percentile: Fraction of lowest-energy frames treated as noise floor.
        
    Returns:
        float: Estimated SNR in dB.
    """
    if not samples or len(samples) < 320:
        return 0.0
    
    # Calculate energy in 20ms frames (assuming ~16kHz, frame size = 320)
    frame_size = 320
    num_frames = len(samples) // frame_size
    if num_frames == 0:
        return 0.0
    
    frame_energies = []
    for i in range(num_frames):
        chunk = samples[i * frame_size : (i + 1) * frame_size]
        rms = calculate_rms(chunk)
        frame_energies.append(rms)
    
    frame_energies.sort()
    
    # Noise floor from lowest percentile
    noise_count = max(1, int(num_frames * noise_floor_percentile))
    noise_energy = sum(frame_energies[:noise_count]) / noise_count
    
    # Signal energy from upper half
    signal_count = max(1, num_frames // 2)
    signal_energy = sum(frame_energies[-signal_count:]) / signal_count
    
    if noise_energy < 1e-7:
        return 40.0  # High clarity limit
    
    snr_db = 20.0 * math.log10(signal_energy / (noise_energy + 1e-9))
    return max(0.0, min(snr_db, 60.0))


# ==========================================
# Synthetic Test Audio File Generator
# ==========================================

def generate_synthetic_tone(
    frequency: float = 440.0,
    duration_sec: float = 2.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> List[float]:
    """Generates an in-memory synthetic sine wave for fast testing."""
    total_samples = int(duration_sec * sample_rate)
    samples: List[float] = []
    for i in range(total_samples):
        t = i / sample_rate
        samples.append(amplitude * math.sin(2.0 * math.pi * frequency * t))
    return samples


def generate_test_wav(
    output_path: Union[str, Path],
    duration_sec: float = 3.0,
    sample_rate: int = 16000,
    sample_type: str = "speech_like"
) -> Path:
    """
    Generates deterministic, synthetic WAV files using pure standard library (wave + struct).
    Allows automated testing of audio loaders and validators without requiring large audio datasets.
    
    Supported sample_types:
        - 'speech_like': Multi-harmonic modulated sine waves simulating human vowel formants (F0=140Hz + harmonics).
        - 'silence': Pure zero-energy audio to test silence rejection.
        - 'low_energy': Very quiet background hiss (-60 dB).
        - 'short': 0.2-second chirp to test minimum duration rejection.
        - 'clipping': High-amplitude signal to test normalization.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    total_samples = int(duration_sec * sample_rate)
    samples: List[float] = []
    
    if sample_type == "silence":
        samples = [0.0] * total_samples
        
    elif sample_type == "low_energy":
        # -60 dB amplitude (~0.001)
        amp = 0.0005
        for i in range(total_samples):
            t = i / sample_rate
            samples.append(amp * math.sin(2.0 * math.pi * 440.0 * t))
            
    elif sample_type == "short":
        short_samples = int(0.2 * sample_rate)
        for i in range(short_samples):
            t = i / sample_rate
            samples.append(0.5 * math.sin(2.0 * math.pi * 300.0 * t))
            
    elif sample_type == "speech_like":
        # Formant synthesis: Fundamental frequency F0 = 130 Hz (typical male/neutral speech),
        # F1 = 500 Hz, F2 = 1500 Hz, F3 = 2500 Hz, with amplitude modulation (prosody rhythm).
        for i in range(total_samples):
            t = i / sample_rate
            # 3 Hz envelope rhythm (simulates syllable pauses)
            envelope = 0.5 * (1.0 + math.sin(2.0 * math.pi * 3.0 * t))
            # Harmonic stack
            f0 = math.sin(2.0 * math.pi * 130.0 * t) * 0.4
            f1 = math.sin(2.0 * math.pi * 500.0 * t) * 0.25
            f2 = math.sin(2.0 * math.pi * 1500.0 * t) * 0.15
            f3 = math.sin(2.0 * math.pi * 2500.0 * t) * 0.05
            
            raw_sample = (f0 + f1 + f2 + f3) * envelope
            samples.append(raw_sample)
            
    elif sample_type == "clipping":
        for i in range(total_samples):
            t = i / sample_rate
            val = 2.5 * math.sin(2.0 * math.pi * 220.0 * t)
            # Clipped
            samples.append(max(-1.0, min(1.0, val)))
    else:
        # Default pure 440 Hz tone
        for i in range(total_samples):
            t = i / sample_rate
            samples.append(0.5 * math.sin(2.0 * math.pi * 440.0 * t))

    # Write standard 16-bit PCM WAV
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)       # Mono
        wav_file.setsampwidth(2)      # 16-bit PCM (2 bytes per sample)
        wav_file.setframerate(sample_rate)
        
        packed_frames = bytearray()
        for s in samples:
            # Clamp to [-1.0, 1.0] and convert to 16-bit int [-32768, 32767]
            clamped = max(-1.0, min(1.0, s))
            int_val = int(clamped * 32767.0)
            packed_frames.extend(struct.pack("<h", int_val))
            
        wav_file.writeframes(packed_frames)
        
    return output_path
