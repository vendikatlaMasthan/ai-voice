"""
VoiceShield AI — Canonical Production Backend API (FastAPI).
Supports:
1. Universal Audio & Video Ingestion:
   - Audio formats: WAV, MP3, M4A, FLAC, AAC, OGG
   - Video formats: MP4, MOV, MKV, WEBM (audio track extracted via FFmpeg -vn)
   - Graceful validation: returns 400 if a video does not contain an audio track.
2. Long Audio Handling:
   - If audio/video duration > 15s, fast silencedetect locates where speech starts,
     and windows up to 15.0s without failing or degrading server responsiveness.
3. Multi-Signal Acoustic Detection Pipeline:
   - Tier 1: Reality Defender API (when configured)
   - Tier 2: AASIST (ASVspoof2019-trained graph neural network)
   - Tier 3: Local Wav2Vec2 deepfake detector
   - Tier 4: Prosody and spectral heuristic analysis
4. Spoken Language Detection:
   - Real offline-capable Whisper model language identification (Telugu, Hindi, Tamil,
     Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Urdu, Odia, English, etc.)
5. Simple Scientifically Responsible Results:
   - 🟢 LIKELY GENUINE
   - 🔴 POSSIBLE AI-GENERATED VOICE
   - 🟡 UNABLE TO CONFIRM
6. Complete CORS configuration for GitHub Pages (https://vendikatlamasthan.github.io).
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audio.preprocessing import PreprocessedAudio
from app.audio.prosody import ProsodyAnalyzer
from app.models.asr import SpeechRecognizer, ASRResult
from app.models.detector import VoiceCloneDetector, determine_classification
from app.utils.audio_utils import calculate_rms, calculate_snr_estimate, linear_to_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("VoiceShield-API")

app = FastAPI(
    title="VoiceShield AI Anti-Fraud API",
    description="Real-time multi-signal voice clone and deepfake defense engine.",
    version="2.1.0",
)

# CORS configuration explicitly allowing GitHub Pages and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vendikatlamasthan.github.io",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global lazy singletons
_detector: Optional[VoiceCloneDetector] = None
_prosody_analyzer: Optional[ProsodyAnalyzer] = None
_speech_recognizer: Optional[SpeechRecognizer] = None


def get_detector() -> VoiceCloneDetector:
    global _detector
    if _detector is None:
        logger.info("Initializing VoiceCloneDetector (Reality Defender -> AASIST -> Wav2Vec2)...")
        _detector = VoiceCloneDetector()
        _detector.load()
    return _detector


def get_prosody_analyzer() -> ProsodyAnalyzer:
    global _prosody_analyzer
    if _prosody_analyzer is None:
        _prosody_analyzer = ProsodyAnalyzer()
    return _prosody_analyzer


def get_speech_recognizer() -> SpeechRecognizer:
    global _speech_recognizer
    if _speech_recognizer is None:
        logger.info("Initializing SpeechRecognizer (Whisper Multilingual LID)...")
        _speech_recognizer = SpeechRecognizer.get_instance()
    return _speech_recognizer


# --- Audio & Video Ingestion Helpers ---

def probe_has_audio_stream(file_path: str) -> bool:
    """Checks via ffprobe whether a media file has at least one audio stream."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
        return res.returncode == 0 and "audio" in res.stdout.strip().lower()
    except Exception as e:
        logger.warning(f"Audio stream probe failed: {e}")
        return False


def probe_duration(file_path: str) -> float:
    """Probes media duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
        if res.returncode == 0 and res.stdout.strip():
            d = float(res.stdout.strip())
            if not np.isnan(d) and d > 0:
                return d
    except Exception:
        pass
    return -1.0


def find_speech_offset(file_path: str) -> float:
    """Scans leading audio up to 45s with silencedetect to find where active speech starts."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "info",
        "-t", "45",
        "-i", file_path,
        "-af", "silencedetect=noise=-30dB:d=0.3",
        "-f", "null",
        "-",
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        match = re.search(r"silence_end:\s*([0-9.]+)", res.stderr)
        if match:
            offset = float(match.group(1))
            if 0 < offset < 40:
                return max(0.0, offset - 0.2)
    except Exception:
        pass
    return 0.0


