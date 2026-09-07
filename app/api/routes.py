"""
FastAPI Route Definitions for VoiceShield (Phase 4).

Exposes:
- GET /health: Service health and metadata
- POST /analyze: Deepfake audio detection & multi-signal risk calculation
- POST /enroll: Speaker enrollment interface (Phase 5 placeholder)
- POST /verify-speaker: Biometric speaker verification interface (Phase 5 placeholder)
"""

import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.audio.preprocessing import AudioPreprocessor
from app.audio.prosody import ProsodyAnalysisResult, ProsodyAnalyzer
from app.models.detector import VoiceCloneDetector, determine_classification
from app.risk.context import CallContext
from app.risk.scoring import VoiceShieldRiskEngine
from app.utils.audio_utils import (
    AudioCorruptError,
    AudioSilentError,
    AudioTooShortError,
    AudioTooLongError,
    FileNotFoundAudioError,
    UnsupportedFormatError,
)

router = APIRouter()

# Global engine singletons (lazily initialized or injected)
_preprocessor: Optional[AudioPreprocessor] = None
_prosody_analyzer: Optional[ProsodyAnalyzer] = None
_detector: Optional[VoiceCloneDetector] = None
_risk_engine: Optional[VoiceShieldRiskEngine] = None


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


def get_risk_engine() -> VoiceShieldRiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = VoiceShieldRiskEngine()
    return _risk_engine


# --- Pydantic Response Schemas ---

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "VoiceShield API"
    version: str = "1.0.0"
    supported_models: List[str] = [
        "garystafford/wav2vec2-deepfake-voice-detector",
    ]


class DeepfakeResultSchema(BaseModel):
    prediction: str
    classification: Optional[str] = None
    verdict: Optional[str] = None
    fake_probability: float
    real_probability: float
    model_type: str
    model_id: str
    inference_time_ms: float
    disclaimer: Optional[str] = None


class SpeakerVerificationDetailSchema(BaseModel):
    status: str
    speaker_id: Optional[str] = None
    similarity_score: Optional[float] = None
    threshold: Optional[float] = None
    is_match: Optional[bool] = None
    speaker_mismatch_flag: Optional[int] = None
    inference_time_ms: Optional[float] = None


class AudioMetadataSchema(BaseModel):
    sample_rate: int
    original_duration_sec: float
    processed_duration_sec: float
    estimated_snr_db: float
    rms_db: float


class RiskSignalsSchema(BaseModel):
    fake_probability: float
    speaker_mismatch: int
    acoustic_anomaly: float
    context_flag: float
    speaker_verification_status: str
    acoustic_model_status: str
    prosody_reasons: Optional[List[str]] = None
    prosody_features: Optional[Dict[str, float]] = None


class AnalyzeResponse(BaseModel):
    call_id: str
    classification: str
    verdict: str
    risk_score: int
    risk_level: str
    deepfake_detection: DeepfakeResultSchema
    speaker_verification: SpeakerVerificationDetailSchema
    prosody_analysis: Optional[Dict[str, Any]] = None
    risk_signals: RiskSignalsSchema
    flags: List[str]
    recommended_action: str
    audio_metadata: AudioMetadataSchema


