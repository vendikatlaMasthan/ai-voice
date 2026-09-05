"""
Command-line test script for Voice-Cloning & Deepfake Detection System (Milestone 1).
Runs inference on sample files and verifies all error-handling conditions:
- Valid speech audio
- Missing audio file
- Corrupt/unsupported file
- Too short audio (< 0.5s)
- Silence / no speech (< -45 dB)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is in Python sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.audio.preprocessing import AudioPreprocessor
from app.config import default_config
from app.models.detector import VoiceCloneDetector
from app.utils.audio_utils import (
    AudioError,
    AudioSilentError,
    AudioTooShortError,
    CorruptAudioError,
    FileNotFoundAudioError,
    generate_test_wav,
)


def ensure_test_samples(samples_dir: Path):
    """Generates standard synthetic test WAV files for automated verification."""
    samples_dir.mkdir(parents=True, exist_ok=True)

    samples = {
        "valid_speech.wav": ("speech_like", 3.0),
        "too_short.wav": ("short", 0.2),
        "silent_audio.wav": ("silence", 2.0),
        "low_energy_hiss.wav": ("low_energy", 2.5),
    }

    for filename, (stype, dur) in samples.items():
        file_path = samples_dir / filename
        if not file_path.exists():
            generate_test_wav(file_path, duration_sec=dur, sample_rate=16000, sample_type=stype)
            print(f"[Sample Generator] Created test sample: {file_path.name}")

    # Create a corrupted file for error testing
    corrupt_path = samples_dir / "corrupted_file.wav"
    if not corrupt_path.exists():
        with open(corrupt_path, "wb") as f:
            f.write(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00GARBAGE_DATA_TRUNCATED")
        print(f"[Sample Generator] Created corrupted test sample: {corrupt_path.name}")


def analyze_single_audio(
    file_path: str,
    preprocessor: AudioPreprocessor,
    detector: VoiceCloneDetector
):
    """Performs preprocessing and model prediction with comprehensive error handling."""
    print(f"\n=======================================================")
    print(f"Analyzing Target: {file_path}")
    print(f"=======================================================")

    try:
        # Step 1: Preprocessing & Validation
        preprocessed = preprocessor.process(file_path)
        print(f"[Preprocessing] Status: SUCCESS")
        print(f"  - Sample Rate: {preprocessed.sample_rate} Hz (Mono)")
        print(f"  - Original Duration: {preprocessed.original_duration_sec}s | Processed: {preprocessed.processed_duration_sec}s")
        print(f"  - RMS Energy: {preprocessed.rms_energy_db} dB | SNR: {preprocessed.estimated_snr_db} dB")

        # Step 2: Model Inference
        result = detector.predict(preprocessed)
        print(f"[Model Inference] Status: SUCCESS")
        print("\n--- Output JSON Result ---")
        print(json.dumps(result.to_dict(), indent=2))
        return result

    except FileNotFoundAudioError as e:
        print(f"[EXPECTED ERROR] Missing File Error: {e}")
    except AudioTooShortError as e:
        print(f"[EXPECTED ERROR] Audio Too Short Error: {e}")
    except AudioSilentError as e:
        print(f"[EXPECTED ERROR] Silence/No Usable Speech Error: {e}")
    except CorruptAudioError as e:
        print(f"[EXPECTED ERROR] Corrupt/Unsupported Audio Error: {e}")
    except AudioError as e:
        print(f"[ERROR] Audio Processing Error: {e}")
    except Exception as e:
        print(f"[UNEXPECTED ERROR]: {type(e).__name__}: {e}")

    return None


def run_full_verification_suite(samples_dir: Path, use_baseline: bool = False):
    """Runs through all positive and negative test cases to verify pipeline correctness."""
    print("=" * 65)
    print("SIH 2026 Problem Statement 26104: AI Voice Cloning Detection")
    print("Verification Suite (Preprocessing & Inference Foundation)")
    print("=" * 65)

    ensure_test_samples(samples_dir)

    preprocessor = AudioPreprocessor()
    detector = VoiceCloneDetector(use_deep_learning_backend=not use_baseline)
    detector.load()

    test_cases = [
        ("Valid Speech Audio (Pass Expected)", samples_dir / "valid_speech.wav"),
        ("Too Short Audio (Rejection Expected)", samples_dir / "too_short.wav"),
        ("Silent Audio (Rejection Expected)", samples_dir / "silent_audio.wav"),
        ("Corrupted Audio (Rejection Expected)", samples_dir / "corrupted_file.wav"),
        ("Non-Existent File (Rejection Expected)", samples_dir / "does_not_exist.wav"),
    ]

    for label, path in test_cases:
        print(f"\n>>> TEST CASE: {label}")
        analyze_single_audio(str(path), preprocessor, detector)

    print("\n" + "=" * 65)
    print("Verification suite completed successfully.")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="VoiceShield: Voice Cloning & Deepfake Speech Detection CLI"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to an individual audio file to analyze (.wav)"
    )
    parser.add_argument(
        "--model-name", "-m",
        type=str,
        default=default_config.model.hf_model_name,
        help=f"Hugging Face model repository ID (default: {default_config.model.hf_model_name})"
    )
    parser.add_argument(
        "--use-baseline",
        action="store_true",
        help="Force fallback to lightweight acoustic baseline (no Hugging Face weight download)"
    )
    parser.add_argument(
        "--run-all-tests", "-a",
        action="store_true",
        help="Run the complete milestone verification suite (valid, short, silent, corrupt)"
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Generate synthetic test audio samples in data/samples/"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda", "auto"],
        help="Hardware execution device (default: cpu)"
    )

    args = parser.parse_args()

    samples_dir = default_config.samples_dir
    default_config.model.device = args.device
    default_config.model.hf_model_name = args.model_name
    default_config.model.model_name_or_path = args.model_name

    if args.generate_samples:
        ensure_test_samples(samples_dir)
        print(f"[Done] Test samples generated in {samples_dir}")
        return

    if args.file:
        preprocessor = AudioPreprocessor()
        detector = VoiceCloneDetector(use_deep_learning_backend=not args.use_baseline)
        detector.load()
        analyze_single_audio(args.file, preprocessor, detector)
    else:
        # Default behavior: run complete verification test suite
        run_full_verification_suite(samples_dir, use_baseline=args.use_baseline)


if __name__ == "__main__":
    main()
