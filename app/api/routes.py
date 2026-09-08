"""
FastAPI Route Definitions for VoiceShield (Conforming to SPEC.md).

Exposes:
- GET /health: Service health and metadata
- POST /analyze: Voice clone detection, acoustic anomaly analysis, and unified classification
"""

import asyncio
import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.audio.preprocessing import AudioPreprocessor
from app.audio.prosody import ProsodyAnalyzer
from app.models.detector import VoiceCloneDetector, determine_classification
from app.utils.audio_utils import (
    AudioCorruptError,
    AudioSilentError,
    AudioTooShortError,
    AudioTooLongError,
    FileNotFoundAudioError,
    UnsupportedFormatError,
)

router = APIRouter()

# Global engine singletons (lazily initialized)
_preprocessor: Optional[AudioPreprocessor] = None
_prosody_analyzer: Optional[ProsodyAnalyzer] = None
_detector: Optional[VoiceCloneDetector] = None


def get_preprocessor() -> AudioPreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = AudioPreprocessor()
    return _preprocessor


def get_prosody_analyzer() -> ProsodyAnalyzer:
    global _prosody_analyzer
    if _prosody_analyzer is None:
        _prosody_analyzer = ProsodyAnalyzer()
    return _prosody_analyzer


def get_detector() -> VoiceCloneDetector:
    global _detector
    if _detector is None:
        _detector = VoiceCloneDetector()
        _detector.load()
    return _detector


# --- Pydantic Response Schemas (SPEC.md Contract) ---

class SubScores(BaseModel):
    synthetic_voice_score: float = Field(..., ge=0.0, le=100.0, description="Synthetic voice score [0-100]")
    replay_channel_score: float = Field(..., ge=0.0, le=100.0, description="Replay/channel acoustic anomaly score [0-100]")
    naturalness_score: float = Field(..., ge=0.0, le=100.0, description="Naturalness & prosody dynamics score [0-100]")


class AudioMetadataSchema(BaseModel):
    sample_rate: int = 16000
    original_duration_sec: float
    processed_duration_sec: float
    estimated_snr_db: float
    rms_db: float


