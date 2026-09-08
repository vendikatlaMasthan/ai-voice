"""
Universal Audio Ingestion Pipeline for VoiceShield AI.

Canonical rule:
EVERY code path that receives audio (upload, mic recording, quality check,
or preprocessing) MUST call this single shared conversion function first.
Converts any incoming audio format (WebM, Opus, MP3, WAV, M4A, FLAC, OGG, AAC)
into 16kHz mono float32 PCM via FFmpeg.
No other code in the backend touches raw upload or recording bytes.
"""

import logging
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger("VoiceShield.AudioIngestion")

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


class AudioIngestionError(Exception):
    """Base exception for audio ingestion and decoding issues."""
    pass


class CorruptAudioError(AudioIngestionError):
    """Raised when audio bytes cannot be decoded or are corrupt."""
    pass


def convert_and_decode_to_16k_mono(
    audio_input: Union[str, Path, bytes, BinaryIO],
    original_filename: Optional[str] = None,
    keep_wav_file: bool = False,
) -> Tuple[np.ndarray, int, Optional[str]]:
    """
    Universal ingestion function for all VoiceShield audio.
    
    Args:
        audio_input: File path, bytes, or file-like binary stream.
        original_filename: Optional filename hint for temporary file extension.
        keep_wav_file: If True, persists the converted .wav file and returns its path.
                       The caller is responsible for cleaning it up when done.

    Returns:
        Tuple of:
            - waveform: 1D np.ndarray (float32, normalized to [-1.0, 1.0])
            - sample_rate: int (always 16000)
            - wav_path: Optional[str] (path to converted 16kHz mono WAV file if keep_wav_file=True)

    Raises:
        CorruptAudioError: If decoding fails or audio stream is invalid.
    """
    temp_dir = tempfile.mkdtemp(prefix="voiceshield_ingest_")
    input_tmp_path: Optional[str] = None
    output_wav_path: Optional[str] = None

    try:
        # 1. Materialize input bytes to a temporary file if not already a valid existing path
        if isinstance(audio_input, (str, Path)) and os.path.exists(str(audio_input)):
            input_tmp_path = str(audio_input)
        else:
            ext = ".tmp"
            if original_filename:
                ext = Path(original_filename).suffix or ".tmp"
            
            with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=ext, delete=False) as f_in:
                input_tmp_path = f_in.name
                if isinstance(audio_input, bytes):
                    f_in.write(audio_input)
                elif hasattr(audio_input, "read"):
                    shutil.copyfileobj(audio_input, f_in)
                else:
                    raise CorruptAudioError("Invalid audio input provided to ingestion pipeline.")
                f_in.flush()

        if not os.path.exists(input_tmp_path) or os.path.getsize(input_tmp_path) == 0:
            raise CorruptAudioError("Audio file is empty or could not be saved.")

        # 2. Convert via FFmpeg to 16kHz mono s16le PCM
        output_wav_path = os.path.join(temp_dir, "standardized_16k_mono.wav")
        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-v", "error",
            "-i", input_tmp_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", str(TARGET_CHANNELS),
            "pipe:1",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            raw_pcm, err_bytes = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise CorruptAudioError("Audio decoding timed out.")
        except FileNotFoundError:
            raise AudioIngestionError("FFmpeg binary is missing on the system PATH.")

        if proc.returncode != 0 or len(raw_pcm) < 2:
            err_msg = err_bytes.decode("utf-8", errors="ignore").strip()
            logger.error(f"FFmpeg decode failed with exit code {proc.returncode}: {err_msg}")
            raise CorruptAudioError(f"We couldn't decode this audio. Please verify the file format.")

        # 3. Parse raw PCM s16le bytes into float32 numpy array
        waveform = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0

        if len(waveform) == 0:
            raise CorruptAudioError("Decoded audio stream contains 0 samples.")

        # 4. If caller requested a standard WAV file on disk (for APIs like Reality Defender)
        final_wav_path = None
        if keep_wav_file:
            # Generate valid standard WAV file header + PCM
            import wave
            final_wav_dir = tempfile.mkdtemp(prefix="vs_standard_wav_")
            final_wav_path = os.path.join(final_wav_dir, "standard_16k.wav")
            pcm_ints = (waveform * 32767.0).clip(-32768, 32767).astype(np.int16)
            with wave.open(final_wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(TARGET_SAMPLE_RATE)
                wf.writeframes(pcm_ints.tobytes())

        return waveform, TARGET_SAMPLE_RATE, final_wav_path

    finally:
        # Clean up temporary directory (excluding final_wav_path if persisted)
        shutil.rmtree(temp_dir, ignore_errors=True)
