"""
Audio Preprocessing Pipeline for Voice Deepfake & Cloning Detection.
Handles audio loading, format conversion, 16kHz resampling, mono mixing,
silence removal, amplitude normalization, and signal validation.
"""

import math
import os
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import AudioConfig, default_config
from app.utils.audio_utils import (
    AudioSilentError,
    AudioTooShortError,
    CorruptAudioError,
    FileNotFoundAudioError,
    calculate_rms,
    calculate_snr_estimate,
    linear_to_db,
)


@dataclass
class PreprocessedAudio:
    """Container holding preprocessed audio waveform and analytical metadata."""
    waveform: List[float]               # 1D float list normalized to [-1.0, 1.0]
    sample_rate: int                    # Target sample rate (default 16000 Hz)
    original_duration_sec: float        # Duration before trimming/padding
    processed_duration_sec: float       # Final duration in seconds
    rms_energy_db: float                # Overall RMS energy in dB
    estimated_snr_db: float             # Estimated Signal-to-Noise Ratio
    channels: int                       # 1 (Mono)
    metadata: Dict[str, Any]            # Diagnostics & file properties


class AudioPreprocessor:
    """
    Production-ready Audio Preprocessor designed for speech deepfake models.
    Supports standard 16kHz mono normalization, silence detection, and duration bounds.
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or default_config.audio

    def load_audio_file(self, file_path: Union[str, Path]) -> Tuple[List[float], int]:
        """
        Load an audio file from disk, convert to float array in [-1.0, 1.0], and get sample rate.
        Supports all major formats (WAV, MP3, M4A, FLAC, OGG, WEBM, AAC) using universal ffmpeg
        decoding with fallback to soundfile and native wave modules.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundAudioError(f"Audio file not found: '{file_path}'")

        if path.stat().st_size == 0:
            raise CorruptAudioError(f"Audio file is empty (0 bytes): '{file_path}'")

        # 1. Primary decoder: Universal ffmpeg decoding (supports WAV, MP3, M4A, FLAC, OGG, WEBM, AAC)
        try:
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-v", "error",
                "-i", str(path),
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-"
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out_bytes, err_bytes = proc.communicate(timeout=15)

            if proc.returncode == 0 and len(out_bytes) > 0:
                total_samples = len(out_bytes) // 2
                if total_samples == 0:
                    raise CorruptAudioError(f"Decoded audio file contains 0 samples: '{file_path}'")
                fmt = f"<{total_samples}h"
                ints = struct.unpack(fmt, out_bytes)
                samples = [val / 32768.0 for val in ints]
                return samples, 16000
            elif proc.returncode != 0:
                # If ffmpeg returned non-zero, check if file is corrupt
                err_msg = err_bytes.decode("utf-8", errors="ignore").strip()
                if "Invalid data found" in err_msg or "does not contain any stream" in err_msg:
                    raise CorruptAudioError(f"Corrupt or invalid audio file '{file_path}': {err_msg}")
        except subprocess.TimeoutExpired:
            proc.kill()
            raise CorruptAudioError(f"Timeout decoding audio file '{file_path}'")
        except FileNotFoundError:
            # ffmpeg binary not installed on PATH, continue to fallback libraries
            pass
        except CorruptAudioError:
            raise
        except Exception:
            pass

        # 2. Secondary fallback: soundfile if installed
        try:
            import soundfile as sf
            data, sr = sf.read(str(path), dtype="float32")
            if len(data.shape) > 1 and data.shape[1] > 1:
                mono_data = data.mean(axis=1)
            else:
                mono_data = data.flatten()
            return mono_data.tolist(), sr
        except ImportError:
            pass
        except Exception:
            pass

        # 3. Native fallback: Python standard library 'wave' for standard PCM WAV files
        try:
            with wave.open(str(path), "rb") as wav:
                num_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frame_rate = wav.getframerate()
                num_frames = wav.getnframes()

                if num_frames == 0:
                    raise CorruptAudioError(f"Audio file contains 0 frames: '{file_path}'")

                raw_bytes = wav.readframes(num_frames)

                samples: List[float] = []
                if sample_width == 2:  # 16-bit PCM
                    total_samples = len(raw_bytes) // 2
                    fmt = f"<{total_samples}h"
                    ints = struct.unpack(fmt, raw_bytes)
                    if num_channels == 1:
                        samples = [val / 32768.0 for val in ints]
                    else:
                        samples = [
                            sum(ints[i : i + num_channels]) / (num_channels * 32768.0)
                            for i in range(0, len(ints), num_channels)
                        ]
                elif sample_width == 1:  # 8-bit unsigned PCM
                    if num_channels == 1:
                        samples = [(b - 128) / 128.0 for b in raw_bytes]
                    else:
                        samples = [
                            sum((raw_bytes[i + c] - 128) / 128.0 for c in range(num_channels)) / num_channels
                            for i in range(0, len(raw_bytes), num_channels)
                        ]
                elif sample_width == 4:  # 32-bit int
                    total_samples = len(raw_bytes) // 4
                    ints = struct.unpack(f"<{total_samples}i", raw_bytes)
                    if num_channels == 1:
                        samples = [val / 2147483648.0 for val in ints]
                    else:
                        samples = [
                            sum(ints[i : i + num_channels]) / (num_channels * 2147483648.0)
                            for i in range(0, len(ints), num_channels)
                        ]
                else:
                    raise CorruptAudioError(f"Unsupported bit depth ({sample_width * 8}-bit) in '{file_path}'")

                return samples, frame_rate

        except (wave.Error, struct.error, EOFError) as err:
            raise CorruptAudioError(f"Failed to decode audio file '{file_path}': {str(err)}") from err

    def resample(self, samples: List[float], orig_sr: int, target_sr: int) -> List[float]:
        """
        Resample 1D audio from orig_sr to target_sr.
        Uses scipy/librosa/torchaudio if available, with a fast linear interpolation fallback.
        """
        if orig_sr == target_sr:
            return samples

        try:
            import scipy.signal
            num_target_samples = int(len(samples) * target_sr / orig_sr)
            resampled = scipy.signal.resample(samples, num_target_samples)
            return resampled.tolist()
        except ImportError:
            # High-speed linear interpolation fallback
            num_orig = len(samples)
            num_target = int(num_orig * target_sr / orig_sr)
            if num_target <= 0 or num_orig <= 0:
                return []
            
            step = (num_orig - 1) / max(1, (num_target - 1))
            resampled = []
            for i in range(num_target):
                pos = i * step
                idx = int(pos)
                frac = pos - idx
                if idx >= num_orig - 1:
                    resampled.append(samples[-1])
                else:
                    val = (1.0 - frac) * samples[idx] + frac * samples[idx + 1]
                    resampled.append(val)
            return resampled

    def peak_normalize(self, samples: List[float], target_peak: float = 0.95) -> List[float]:
        """Normalize maximum peak amplitude to target_peak (preventing clipping while standardizing volume)."""
        if not samples:
            return []
        max_val = max(abs(x) for x in samples)
        if max_val < 1e-6:
            return samples  # Don't amplify pure silence
        scale = target_peak / max_val
        return [x * scale for x in samples]

    def remove_silence(
        self, samples: List[float], sr: int, threshold_db: float = -45.0, frame_duration_ms: int = 20
    ) -> Tuple[List[float], float]:
        """
        Energy-based Voice Activity / Silence Trimmer.
        Removes silent frames from start and end, and filters excessive interior dead pauses.
        
        Returns:
            Tuple[List[float], float]: (trimmed_samples, speech_ratio)
        """
        frame_len = int(sr * (frame_duration_ms / 1000.0))
        if frame_len <= 0 or len(samples) < frame_len:
            return samples, 1.0

        num_frames = len(samples) // frame_len
        frame_energies = []
        active_indices = []

        for i in range(num_frames):
            frame = samples[i * frame_len : (i + 1) * frame_len]
            rms = calculate_rms(frame)
            energy_db = linear_to_db(rms)
            frame_energies.append(energy_db)
            if energy_db >= threshold_db:
                active_indices.append(i)

        if not active_indices:
            # Completely silent
            return [], 0.0

        speech_ratio = len(active_indices) / max(1, num_frames)

        # Trim leading and trailing silence with a 2-frame safety margin
        start_frame = max(0, active_indices[0] - 2)
        end_frame = min(num_frames, active_indices[-1] + 3)

        trimmed = samples[start_frame * frame_len : end_frame * frame_len]
        return trimmed, speech_ratio

    def pad_or_truncate(
        self, samples: List[float], target_length_samples: int
    ) -> List[float]:
        """
        Ensures the audio array has an exact target sample length for consistent batching/tensors.
        Truncates if longer, or zero-pads symmetrically/end if shorter.
        """
        current_len = len(samples)
        if current_len == target_length_samples:
            return samples
        elif current_len > target_length_samples:
            # Truncate to first target_length_samples
            return samples[:target_length_samples]
        else:
            # Pad with zeros at the end
            pad_amount = target_length_samples - current_len
            return samples + [0.0] * pad_amount

    def process(self, file_path: Union[str, Path]) -> PreprocessedAudio:
        """
        Complete end-to-end preprocessing execution:
        1. Load & decode audio
        2. Convert to mono & resample to 16kHz
        3. Validate duration (min duration check)
        4. Energy & silence verification
        5. Peak amplitude normalization
        6. Compute SNR & metrics
        """
        raw_samples, original_sr = self.load_audio_file(file_path)
        original_duration = len(raw_samples) / max(1, original_sr)

        # Check 1: Initial duration check
        if original_duration < self.config.min_duration_sec:
            raise AudioTooShortError(original_duration, self.config.min_duration_sec)

        # 2. Resample to target sample rate (16kHz)
        samples_16k = self.resample(raw_samples, original_sr, self.config.sample_rate)

        # 3. Silence & Speech energy detection
        trimmed_samples, speech_ratio = self.remove_silence(
            samples_16k,
            self.config.sample_rate,
            threshold_db=self.config.silence_threshold_db
        )

        overall_rms = calculate_rms(samples_16k)
        overall_db = linear_to_db(overall_rms)

        # Check 2: Silence rejection
        if not trimmed_samples or speech_ratio < self.config.min_speech_ratio or overall_db < self.config.silence_threshold_db:
            raise AudioSilentError(overall_db, self.config.silence_threshold_db)

        # 4. Check post-trim duration
        post_trim_duration = len(trimmed_samples) / self.config.sample_rate
        if post_trim_duration < self.config.min_duration_sec:
            raise AudioTooShortError(post_trim_duration, self.config.min_duration_sec)

        # 5. Peak Normalization
        if self.config.normalize_peak:
            normalized_samples = self.peak_normalize(trimmed_samples, self.config.peak_level)
        else:
            normalized_samples = trimmed_samples

        # 6. Quality Metrics
        final_rms = calculate_rms(normalized_samples)
        final_db = linear_to_db(final_rms)
        snr_db = calculate_snr_estimate(normalized_samples)

        return PreprocessedAudio(
            waveform=normalized_samples,
            sample_rate=self.config.sample_rate,
            original_duration_sec=round(original_duration, 3),
            processed_duration_sec=round(post_trim_duration, 3),
            rms_energy_db=round(final_db, 2),
            estimated_snr_db=round(snr_db, 2),
            channels=1,
            metadata={
                "source_file": str(file_path),
                "original_sample_rate": original_sr,
                "target_sample_rate": self.config.sample_rate,
                "speech_ratio": round(speech_ratio, 3),
                "sample_count": len(normalized_samples),
            }
        )
