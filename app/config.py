"""
Configuration Module for Voice-Cloning Detection System.
Centralizes all audio parameters, model paths, and hardware acceleration settings.
Designed for lightweight execution on Windows 11 / 8GB RAM / NVIDIA MX450 GPU or CPU.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AudioConfig:
    """Audio preprocessing and feature extraction parameters."""
    sample_rate: int = 16000          # 16 kHz is standard for Wav2Vec2 / WavLM / Whisper
    channels: int = 1                 # Mono audio
    min_duration_sec: float = 0.5     # Minimum audio duration (reject shorter)
    max_duration_sec: float = 30.0    # Maximum input audio length
    target_duration_sec: float = 4.0  # Normalized evaluation window length (pad/trim to this)
    silence_threshold_db: float = -45.0  # Threshold below which audio is classified as silent
    min_speech_ratio: float = 0.15    # Minimum fraction of non-silent frames required
    normalize_peak: bool = True       # Apply peak normalization to [-0.95, +0.95]
    peak_level: float = 0.95


@dataclass
class ModelConfig:
    """Model inference and hardware execution parameters."""
    # Pretrained Hugging Face audio classification model explicitly fine-tuned for deepfake voice detection
    # Primary: "garystafford/wav2vec2-deepfake-voice-detector" (Wav2Vec2 fine-tuned on modern TTS/cloned speech)
    # Alternative: "MelodyMachine/Deepfake-audio-detection-V2"
    hf_model_name: str = "garystafford/wav2vec2-deepfake-voice-detector"
    
    # Path to local checkpoint or Hugging Face repo ID
    model_name_or_path: str = "garystafford/wav2vec2-deepfake-voice-detector"
    fine_tuned_weights_path: Optional[str] = None
    
    # Execution device: 'cpu' by default; 'cuda' or 'auto' activates NVIDIA GPU only when safely available
    device: str = "cpu"
    
    # Memory optimization for 8GB RAM / MX450 (2GB VRAM)
    use_fp16: bool = False             # Set True for CUDA if GPU supports FP16 inference
    batch_size: int = 1                # Single-sample inference for low VRAM
    max_inference_length_samples: int = 16000 * 10  # 10 seconds maximum chunk for transformer memory
    
    # Classification decision boundary
    decision_threshold: float = 0.5   # Fake probability >= threshold -> "FAKE"


@dataclass
class AppConfig:
    """Root Application Configuration."""
    audio: AudioConfig = field(default_factory=AudioConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    
    # Base filesystem paths
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    samples_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "samples")
    cache_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / ".cache")

    def __post_init__(self):
        # Create directories if they do not exist
        os.makedirs(self.samples_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)


# Global default configuration instance
default_config = AppConfig()