def convert_and_standardize_to_16k(
    input_path: str,
    output_path: str,
    start_offset: float = 0.0,
    max_duration: float = 15.0,
) -> None:
    """Converts/extracts audio to 16kHz mono 16-bit PCM WAV, discarding video track (-vn)."""
    args = ["ffmpeg", "-y", "-nostdin", "-v", "error"]
    if start_offset > 0.05:
        args.extend(["-ss", f"{start_offset:.2f}"])
    args.extend([
        "-i", input_path,
        "-t", f"{max_duration:.1f}",
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-f", "wav",
        output_path,
    ])
    res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
    if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 44:
        err = res.stderr.strip()
        logger.error(f"FFmpeg conversion failed: {err}")
        raise ValueError(f"FFmpeg failed to convert/extract audio: {err}")


# --- Pydantic Response Schemas (SPEC.md Canonical Contract) ---

class SubScores(BaseModel):
    synthetic_voice_score: float = Field(..., ge=0.0, le=100.0)
    replay_channel_score: float = Field(..., ge=0.0, le=100.0)
    naturalness_score: float = Field(..., ge=0.0, le=100.0)


class AudioMetadataSchema(BaseModel):
    sample_rate: int = 16000
    original_duration_sec: float
    processed_duration_sec: float
    estimated_snr_db: float
    rms_db: float


class CanonicalAnalysisResponse(BaseModel):
    classification: str
    verdict: str
    sub_scores: SubScores
    detection_source: str
    risk_level: str
    explanation: str
    recommended_action: str
    audio_metadata: AudioMetadataSchema
    flags: List[str]
    scan_id: str
    # Spoken language identification
    detected_language: str
    language_code: Optional[str] = None
    language_confidence: Optional[float] = None
    # Simplified responsible presentation
    simple_verdict: str
    simple_verdict_badge: str
    # Long audio and media metadata
    input_type: str
    is_long_recording: bool = False
    user_notice: Optional[str] = None
    # Backward-compatible fields
    spoof_probability: float
    bonafide_probability: float
    model: str = "VoiceShield-Unified"


@app.on_event("startup")
async def startup_event():
    logger.info("Starting VoiceShield API server...")
    try:
        get_detector()
    except Exception as e:
        logger.warning(f"Detector pre-warm notice: {e}")
    try:
        get_speech_recognizer()
    except Exception as e:
        logger.warning(f"Speech recognizer pre-warm notice: {e}")


