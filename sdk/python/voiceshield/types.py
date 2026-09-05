"""
VoiceShield AI — Python SDK Types
Data models for enterprise, banking, and telecom integration.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeepfakeResult:
    prediction: str
    fake_probability: float
    real_probability: float
    model_type: str = "Wav2Vec2"
    inference_time_ms: float = 0.0


@dataclass
class SpeakerVerificationResult:
    status: str
    speaker_id: Optional[str] = None
    similarity_score: Optional[float] = None
    threshold: Optional[float] = None
    is_match: Optional[bool] = None
    speaker_mismatch_flag: Optional[int] = None
    sample_count: Optional[int] = None
    inference_time_ms: Optional[float] = None


@dataclass
class ProsodyAnalysisResult:
    acoustic_anomaly: float
    features: Dict[str, float] = field(default_factory=dict)
    anomaly_reasons: List[str] = field(default_factory=list)
    status: str = "COMPLETED"


@dataclass
class ASRAnalysisResult:
    language: str
    language_name: str
    language_confidence: float
    transcript: str
    is_speech: bool
    inference_time_ms: float
    keywords_detected: List[str] = field(default_factory=list)
    speech_context_flags: List[str] = field(default_factory=list)


@dataclass
class RiskSignalsResult:
    fake_probability: float
    speaker_mismatch: int
    acoustic_anomaly: float
    context_flag: int
    speaker_verification_status: str
    acoustic_model_status: str
    prosody_reasons: List[str] = field(default_factory=list)


@dataclass
class AudioMetadataResult:
    sample_rate: int
    original_duration_sec: float
    processed_duration_sec: float
    estimated_snr_db: float
    rms_db: float


@dataclass
class VerificationSessionResult:
    call_id: str
    status: str
    recommended_action: str
    risk_score: int
    risk_level: str
    is_held: bool
    hold_reason: Optional[str] = None
    selected_method: Optional[str] = None
    in_progress_step: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class AnalyzeResult:
    call_id: str
    risk_score: int
    risk_level: str
    recommended_action: str
    deepfake_detection: DeepfakeResult
    speaker_verification: SpeakerVerificationResult
    risk_signals: RiskSignalsResult
    flags: List[str]
    audio_metadata: AudioMetadataResult
    prosody_analysis: Optional[ProsodyAnalysisResult] = None
    language: Optional[str] = None
    language_name: Optional[str] = None
    language_confidence: Optional[float] = None
    transcript: Optional[str] = None
    speech_context_flags: List[str] = field(default_factory=list)
    asr_analysis: Optional[ASRAnalysisResult] = None
    verification_session: Optional[VerificationSessionResult] = None
    pipeline_latency_ms: Optional[float] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrollmentResult:
    status: str
    speaker_id: str
    speaker_name: Optional[str]
    sample_count: int
    embedding_dimension: int
    created_at: float
    updated_at: float
    message: str
    sample_rate_verified: int
    inference_time_ms: float


@dataclass
class VerifyResult:
    status: str
    speaker_id: str
    similarity_score: float
    threshold: float
    match: bool
    speaker_mismatch_flag: int
    sample_count: int
    inference_time_ms: float
    message: str


@dataclass
class EnrolledSpeaker:
    speaker_id: str
    speaker_name: Optional[str] = None
    dimension: int = 192
    sample_count: int = 1
    created_at: float = 0.0
    updated_at: Optional[float] = None


@dataclass
class OrganizationPolicy:
    organization_id: str
    name: str
    fake_prob_critical_threshold: float
    fake_prob_warn_threshold: float
    transaction_auto_hold_amount: float
    high_risk_wire_threshold: float
    role_enforcement_strictness: str
    speaker_verification_strictness: float
    independent_callback_required: bool
    supervisor_escalation_required: bool
    otp_verification_required: bool
    version: int = 1