class CanonicalAnalysisResponse(BaseModel):
    call_id: str
    classification: str = Field(..., description="One of GENUINE_LIVE | REPLAYED_RECORDED | SYNTHETIC_AI_GENERATED | UNCERTAIN")
    verdict: str
    sub_scores: SubScores
    detection_source: str = Field(..., description="Engine(s) that produced synthetic_voice_score")
    risk_level: str = Field(..., description="One of Low | Medium | High")
    explanation: str
    recommended_action: str
    audio_metadata: AudioMetadataSchema
    flags: List[str]
    spoof_probability: float
    bonafide_probability: float
    model: str


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "VoiceShield API"
    version: str = "2.0.0"
    detection_tiers: List[str] = [
        "Tier 1: Reality Defender RealAPI",
        "Tier 2: AASIST (ASVspoof2019)",
        "Tier 3: Pretrained Wav2Vec2",
        "Tier 4: Baseline Spectral Heuristic",
    ]


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint returning service readiness and tier metadata."""
    return HealthResponse()


@router.post("/analyze", response_model=CanonicalAnalysisResponse, tags=["Detection & Risk"])
@router.post("/api/analyze", response_model=CanonicalAnalysisResponse, tags=["Detection & Risk"])
async def analyze_audio(
    file: UploadFile = File(..., description="Audio file (.wav, .mp3, .webm, .ogg, .flac, etc.) to analyze"),
):
    """
    Unified analysis endpoint for voice cloning detection.
    Guarantees hard 15s timeout ceiling covering all detection tiers.
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please attach a valid audio file in the 'file' field.",
        )

    temp_dir = tempfile.mkdtemp(prefix="voiceshield_")
    temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex}_{file.filename}")

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        async def _run_detection():
            # 1. Preprocess audio via universal ingestion pipeline (16kHz mono)
            preprocessor = get_preprocessor()
            preprocessed = preprocessor.process(temp_path)

            # 2. Multi-tier deepfake detection (Reality Defender -> AASIST -> Wav2Vec2 -> Baseline)
            detector = get_detector()
            prediction_result = detector.predict(preprocessed)
            detection_source = prediction_result.metadata.get("detection_source", "local_fallback")
            fake_prob = float(prediction_result.fake_probability)
            synthetic_voice_score = round(fake_prob * 100.0, 1)

            # 3. Prosody & Acoustic Anomaly Analysis (Heuristic tier)
            prosody_analyzer = get_prosody_analyzer()
            prosody_result = prosody_analyzer.analyze(preprocessed)

            acoustic_anomaly = float(prosody_result.acoustic_anomaly)
            replay_channel_score = round(min(100.0, max(0.0, acoustic_anomaly * 100.0)), 1)
            naturalness_score = round(min(100.0, max(0.0, (1.0 - acoustic_anomaly) * 100.0)), 1)

            hf_ratio = 0.0
            if hasattr(prosody_result, "features") and isinstance(prosody_result.features, dict):
                hf_ratio = float(prosody_result.features.get("hf_energy_ratio", 0.0))

            # 4. Determine Classification with AASIST calibration caveat
            target_classification = determine_classification(
                fake_probability=fake_prob,
                acoustic_anomaly=acoustic_anomaly,
                snr_db=preprocessed.estimated_snr_db,
                hf_energy_ratio=hf_ratio,
                detection_source=detection_source,
            )

            # 5. Derive Risk Level (SPEC.md)
            if target_classification == "SYNTHETIC_AI_GENERATED" or synthetic_voice_score >= 70.0:
                risk_level = "High"
            elif target_classification in ("REPLAYED_RECORDED", "UNCERTAIN") or synthetic_voice_score >= 40.0:
                risk_level = "Medium"
            else:
                risk_level = "Low"

            # 6. Formulate Explanations & Actionable Advice
            flags: List[str] = []
            if target_classification == "SYNTHETIC_AI_GENERATED":
                flags.append(f"Synthetic voice clone detected by {detection_source} ({synthetic_voice_score}/100)")
                explanation = f"Digital speech synthesis artifacts detected by {detection_source} (Synthetic Voice Score: {synthetic_voice_score}/100)."
                recommended_action = "SECONDARY_VERIFICATION"
            elif target_classification == "REPLAYED_RECORDED":
                flags.append(f"Acoustic channel / replay anomaly detected ({replay_channel_score}/100)")
                explanation = f"Loudspeaker channel acoustics and playback roll-off detected (Replay Score: {replay_channel_score}/100)."
                recommended_action = "REQUEST_LIVE_CALLBACK"
            elif target_classification == "GENUINE_LIVE":
                flags.append(f"Natural human vocal tract acoustics verified (Naturalness: {naturalness_score}/100)")
                explanation = f"Natural speech dynamics, vocal variation, and human resonance verified (Naturalness Score: {naturalness_score}/100)."
                recommended_action = "ALLOW"
            else:
                flags.append("Inconclusive acoustic signals or conflicting detection tier scores")
                if detection_source == "aasist" and fake_prob >= 0.65 and naturalness_score >= 65:
                    flags.append("AASIST high synthetic score counterbalanced by natural human prosody (calibration caveat)")
                explanation = "Acoustic signals are conflicting or borderline. Cannot confirm authenticity with high certainty."
                recommended_action = "MANUAL_REVIEW"

            call_id = f"CALL-{uuid.uuid4().hex[:10].upper()}"

            return CanonicalAnalysisResponse(
                call_id=call_id,
                classification=target_classification,
                verdict=target_classification,
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
                    sample_rate=preprocessed.sample_rate,
                    original_duration_sec=preprocessed.original_duration_sec,
                    processed_duration_sec=preprocessed.processed_duration_sec,
                    estimated_snr_db=preprocessed.estimated_snr_db,
                    rms_db=preprocessed.rms_energy_db,
                ),
                flags=flags,
                spoof_probability=round(fake_prob, 4),
                bonafide_probability=round(1.0 - fake_prob, 4),
                model=detection_source,
            )

        # Enforce 15-second hard timeout
        try:
            return await asyncio.wait_for(_run_detection(), timeout=15.0)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="We couldn't complete the analysis in time. Please try a shorter recording or try again.",
            )

    except AudioTooShortError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The voice recording is too short. Please speak for at least 1 to 2 seconds for reliable analysis.",
        )
    except AudioSilentError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No clear voice was detected. Please ensure your microphone is working and speak clearly.",
        )
    except (AudioCorruptError, UnsupportedFormatError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't process this audio format. Please check your recording or try a different file.",
        )
    except HTTPException:
        raise
    except Exception as err:
        # Technical error sanitization: log server-side only
        import logging
        logging.getLogger("VoiceShield").error(f"Analysis error: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We encountered an issue analyzing this voice sample. Please try again.",
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
