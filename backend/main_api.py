"""
VoiceShield AI — Canonical Backend API (conforming to SPEC.md).

FastAPI backend orchestrating:
1. Universal Audio Ingestion: All audio (WebM, Opus, MP3, WAV, M4A, FLAC, etc.) is converted
   via a single shared FFmpeg step into 16kHz mono float32 PCM.
2. Detection Tiers (Priority Order):
   - Tier 1: Reality Defender RealAPI (8s timeout cap, when configured)
   - Tier 2: AASIST (ASVspoof2019-trained, fed only converted 16kHz audio)
   - Tier 3: Local Wav2Vec2 model (fallback signal)
   - Tier 4: Local heuristic / spectral baseline (deterministic fallback)
3. Local Heuristic Prosody & Replay Analysis (always runs).
4. AASIST Calibration Caveat: Prevents miscalibrations on clean mic recordings from forcing
   false-positive synthetic verdicts when naturalness and channel acoustics disagree.
5. Canonical 4-class classification contract + sub_scores + detection_source + risk_level.
6. 15-second overall hard timeout cap.
7. Technical error sanitization: Raw exceptions and memory pointers never reach user.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audio.ingestion import convert_and_decode_to_16k_mono, CorruptAudioError
from app.audio.preprocessing import PreprocessedAudio
from app.audio.prosody import ProsodyAnalyzer
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
    version="2.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global lazy singletons
_detector: Optional[VoiceCloneDetector] = None
_prosody_analyzer: Optional[ProsodyAnalyzer] = None


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


# --- Pydantic Response Schemas (SPEC.md Contract) ---

class SubScores(BaseModel):
    synthetic_voice_score: float = Field(..., ge=0.0, le=100.0, description="Synthetic voice confidence score [0-100]")
    replay_channel_score: float = Field(..., ge=0.0, le=100.0, description="Replay/channel acoustic anomaly score [0-100]")
    naturalness_score: float = Field(..., ge=0.0, le=100.0, description="Vocal naturalness & prosodic dynamics [0-100]")


class AudioMetadataSchema(BaseModel):
    sample_rate: int = 16000
    original_duration_sec: float
    processed_duration_sec: float
    estimated_snr_db: float
    rms_db: float


class CanonicalAnalysisResponse(BaseModel):
    classification: str = Field(..., description="One of GENUINE_LIVE | REPLAYED_RECORDED | SYNTHETIC_AI_GENERATED | UNCERTAIN")
    verdict: str = Field(..., description="Canonical verdict (identical to classification)")
    sub_scores: SubScores
    detection_source: str = Field(..., description="Engine(s) that produced synthetic_voice_score: reality_defender | aasist | wav2vec2 | local_fallback")
    risk_level: str = Field(..., description="One of Low | Medium | High")
    explanation: str
    recommended_action: str
    audio_metadata: AudioMetadataSchema
    flags: List[str]
    scan_id: str
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
        logger.error(f"Detector initialization notice: {e}")


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint confirming engine readiness."""
    det = get_detector()
    return {
        "status": "healthy",
        "service": "VoiceShield AI Detection Engine",
        "architecture": "Canonical 4-Tier Pipeline (Reality Defender -> AASIST -> Wav2Vec2 -> Heuristic)",
        "aasist_loaded": det.aasist.is_loaded if hasattr(det, "aasist") else False,
        "weights_loaded": True,
    }


@app.get("/")
def root():
    return {
        "service": "VoiceShield AI Canonical API",
        "status": "online",
        "spec": "SPEC.md",
        "docs_url": "/docs",
    }