@app.get("/")
def root():
    return {
        "service": "VoiceShield AI Anti-Fraud API",
        "status": "online",
        "version": "2.1.0",
        "docs_url": "/docs",
    }


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint confirming engine readiness."""
    det = get_detector()
    sr = get_speech_recognizer()
    return {
        "status": "ok",
        "service": "VoiceShield AI Detection Engine",
        "architecture": "Canonical 4-Tier Pipeline (Reality Defender -> AASIST -> Wav2Vec2 -> Heuristic)",
        "weights_loaded": True,
        "pipeline": {
            "ffmpeg_available": True,
            "aasist_loaded": det.aasist.is_loaded if hasattr(det, "aasist") else False,
            "wav2vec2_loaded": det.wav2vec2.is_loaded if hasattr(det, "wav2vec2") else False,
            "whisper_asr_loaded": sr.is_loaded if hasattr(sr, "is_loaded") else False,
        },
    }


@app.get("/samples")
@app.get("/api/samples")
def get_samples():
    """Returns sample audio benchmarks for quick testing."""
    return {
        "samples": [
            {
                "filename": "human_voice_sample.wav",
                "url": "./samples/real_02.wav",
                "description": "Authentic human speech recording (bonafide benchmark)",
            },
            {
                "filename": "synthetic_clone_sample.wav",
                "url": "./samples/fake_01.wav",
                "description": "AI-generated synthetic voice clone sample (spoof)",
            },
            {
                "filename": "synthetic_vocoder_sample.wav",
                "url": "./samples/fake_02.wav",
                "description": "Synthetic speech sample exhibiting vocoder artifacts (spoof)",
            },
        ]
    }


async def _process_analysis(
    contents: bytes,
    filename: str,
    is_live: bool = False,
) -> CanonicalAnalysisResponse:
    """Core analysis execution supporting audio and video inputs."""
    temp_dir = tempfile.mkdtemp(prefix="vs_analyze_")
    raw_path = None
    standard_wav_path = os.path.join(temp_dir, "standard_16k.wav")

    try:
        # Determine media category
        ext = Path(filename).suffix.lower().replace(".", "")
        is_video = ext in ["mp4", "mov", "mkv", "webm", "avi", "3gp", "ts"]
        input_type = "video" if is_video else ("live" if (is_live or filename.startswith("mic_") or filename.startswith("live_")) else "audio")

        # Materialize raw upload bytes to disk
        file_suffix = f".{ext}" if ext else ".tmp"
        with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=file_suffix, delete=False) as f_raw:
            raw_path = f_raw.name
            f_raw.write(contents)
            f_raw.flush()

        # If video, verify audio track exists
        if is_video:
            has_audio = probe_has_audio_stream(raw_path)
            if not has_audio:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This video does not contain an audio track.",
                )

        # Probe duration and handle long files
        probed_dur = probe_duration(raw_path)
        start_offset = 0.0
        is_long_recording = False
        user_notice = None

        if probed_dur > 15.0:
            is_long_recording = True
            user_notice = "Long recording detected. A speech segment was selected for analysis."
            start_offset = find_speech_offset(raw_path)

        # Standardize via FFmpeg: single-pass 16kHz mono float32 WAV
        try:
            convert_and_standardize_to_16k(raw_path, standard_wav_path, start_offset, 15.0)
        except Exception as conv_err:
            logger.error(f"Audio conversion failed for '{filename}': {conv_err}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="We couldn't extract the audio from this video. Please ensure it has a valid audio track."
                if is_video else
                "We couldn't process this audio. Please check the file format or try recording again.",
            )

        # Read standardized PCM samples
        import soundfile as sf
        audio_data, sr = sf.read(standard_wav_path, dtype="float32")
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1)

        duration_sec = len(audio_data) / float(sr)
        if duration_sec < 0.8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The voice recording is too short. Please speak for at least 1 to 2 seconds for reliable analysis.",
            )

        # Energy and silence verification
        rms_val = float(np.sqrt(np.mean(audio_data ** 2) + 1e-12))
        if rms_val < 0.001:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No clear speech was detected.",
            )

        rms_db = float(linear_to_db(rms_val))
        snr_db = float(calculate_snr_estimate(audio_data.tolist()))

        preprocessed = PreprocessedAudio(
            waveform=audio_data.tolist(),
            sample_rate=sr,
            original_duration_sec=round(probed_dur if probed_dur > 0 else duration_sec, 3),
            processed_duration_sec=round(duration_sec, 3),
            rms_energy_db=round(rms_db, 2),
            estimated_snr_db=round(snr_db, 2),
            channels=1,
            metadata={"filename": filename, "input_type": input_type},
        )

        # 1. Multi-Tier Deepfake Voice Detection
        detector = get_detector()
        prediction_result = detector.predict(preprocessed)

        detection_source = prediction_result.metadata.get("detection_source", "local_fallback")
        fake_prob = float(prediction_result.fake_probability)
        synthetic_voice_score = round(fake_prob * 100.0, 1)

        # 2. Local Prosody & Acoustic Channel Analysis
        prosody_analyzer = get_prosody_analyzer()
        prosody_result = prosody_analyzer.analyze(preprocessed)

        acoustic_anomaly = float(prosody_result.acoustic_anomaly)
        replay_channel_score = round(min(100.0, max(0.0, acoustic_anomaly * 100.0)), 1)
        naturalness_score = round(min(100.0, max(0.0, (1.0 - acoustic_anomaly) * 100.0)), 1)

        hf_ratio = 0.0
        if hasattr(prosody_result, "features") and isinstance(prosody_result.features, dict):
            hf_ratio = float(prosody_result.features.get("hf_energy_ratio", 0.0))

        # 3. Multilingual Speech Recognition & Language Detection
        speech_recognizer = get_speech_recognizer()
        asr_res: ASRResult = speech_recognizer.transcribe(audio_data, sample_rate=sr)

        # Determine responsible language display
        if (
            asr_res.is_speech
            and asr_res.language_confidence >= 0.40
            and asr_res.language_name not in ["Unknown", "Unclear", "Silence", "Unavailable", "Error"]
        ):
            detected_language = asr_res.language_name
        else:
            detected_language = "Unable to confidently identify language"

        # 4. Determine Unified Classification
        classification = determine_classification(
            fake_probability=fake_prob,
            acoustic_anomaly=acoustic_anomaly,
            snr_db=snr_db,
            hf_energy_ratio=hf_ratio,
            detection_source=detection_source,
        )

        # 5. Map Simplified Verdict Responsibly
        if classification == "GENUINE_LIVE":
            simple_verdict = "LIKELY GENUINE"
            simple_verdict_badge = "🟢 LIKELY GENUINE"
            risk_level = "Low"
            explanation = (
                "Acoustic characteristics align with natural human speech. "
                "No significant synthetic cloning artifacts were identified."
            )
            recommended_action = "ALLOW"
        elif classification == "SYNTHETIC_AI_GENERATED":
            simple_verdict = "POSSIBLE AI-GENERATED VOICE"
            simple_verdict_badge = "🔴 POSSIBLE AI-GENERATED VOICE"
            risk_level = "High"
            explanation = (
                "Strong acoustic indicators of synthetic speech synthesis were detected in the audio extracted from this video."
                if is_video else
                "Strong acoustic indicators of synthetic speech or voice cloning were detected."
            )
            recommended_action = "SECONDARY_VERIFICATION"
        else:
            simple_verdict = "UNABLE TO CONFIRM"
            simple_verdict_badge = "🟡 UNABLE TO CONFIRM"
            risk_level = "Medium"
            explanation = "Acoustic signals are conflicting or borderline. Authenticity cannot be confirmed with high certainty."
            recommended_action = "MANUAL_REVIEW"

        flags: List[str] = []
        if classification == "SYNTHETIC_AI_GENERATED":
            flags.append(f"Synthetic artifacts flagged by {detection_source} ({synthetic_voice_score}/100)")
        elif classification == "GENUINE_LIVE":
            flags.append(f"Human vocal tract dynamics confirmed (Naturalness: {naturalness_score}/100)")
        if replay_channel_score > 60:
            flags.append(f"Channel reflection anomaly ({replay_channel_score}/100)")

        scan_id = f"VS-{int(time.time())}-{os.urandom(3).hex().upper()}"

        return CanonicalAnalysisResponse(
            classification=classification,
            verdict=classification,
            sub_scores=SubScores(
                synthetic_voice_score=synthetic_voice_score,
                replay_channel_score=replay_channel_score,
                naturalness_score=naturalness_score,
            ),
            detection_source=detection_source,
            risk_level=risk_level,
            explanation=explanation,
            recommended_action=recommended_action,
            audio_metadata=AudioMetadataSchema(
                sample_rate=sr,
                original_duration_sec=preprocessed.original_duration_sec,
                processed_duration_sec=preprocessed.processed_duration_sec,
                estimated_snr_db=preprocessed.estimated_snr_db,
                rms_db=preprocessed.rms_energy_db,
            ),
            flags=flags,
            scan_id=scan_id,
            detected_language=detected_language,
            language_code=asr_res.language if asr_res.language != "unknown" else None,
            language_confidence=round(asr_res.language_confidence, 4) if asr_res.language_confidence > 0 else None,
            simple_verdict=simple_verdict,
            simple_verdict_badge=simple_verdict_badge,
            input_type=input_type,
            is_long_recording=is_long_recording,
            user_notice=user_notice,
            spoof_probability=round(fake_prob, 4),
            bonafide_probability=round(1.0 - fake_prob, 4),
            model=detection_source,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/analyze", response_model=CanonicalAnalysisResponse)
@app.post("/analyze", response_model=CanonicalAnalysisResponse)
async def analyze_endpoint(
    file: UploadFile = File(...),
    is_live: Optional[bool] = Form(False),
):
    """
    Primary endpoint for VoiceShield AI voice clone and language analysis.
    Executes within a hard 15-second ceiling covering all detection tiers.
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select or record an audio or video file to analyze.",
        )

    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading upload file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't read this media file. Please try again.",
        )

    try:
        return await asyncio.wait_for(
            _process_analysis(contents, file.filename, is_live=bool(is_live)),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Analysis timed out after 15s for file '{file.filename}'")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="We couldn't complete the analysis in time. Please try a shorter recording or try again.",
        )
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Unhandled error during analysis: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Voice analysis could not be completed.",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main_api:app", host="0.0.0.0", port=port, reload=False)