# --- Endpoints ---

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint returning service readiness and model metadata.
    """
    return HealthResponse(
        status="ok",
        service="VoiceShield API",
        version="1.0.0",
        supported_models=[
            "garystafford/wav2vec2-deepfake-voice-detector",
        ],
    )


@router.post("/analyze", response_model=AnalyzeResponse, tags=["Detection & Risk"])
async def analyze_audio(
    file: UploadFile = File(..., description="Audio file (.wav, .flac, .mp3, etc.) to analyze"),
    speaker_id: Optional[str] = Form(None, description="Optional claimed speaker ID for biometric verification"),
    verification_threshold: Optional[float] = Form(None, description="Custom similarity threshold [0.0 - 1.0]"),
    caller_id: Optional[str] = Form(None, description="Incoming phone number or caller identifier"),
    is_caller_recognized: bool = Form(True, description="Whether caller is an established saved contact"),
    is_previously_flagged: bool = Form(False, description="Whether caller has prior suspicious incident history"),
    claimed_role: Optional[str] = Form(None, description="Caller's claimed role (e.g. CEO, CFO, Accountant)"),
    requested_transaction_amount: Optional[float] = Form(None, description="Financial transfer amount requested"),
    normal_transaction_amount: Optional[float] = Form(None, description="Historical average transaction baseline"),
    is_urgent: bool = Form(False, description="Whether immediate action/urgency pressure is asserted"),
    urgency_reason: Optional[str] = Form(None, description="Reason stated for urgency pressure"),
    transcript_text: Optional[str] = Form(None, description="Call transcript snippet for keyword scanning"),
    acoustic_anomaly_override: Optional[float] = Form(
        None, description="Optional manual override for prosodic anomaly score [0.0, 1.0]"
    ),
):
    """
    Primary analysis endpoint for voice cloning detection, biometric speaker verification, and fraud risk scoring.
    
    1. Validates and preprocesses uploaded audio into 16kHz mono.
    2. Runs deepfake voice clone detection using fine-tuned Wav2Vec2.
    3. Performs deterministic prosodic and acoustic anomaly feature extraction.
    4. Performs biometric speaker verification if speaker_id is enrolled.
    5. Evaluates contextual indicators (caller recognition, claimed role, transaction spikes, urgency keywords).
    6. Computes composite risk score and outputs actionable security recommendations.
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing audio file. Please attach a valid audio file in the 'file' form field.",
        )

    temp_dir = tempfile.mkdtemp(prefix="voiceshield_")
    temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex}_{file.filename}")

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 1. Preprocess audio using Phase 1 pipeline
        preprocessor = get_preprocessor()
        preprocessed = preprocessor.process(temp_path)

        # 2. Deepfake detection inference using Phase 2 model
        detector = get_detector()
        prediction_result = detector.predict(preprocessed)

        # 3. Prosody & Acoustic Anomaly Analysis
        prosody_analyzer = get_prosody_analyzer()
        prosody_result = prosody_analyzer.analyze(preprocessed)

        if acoustic_anomaly_override is not None and float(acoustic_anomaly_override) > 0.0:
            resolved_acoustic_anomaly = float(acoustic_anomaly_override)
        else:
            resolved_acoustic_anomaly = prosody_result.acoustic_anomaly

        speaker_mismatch_signal = 0
        speaker_verification_status = "NOT_EVALUATED"
        speaker_detail = SpeakerVerificationDetailSchema(
            status="NOT_EVALUATED",
            speaker_id=speaker_id,
            similarity_score=None,
            threshold=None,
            is_match=None,
            speaker_mismatch_flag=0,
            inference_time_ms=0.0,
        )

        # 5. Formulate call context for Phase 3 risk engine
        call_context = CallContext(
            caller_id=caller_id,
            is_caller_recognized=is_caller_recognized,
            is_previously_flagged=is_previously_flagged,
            claimed_role=claimed_role,
            requested_transaction_amount=requested_transaction_amount,
            normal_transaction_amount=normal_transaction_amount,
            is_urgent=is_urgent,
            urgency_reason=urgency_reason,
            transcript_text=transcript_text,
        )

        # 6. Calculate composite risk score using Phase 3 engine
        risk_engine = get_risk_engine()
        risk_assessment = risk_engine.evaluate(
            fake_probability=prediction_result.fake_probability,
            speaker_mismatch=speaker_mismatch_signal,
            acoustic_anomaly=resolved_acoustic_anomaly,
            context=call_context,
            prosody_reasons=prosody_result.anomaly_reasons,
        )

        call_id = f"CALL-{uuid.uuid4().hex[:10].upper()}"

        hf_ratio = 0.0
        if hasattr(prosody_result, "features") and isinstance(prosody_result.features, dict):
            hf_ratio = float(prosody_result.features.get("hf_energy_ratio", 0.0))

        target_classification = determine_classification(
            fake_probability=prediction_result.fake_probability,
            acoustic_anomaly=resolved_acoustic_anomaly,
            snr_db=preprocessed.estimated_snr_db,
            hf_energy_ratio=hf_ratio,
        )

        return AnalyzeResponse(
            call_id=call_id,
            classification=target_classification,
            verdict=target_classification,
            risk_score=risk_assessment.risk_score,
            risk_level=risk_assessment.risk_level,
            deepfake_detection=DeepfakeResultSchema(
                prediction=prediction_result.prediction,
                classification=target_classification,
                verdict=target_classification,
                fake_probability=prediction_result.fake_probability,
                real_probability=prediction_result.real_probability,
                model_type=prediction_result.metadata.get("model_type", "Wav2Vec2"),
                model_id=prediction_result.metadata.get("model_id", "garystafford/wav2vec2-deepfake-voice-detector"),
                inference_time_ms=prediction_result.metadata.get("inference_time_ms", 0.0),
                disclaimer=prediction_result.metadata.get("disclaimer"),
            ),
            speaker_verification=speaker_detail,
            prosody_analysis=prosody_result.to_dict(),
            risk_signals=RiskSignalsSchema(
                fake_probability=prediction_result.fake_probability,
                speaker_mismatch=speaker_mismatch_signal,
                acoustic_anomaly=round(float(resolved_acoustic_anomaly), 4),
                context_flag=risk_assessment.signals.get("context_flag", 0.0),
                speaker_verification_status=speaker_verification_status,
                acoustic_model_status="DETERMINISTIC_PROSODY_ANALYSIS",
                prosody_reasons=prosody_result.anomaly_reasons,
                prosody_features={k: round(float(v), 4) for k, v in prosody_result.features.items()},
            ),
            flags=risk_assessment.flags,
            recommended_action=risk_assessment.recommended_action,
            audio_metadata=AudioMetadataSchema(
                sample_rate=preprocessed.sample_rate,
                original_duration_sec=preprocessed.original_duration_sec,
                processed_duration_sec=preprocessed.processed_duration_sec,
                estimated_snr_db=preprocessed.estimated_snr_db,
                rms_db=preprocessed.rms_energy_db,
            ),
        )


    except AudioTooShortError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_type": "AudioTooShortError", "message": str(err)},
        )
    except AudioTooLongError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_type": "AudioTooLongError", "message": str(err)},
        )
    except AudioSilentError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_type": "AudioSilentError", "message": str(err)},
        )
    except (AudioCorruptError, UnsupportedFormatError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_type": "AudioCorruptError", "message": str(err)},
        )
    except FileNotFoundAudioError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_type": "FileNotFoundAudioError", "message": str(err)},
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error_type": "InferenceError", "message": f"Analysis failed: {str(err)}"},
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