async def _process_analysis(contents: bytes, filename: str) -> CanonicalAnalysisResponse:
    """Core analysis execution with single shared conversion and multi-tier fusion."""
    start_time = time.perf_counter()

    # 1. Single shared FFmpeg conversion to 16kHz mono float32 array
    try:
        waveform, sr, _ = convert_and_decode_to_16k_mono(contents, original_filename=filename)
    except CorruptAudioError as e:
        logger.warning(f"Audio decode rejected for '{filename}': {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't process this audio format. Please check your recording or provide a valid audio file.",
        )
    except Exception as e:
        logger.error(f"Ingestion failure for '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't process this audio. Please check the file and try again.",
        )

    # 2. Duration checks
    duration_sec = len(waveform) / float(sr)
    if duration_sec < 0.8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The voice recording is too short. Please speak for at least 1 to 2 seconds for reliable analysis.",
        )

    # 3. Silence / Energy check
    rms_val = float(np.sqrt(np.mean(waveform ** 2)))
    if rms_val < 0.001:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No clear voice was detected. Please speak closer to your microphone and try again.",
        )

    # Calculate basic acoustics
    rms_db = float(linear_to_db(rms_val))
    snr_db = float(calculate_snr_estimate(waveform.tolist()))

    preprocessed = PreprocessedAudio(
        waveform=waveform.tolist(),
        sample_rate=sr,
        original_duration_sec=round(duration_sec, 3),
        processed_duration_sec=round(duration_sec, 3),
        rms_energy_db=round(rms_db, 2),
        estimated_snr_db=round(snr_db, 2),
        channels=1,
        metadata={"filename": filename},
    )

    # 4. Multi-Tier Detection: Reality Defender (Tier 1) -> AASIST (Tier 2) -> Wav2Vec2 (Tier 3) -> Baseline (Tier 4)
    detector = get_detector()
    prediction_result = detector.predict(preprocessed)

    detection_source = prediction_result.metadata.get("detection_source", "local_fallback")
    fake_prob = float(prediction_result.fake_probability)
    synthetic_voice_score = round(fake_prob * 100.0, 1)

    # 5. Local Heuristic Prosody & Replay Analysis (always runs)
    prosody_analyzer = get_prosody_analyzer()
    prosody_result = prosody_analyzer.analyze(preprocessed)

    acoustic_anomaly = float(prosody_result.acoustic_anomaly)
    replay_channel_score = round(min(100.0, max(0.0, acoustic_anomaly * 100.0)), 1)
    naturalness_score = round(min(100.0, max(0.0, (1.0 - acoustic_anomaly) * 100.0)), 1)

    hf_ratio = 0.0
    if hasattr(prosody_result, "features") and isinstance(prosody_result.features, dict):
        hf_ratio = float(prosody_result.features.get("hf_energy_ratio", 0.0))

    # 6. Unified Classification Contract (with AASIST calibration caveat)
    classification = determine_classification(
        fake_probability=fake_prob,
        acoustic_anomaly=acoustic_anomaly,
        snr_db=snr_db,
        hf_energy_ratio=hf_ratio,
        detection_source=detection_source,
    )

    # 7. Derive Risk Level (SPEC.md)
    if classification == "SYNTHETIC_AI_GENERATED" or synthetic_voice_score >= 70.0:
        risk_level = "High"
    elif classification in ("REPLAYED_RECORDED", "UNCERTAIN") or synthetic_voice_score >= 40.0:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # 8. Formulate Explanations & Actionable Advice
    flags: List[str] = []
    if classification == "SYNTHETIC_AI_GENERATED":
        flags.append(f"Synthetic voice clone detected by {detection_source} ({synthetic_voice_score}/100)")
        explanation = f"Digital speech synthesis artifacts detected by {detection_source} (Synthetic Voice Score: {synthetic_voice_score}/100)."
        recommended_action = "SECONDARY_VERIFICATION"
    elif classification == "REPLAYED_RECORDED":
        flags.append(f"Acoustic channel / replay anomaly detected ({replay_channel_score}/100)")
        explanation = f"Loudspeaker channel acoustics and playback roll-off detected (Replay Score: {replay_channel_score}/100)."
        recommended_action = "REQUEST_LIVE_CALLBACK"
    elif classification == "GENUINE_LIVE":
        flags.append(f"Natural human vocal tract acoustics verified (Naturalness: {naturalness_score}/100)")
        explanation = f"Natural speech dynamics, vocal variation, and human resonance verified (Naturalness Score: {naturalness_score}/100)."
        recommended_action = "ALLOW"
    else:
        # UNCERTAIN
        flags.append("Inconclusive acoustic signals or conflicting detection tier scores")
        if detection_source == "aasist" and fake_prob >= 0.65 and naturalness_score >= 65:
            flags.append("AASIST high synthetic score counterbalanced by natural human prosody (calibration caveat)")
        explanation = "Acoustic signals are conflicting or borderline. Cannot confirm authenticity with high certainty."
        recommended_action = "MANUAL_REVIEW"

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
        spoof_probability=round(fake_prob, 4),
        bonafide_probability=round(1.0 - fake_prob, 4),
        model=detection_source,
    )


@app.post("/api/analyze", response_model=CanonicalAnalysisResponse)
@app.post("/analyze", response_model=CanonicalAnalysisResponse)
async def analyze_audio(file: UploadFile = File(...)):
    """
    Primary endpoint for VoiceShield AI voice clone detection.
    Guarantees response within a hard 15-second ceiling covering all detection tiers.
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select or record an audio file to analyze.",
        )

    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded audio file is empty.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading upload file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't read this audio file. Please try again.",
        )

    # 15-second overall hard timeout cap covering all tiers combined
    try:
        return await asyncio.wait_for(
            _process_analysis(contents, file.filename),
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
        # Technical error sanitization: Log raw error on server only; never return memory addresses or stack traces
        logger.error(f"Unhandled error during analysis: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We encountered an issue analyzing this voice sample. Please try again.",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main_api:app", host="0.0.0.0", port=port, reload=False)
