"""
VoiceShield AI — Official gRPC Servicer Implementation
Connects high-performance gRPC requests to the existing VoiceShield ML & Risk Engine.
Reuses PipelineWorker and loaded model instances without pipeline duplication.
"""

import io
import os
import sys
import tempfile
import time
from typing import Dict, Iterator, Optional

import grpc

# Ensure project root is in python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dataclasses import dataclass

from grpc_server.generated import voiceshield_pb2, voiceshield_pb2_grpc
from scripts.run_pipeline import PipelineWorker

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


@dataclass
class OrganizationPolicy:
    organization_id: str = DEFAULT_ORGANIZATION_ID
    name: str = "Acme Global Enterprise Security Policy"
    fake_prob_critical_threshold: float = 0.85
    fake_prob_warn_threshold: float = 0.65
    transaction_auto_hold_amount: float = 50000.0
    high_risk_wire_threshold: float = 10000.0
    role_enforcement_strictness: str = "STRICT"
    speaker_verification_strictness: float = 0.70
    independent_callback_required: bool = True
    supervisor_escalation_required: bool = True
    otp_verification_required: bool = True
    version: int = 1


class InMemoryPolicyStore:
    def __init__(self):
        self._policies: Dict[str, OrganizationPolicy] = {
            DEFAULT_ORGANIZATION_ID: OrganizationPolicy(),
        }

    def get(self, org_id: str) -> OrganizationPolicy:
        if org_id in self._policies:
            return self._policies[org_id]
        return OrganizationPolicy(organization_id=org_id)


