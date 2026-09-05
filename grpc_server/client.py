"""
VoiceShield AI — Official Python gRPC Client Library
Provides type-safe client access to VoiceShield gRPC service with streaming and metadata auth.
"""

from typing import Any, Dict, Iterator, List, Optional, Union
import grpc

from grpc_server.generated import voiceshield_pb2, voiceshield_pb2_grpc


class VoiceShieldGrpcClient:
    """
    Client for interacting with VoiceShield gRPC service.
    """

    def __init__(
        self,
        target: str = "localhost:50051",
        api_key: Optional[str] = None,
        channel: Optional[grpc.Channel] = None,
    ):
        self.target = target
        self.api_key = api_key
        self.channel = channel if channel is not None else grpc.insecure_channel(target)
        self.stub = voiceshield_pb2_grpc.VoiceShieldServiceStub(self.channel)

    def _get_metadata(self) -> List[tuple]:
        if self.api_key:
            return [("x-api-key", self.api_key)]
        return []

    def analyze_audio(
        self,
        audio_bytes: bytes,
        speaker_id: Optional[str] = None,
        verification_threshold: Optional[float] = None,
        organization_id: Optional[str] = None,
        caller_id: Optional[str] = None,
        claimed_role: Optional[str] = None,
        requested_amount: Optional[float] = None,
        normal_amount: Optional[float] = None,
        is_urgent: Optional[bool] = None,
        urgency_reason: Optional[str] = None,
        language: Optional[str] = None,
    ) -> voiceshield_pb2.AnalyzeAudioResponse:
        req = voiceshield_pb2.AnalyzeAudioRequest(
            audio_bytes=audio_bytes,
            speaker_id=speaker_id or "",
            verification_threshold=float(verification_threshold or 0.0),
            organization_id=organization_id or "",
            caller_id=caller_id or "",
            claimed_role=claimed_role or "",
            requested_amount=float(requested_amount or 0.0),
            normal_amount=float(normal_amount or 0.0),
            is_urgent=bool(is_urgent or False),
            urgency_reason=urgency_reason or "",
            language=language or "",
        )
        return self.stub.AnalyzeAudio(req, metadata=self._get_metadata())

    def enroll_speaker(
        self,
        audio_bytes: bytes,
        speaker_id: str,
        speaker_name: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> voiceshield_pb2.EnrollSpeakerResponse:
        req = voiceshield_pb2.EnrollSpeakerRequest(
            audio_bytes=audio_bytes,
            speaker_id=speaker_id,
            speaker_name=speaker_name or "",
            organization_id=organization_id or "",
        )
        return self.stub.EnrollSpeaker(req, metadata=self._get_metadata())

    def verify_speaker(
        self,
        audio_bytes: bytes,
        speaker_id: str,
        threshold: Optional[float] = None,
        organization_id: Optional[str] = None,
    ) -> voiceshield_pb2.VerifySpeakerResponse:
        req = voiceshield_pb2.VerifySpeakerRequest(
            audio_bytes=audio_bytes,
            speaker_id=speaker_id,
            threshold=float(threshold or 0.0),
            organization_id=organization_id or "",
        )
        return self.stub.VerifySpeaker(req, metadata=self._get_metadata())

    def get_risk_policy(
        self, organization_id: Optional[str] = None
    ) -> voiceshield_pb2.GetRiskPolicyResponse:
        req = voiceshield_pb2.GetRiskPolicyRequest(
            organization_id=organization_id or ""
        )
        return self.stub.GetRiskPolicy(req, metadata=self._get_metadata())

    def stream_live_audio(
        self, chunk_iterator: Iterator[voiceshield_pb2.LiveAudioChunk]
    ) -> Iterator[voiceshield_pb2.LiveAudioAnalysisResult]:
        return self.stub.StreamLiveAudio(chunk_iterator, metadata=self._get_metadata())

    def close(self):
        if self.channel:
            self.channel.close()
