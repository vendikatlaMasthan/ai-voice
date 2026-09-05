"""
VoiceShield AI — Official Python SDK
Reusable client library for external banking, enterprise, and telecom voice security integration.
"""

from .client import VoiceShieldClient
from .types import (
    ASRAnalysisResult,
    AnalyzeResult,
    AudioMetadataResult,
    DeepfakeResult,
    EnrolledSpeaker,
    EnrollmentResult,
    OrganizationPolicy,
    ProsodyAnalysisResult,
    RiskSignalsResult,
    SpeakerVerificationResult,
    VerificationSessionResult,
    VerifyResult,
)

__version__ = "1.0.0"

__all__ = [
    "VoiceShieldClient",
    "AnalyzeResult",
    "DeepfakeResult",
    "SpeakerVerificationResult",
    "ProsodyAnalysisResult",
    "ASRAnalysisResult",
    "RiskSignalsResult",
    "AudioMetadataResult",
    "VerificationSessionResult",
    "EnrollmentResult",
    "VerifyResult",
    "EnrolledSpeaker",
    "OrganizationPolicy",
]