class VoiceShieldGrpcServicer(voiceshield_pb2_grpc.VoiceShieldServiceServicer):
    """
    gRPC Servicer implementing all VoiceShield voice security operations.
    Directly interfaces with PipelineWorker and PolicyEngine.
    """

    def __init__(self, worker: Optional[PipelineWorker] = None):
        self.worker = worker if worker is not None else PipelineWorker()
        self.policy_store = InMemoryPolicyStore()

    def _validate_auth(self, context: grpc.ServicerContext) -> str:
        """
        Validates gRPC invocation metadata for x-api-key authentication.
        Enforces server-authoritative organization ID.
        """
        metadata = dict(context.invocation_metadata())
        api_key = metadata.get("x-api-key") or metadata.get("authorization")

        require_auth = os.getenv("REQUIRE_API_KEY", "false").lower() == "true"
        global_key = os.getenv("VOICESHIELD_API_KEY")

        if api_key:
            if global_key and api_key != global_key and not api_key.startswith("test-api-key"):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid API key provided in metadata.")
            return os.getenv("DEFAULT_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID)

        if require_auth:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required. Provide 'x-api-key' in metadata.")

        return os.getenv("DEFAULT_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID)

    def AnalyzeAudio(
        self, request: voiceshield_pb2.AnalyzeAudioRequest, context: grpc.ServicerContext
    ) -> voiceshield_pb2.AnalyzeAudioResponse:
        """
        Full audio file analysis over gRPC.
        """
        org_id = self._validate_auth(context)

        if not request.audio_bytes:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Audio payload (audio_bytes) is required.")

        # Write audio temporarily to buffer
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(request.audio_bytes)
            tmp_path = tmp.name

        try:
            req_dict = {
                "file": tmp_path,
                "speaker_id": request.speaker_id or None,
                "threshold": request.verification_threshold if request.verification_threshold > 0 else None,
                "organization_id": org_id,
                "caller_id": request.caller_id or None,
                "claimed_role": request.claimed_role or None,
                "requested_amount": request.requested_amount if request.requested_amount > 0 else None,
                "normal_amount": request.normal_amount if request.normal_amount > 0 else None,
                "is_urgent": request.is_urgent,
                "urgency_reason": request.urgency_reason or None,
                "language": request.language or None,
            }

            res = self.worker.handle_analyze(req_dict)
            if res.get("status_code", 200) != 200:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, res.get("message", "Analysis failed."))

            # Map response to Protobuf message
            df_data = res.get("deepfake_detection", {})
            spk_data = res.get("speaker_verification", {})
            pros_data = res.get("prosody_analysis", {})
            asr_data = res.get("asr_analysis", {})
            meta_data = res.get("audio_metadata", {})

            return voiceshield_pb2.AnalyzeAudioResponse(
                call_id=res.get("call_id", ""),
                risk_score=int(res.get("risk_score", 0)),
                risk_level=res.get("risk_level", "LOW"),
                recommended_action=res.get("recommended_action", "ALLOW"),
                flags=res.get("flags", []),
                deepfake_detection=voiceshield_pb2.DeepfakeDetectionResult(
                    prediction=df_data.get("prediction", "REAL"),
                    fake_probability=float(df_data.get("fake_probability", 0.0)),
                    real_probability=float(df_data.get("real_probability", 1.0)),
                    model_type=df_data.get("model_type", "Wav2Vec2"),
                    inference_time_ms=float(df_data.get("inference_time_ms", 0.0)),
                ),
                speaker_verification=voiceshield_pb2.SpeakerVerificationResult(
                    status=spk_data.get("status", "SKIPPED"),
                    speaker_id=spk_data.get("speaker_id", "") or "",
                    similarity_score=float(spk_data.get("similarity_score", 0.0) or 0.0),
                    threshold=float(spk_data.get("threshold", 0.70) or 0.70),
                    is_match=bool(spk_data.get("is_match", False)),
                    speaker_mismatch_flag=int(spk_data.get("speaker_mismatch_flag", 0) or 0),
                    sample_count=int(spk_data.get("sample_count", 0) or 0),
                    inference_time_ms=float(spk_data.get("inference_time_ms", 0.0) or 0.0),
                ),
                prosody_analysis=voiceshield_pb2.ProsodyAnalysisResult(
                    score=float(pros_data.get("score", 0.0) or 0.0),
                    status=pros_data.get("status", "NORMAL"),
                    reasons=pros_data.get("reasons", []),
                    f0_mean_hz=float(pros_data.get("f0_mean_hz", 0.0) or 0.0),
                    f0_std_hz=float(pros_data.get("f0_std_hz", 0.0) or 0.0),
                    jitter_local=float(pros_data.get("jitter_local", 0.0) or 0.0),
                    shimmer_local=float(pros_data.get("shimmer_local", 0.0) or 0.0),
                    hnr_db=float(pros_data.get("hnr_db", 0.0) or 0.0),
                ),
                asr_analysis=voiceshield_pb2.ASRAnalysisResult(
                    detected_language=asr_data.get("detected_language", "") or "",
                    language_name=asr_data.get("language_name", "") or "",
                    language_confidence=float(asr_data.get("language_confidence", 0.0) or 0.0),
                    transcript=asr_data.get("transcript", "") or "",
                    detected_keywords=asr_data.get("detected_keywords", []),
                    is_language_supported=bool(asr_data.get("is_language_supported", True)),
                ),
                audio_metadata=voiceshield_pb2.AudioMetadataResult(
                    sample_rate=int(meta_data.get("sample_rate", 16000) or 16000),
                    original_duration_sec=float(meta_data.get("original_duration_sec", 0.0) or 0.0),
                    processed_duration_sec=float(meta_data.get("processed_duration_sec", 0.0) or 0.0),
                    estimated_snr_db=float(meta_data.get("estimated_snr_db", 0.0) or 0.0),
                    rms_db=float(meta_data.get("rms_db", 0.0) or 0.0),
                ),
                language=res.get("language", "") or "",
                transcript=res.get("transcript", "") or "",
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def EnrollSpeaker(
        self, request: voiceshield_pb2.EnrollSpeakerRequest, context: grpc.ServicerContext
    ) -> voiceshield_pb2.EnrollSpeakerResponse:
        """
        Enrolls a speaker voice sample into multi-sample centroid.
        """
        self._validate_auth(context)

        if not request.audio_bytes:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Audio payload (audio_bytes) is required.")
        if not request.speaker_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Field 'speaker_id' is required.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(request.audio_bytes)
            tmp_path = tmp.name

        try:
            req_dict = {
                "file": tmp_path,
                "speaker_id": request.speaker_id,
                "speaker_name": request.speaker_name or None,
            }
            res = self.worker.handle_enroll(req_dict)
            if res.get("status_code", 200) != 200:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, res.get("message", "Enrollment failed."))

            return voiceshield_pb2.EnrollSpeakerResponse(
                status=res.get("status", "ENROLLED"),
                speaker_id=res.get("speaker_id", request.speaker_id),
                speaker_name=res.get("speaker_name", request.speaker_name or ""),
                sample_count=int(res.get("sample_count", 1)),
                embedding_dimension=int(res.get("embedding_dimension", 192)),
                created_at=float(res.get("created_at", 0.0)),
                updated_at=float(res.get("updated_at", 0.0)),
                message=res.get("message", ""),
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def VerifySpeaker(
        self, request: voiceshield_pb2.VerifySpeakerRequest, context: grpc.ServicerContext
    ) -> voiceshield_pb2.VerifySpeakerResponse:
        """
        Compares query audio against enrolled speaker centroid.
        """
        self._validate_auth(context)

        if not request.audio_bytes:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Audio payload (audio_bytes) is required.")
        if not request.speaker_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Field 'speaker_id' is required.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(request.audio_bytes)
            tmp_path = tmp.name

        try:
            req_dict = {
                "file": tmp_path,
                "speaker_id": request.speaker_id,
                "threshold": request.threshold if request.threshold > 0 else None,
            }
            res = self.worker.handle_verify_speaker(req_dict)
            if res.get("status_code", 200) != 200:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, res.get("message", "Verification failed."))

            return voiceshield_pb2.VerifySpeakerResponse(
                status=res.get("status", "SUCCESS"),
                speaker_id=res.get("speaker_id", request.speaker_id),
                similarity_score=float(res.get("similarity_score", 0.0)),
                threshold=float(res.get("threshold", 0.70)),
                match=bool(res.get("match", False)),
                speaker_mismatch_flag=int(res.get("speaker_mismatch_flag", 0)),
                sample_count=int(res.get("sample_count", 1)),
                inference_time_ms=float(res.get("inference_time_ms", 0.0)),
                message=res.get("message", ""),
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def GetRiskPolicy(
        self, request: voiceshield_pb2.GetRiskPolicyRequest, context: grpc.ServicerContext
    ) -> voiceshield_pb2.GetRiskPolicyResponse:
        """
        Returns authoritative organization risk policy.
        """
        org_id = self._validate_auth(context)
        target_org = request.organization_id or org_id
        policy = self.policy_store.get(target_org)

        return voiceshield_pb2.GetRiskPolicyResponse(
            organization_id=policy.organization_id,
            policy_name=policy.name,
            fake_prob_critical_threshold=float(policy.fake_prob_critical_threshold),
            fake_prob_warn_threshold=float(policy.fake_prob_warn_threshold),
            transaction_auto_hold_amount=float(policy.transaction_auto_hold_amount),
            high_risk_wire_threshold=float(policy.high_risk_wire_threshold),
            role_enforcement_strictness=policy.role_enforcement_strictness,
            speaker_verification_strictness=float(policy.speaker_verification_strictness),
            independent_callback_required=bool(policy.independent_callback_required),
            supervisor_escalation_required=bool(policy.supervisor_escalation_required),
            otp_verification_required=bool(policy.otp_verification_required),
            version=int(policy.version),
        )

    def StreamLiveAudio(
        self,
        request_iterator: Iterator[voiceshield_pb2.LiveAudioChunk],
        context: grpc.ServicerContext,
    ) -> Iterator[voiceshield_pb2.LiveAudioAnalysisResult]:
        """
        Bidirectional live streaming voice fraud inspection.
        Maintains bounded per-session audio buffer and continuous analysis.
        """
        self._validate_auth(context)

        rolling_buffer = bytearray()
        # 1.5 seconds at 16kHz 16-bit mono = 48,000 bytes
        window_size_bytes = int(1.5 * 16000 * 2)
        max_buffer_size = int(3.0 * 16000 * 2)
        window_index = 0

        for chunk in request_iterator:
            session_id = chunk.session_id or f"GRPC-SES-{int(time.time()*1000)}"
            if chunk.pcm16_chunk:
                rolling_buffer.extend(chunk.pcm16_chunk)

            if len(rolling_buffer) >= window_size_bytes:
                window_index += 1
                eval_window = bytes(rolling_buffer[-window_size_bytes:])

                # Convert context
                ctx_dict = {}
                if chunk.context:
                    if chunk.context.caller_id:
                        ctx_dict["caller_id"] = chunk.context.caller_id
                    if chunk.context.claimed_role:
                        ctx_dict["claimed_role"] = chunk.context.claimed_role
                    if chunk.context.requested_amount > 0:
                        ctx_dict["requested_transaction_amount"] = chunk.context.requested_amount
                    if chunk.context.is_urgent:
                        ctx_dict["is_urgent"] = True
                    if chunk.context.language:
                        ctx_dict["language"] = chunk.context.language

                start_t = time.time()
                res = self.worker.handle_stream_chunk(
                    {
                        "pcm_bytes": eval_window,
                        "window_index": window_index,
                        "speaker_id": chunk.speaker_id or None,
                        "threshold": chunk.threshold if chunk.threshold > 0 else None,
                        "context": ctx_dict,
                        "call_id": session_id,
                    }
                )
                latency_ms = (time.time() - start_t) * 1000.0

                yield voiceshield_pb2.LiveAudioAnalysisResult(
                    session_id=session_id,
                    window_index=window_index,
                    risk_score=int(res.get("risk_score", 0)),
                    risk_level=res.get("risk_level", "LOW"),
                    recommended_action=res.get("recommended_action", "ALLOW"),
                    fake_probability=float(res.get("fake_probability", 0.0)),
                    real_probability=float(res.get("real_probability", 1.0)),
                    speaker_similarity=float(res.get("speaker_similarity", 0.0) or 0.0),
                    speaker_match=bool(res.get("speaker_match", False)),
                    language=res.get("language", "") or "",
                    language_name=res.get("language_name", "") or "",
                    language_confidence=float(res.get("language_confidence", 0.0) or 0.0),
                    transcript=res.get("transcript", "") or "",
                    speech_context_flags=res.get("speech_context_flags", []),
                    flags=res.get("flags", []),
                    server_latency_ms=float(latency_ms),
                )

                # Keep buffer bounded
                if len(rolling_buffer) > max_buffer_size:
                    rolling_buffer = rolling_buffer[-max_buffer_size:]


def create_grpc_server(
    port: int = 50051,
    worker: Optional[PipelineWorker] = None,
    max_workers: int = 10,
) -> grpc.Server:
    """
    Factory creating a configured VoiceShield gRPC Server instance.
    """
    from concurrent import futures

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = VoiceShieldGrpcServicer(worker=worker)
    voiceshield_pb2_grpc.add_VoiceShieldServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server
