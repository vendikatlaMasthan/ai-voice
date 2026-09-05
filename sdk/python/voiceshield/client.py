"""
VoiceShield AI — Python Client SDK
Integration client for banking backends, telecom gateways, and enterprise call-centers.
"""

import io
import json
import os
from typing import Any, Dict, List, Optional, Union

import requests

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


class VoiceShieldClient:
    """
    Client for interacting with VoiceShield AI REST and live stream endpoints.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if additional_headers:
            headers.update(additional_headers)
        return headers

    def _prepare_file_payload(
        self, audio: Union[str, bytes, io.BytesIO, Any], default_filename: str = "audio.wav"
    ):
        if isinstance(audio, (str, os.PathLike)):
            return ("file", (os.path.basename(str(audio)), open(str(audio), "rb"), "audio/wav"))
        elif isinstance(audio, bytes):
            return ("file", (default_filename, io.BytesIO(audio), "audio/wav"))
        elif hasattr(audio, "read"):
            filename = getattr(audio, "name", default_filename)
            return ("file", (os.path.basename(filename), audio, "audio/wav"))
        else:
            raise ValueError("Unsupported audio payload type. Provide a file path, bytes, or file-like object.")

    def _format_error(self, response: requests.Response, op_name: str) -> str:
        try:
            err_json = response.json()
            err_type = err_json.get("error_type")
            msg = err_json.get("message", response.text)
            if err_type and err_type not in msg:
                return f"VoiceShield {op_name} error [{err_type}] [HTTP {response.status_code}]: {msg}"
            return f"VoiceShield {op_name} error [HTTP {response.status_code}]: {msg}"
        except Exception:
            return f"VoiceShield {op_name} error [HTTP {response.status_code}]: {response.text}"

    def analyze_audio(
        self,
        audio: Union[str, bytes, io.BytesIO, Any],
        speaker_id: Optional[str] = None,
        verification_threshold: Optional[float] = None,
        organization_id: Optional[str] = None,
        caller_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        claimed_role: Optional[str] = None,
        requested_amount: Optional[float] = None,
        normal_amount: Optional[float] = None,
        transaction_reference: Optional[str] = None,
        is_urgent: Optional[bool] = None,
        urgency_reason: Optional[str] = None,
        transcript_text: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AnalyzeResult:
        """
        Sends audio to VoiceShield AI for deepfake detection, prosody inspection,
        speaker verification, and contextual risk evaluation.
        """
        url = f"{self.base_url}/api/analyze"
        data: Dict[str, Any] = {}

        if speaker_id:
            data["speaker_id"] = speaker_id
        if verification_threshold is not None:
            data["verification_threshold"] = str(verification_threshold)
        if organization_id:
            data["organization_id"] = organization_id
        if caller_id:
            data["caller_id"] = caller_id
        if contact_id:
            data["contact_id"] = contact_id
        if claimed_role:
            data["claimed_role"] = claimed_role
        if requested_amount is not None:
            data["requested_transaction_amount"] = str(requested_amount)
        if normal_amount is not None:
            data["normal_transaction_amount"] = str(normal_amount)
        if transaction_reference:
            data["transaction_reference"] = transaction_reference
        if is_urgent is not None:
            data["is_urgent"] = "true" if is_urgent else "false"
        if urgency_reason:
            data["urgency_reason"] = urgency_reason
        if transcript_text:
            data["transcript_text"] = transcript_text
        if language:
            data["language"] = language

        file_tuple = self._prepare_file_payload(audio, "analyze.wav")
        files = [file_tuple]

        response = self.session.post(
            url,
            data=data,
            files=files,
            headers=self._get_headers(),
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(self._format_error(response, "analyze_audio"))

        res_json = response.json()
        return self._parse_analyze_result(res_json)

    def enroll_speaker(
        self,
        audio: Union[str, bytes, io.BytesIO, Any],
        speaker_id: str,
        speaker_name: Optional[str] = None,
    ) -> EnrollmentResult:
        """
        Enrolls a genuine voice sample for a speaker profile.
        Incrementally updates the centroid embedding across sessions.
        """
        if not speaker_id:
            raise ValueError("Field 'speaker_id' is required for enrollment.")

        url = f"{self.base_url}/api/enroll"
        data: Dict[str, Any] = {"speaker_id": speaker_id}
        if speaker_name:
            data["speaker_name"] = speaker_name

        file_tuple = self._prepare_file_payload(audio, "enroll.wav")
        files = [file_tuple]

        response = self.session.post(
            url,
            data=data,
            files=files,
            headers=self._get_headers(),
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(self._format_error(response, "enroll_speaker"))

        data_json = response.json()
        return EnrollmentResult(
            status=data_json.get("status", "ENROLLED"),
            speaker_id=data_json.get("speaker_id", speaker_id),
            speaker_name=data_json.get("speaker_name"),
            sample_count=int(data_json.get("sample_count", 1)),
            embedding_dimension=int(data_json.get("embedding_dimension", 192)),
            created_at=float(data_json.get("created_at", 0.0)),
            updated_at=float(data_json.get("updated_at", 0.0)),
            message=data_json.get("message", ""),
            sample_rate_verified=int(data_json.get("sample_rate_verified", 16000)),
            inference_time_ms=float(data_json.get("inference_time_ms", 0.0)),
        )

    def verify_speaker(
        self,
        audio: Union[str, bytes, io.BytesIO, Any],
        speaker_id: str,
        threshold: Optional[float] = None,
    ) -> VerifyResult:
        """
        Compares query audio against enrolled speaker's multi-sample centroid.
        """
        if not speaker_id:
            raise ValueError("Field 'speaker_id' is required for verification.")

        url = f"{self.base_url}/api/verify-speaker"
        data: Dict[str, Any] = {"speaker_id": speaker_id}
        if threshold is not None:
            data["threshold"] = str(threshold)

        file_tuple = self._prepare_file_payload(audio, "verify.wav")
        files = [file_tuple]

        response = self.session.post(
            url,
            data=data,
            files=files,
            headers=self._get_headers(),
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(self._format_error(response, "verify_speaker"))

        data_json = response.json()
        return VerifyResult(
            status=data_json.get("status", "SUCCESS"),
            speaker_id=data_json.get("speaker_id", speaker_id),
            similarity_score=float(data_json.get("similarity_score", 0.0)),
            threshold=float(data_json.get("threshold", 0.70)),
            match=bool(data_json.get("match", False)),
            speaker_mismatch_flag=int(data_json.get("speaker_mismatch_flag", 0)),
            sample_count=int(data_json.get("sample_count", 1)),
            inference_time_ms=float(data_json.get("inference_time_ms", 0.0)),
            message=data_json.get("message", ""),
        )

    def get_speakers(self) -> List[EnrolledSpeaker]:
        """
        Retrieves all registered speaker profiles from the store.
        """
        url = f"{self.base_url}/api/speakers"
        response = self.session.get(
            url,
            headers=self._get_headers({"Accept": "application/json"}),
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(f"VoiceShield get_speakers error [HTTP {response.status_code}]: {response.text}")

        res_json = response.json()
        raw_list = res_json.get("speakers", [])
        speakers: List[EnrolledSpeaker] = []
        for item in raw_list:
            speakers.append(
                EnrolledSpeaker(
                    speaker_id=item["speaker_id"],
                    speaker_name=item.get("speaker_name"),
                    dimension=int(item.get("dimension", 192)),
                    sample_count=int(item.get("sample_count", 1)),
                    created_at=float(item.get("created_at", 0.0)),
                    updated_at=float(item.get("updated_at", item.get("created_at", 0.0))),
                )
            )
        return speakers

    def get_policy(self, organization_id: Optional[str] = None) -> OrganizationPolicy:
        """
        Retrieves the authoritative organization security policy.
        """
        url = f"{self.base_url}/api/policy"
        params = {}
        if organization_id:
            params["organization_id"] = organization_id

        response = self.session.get(
            url,
            params=params,
            headers=self._get_headers({"Accept": "application/json"}),
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(f"VoiceShield get_policy error [HTTP {response.status_code}]: {response.text}")

        res_json = response.json()
        pol_data = res_json.get("policy", res_json)
        return OrganizationPolicy(
            organization_id=pol_data.get("organization_id", ""),
            name=pol_data.get("name", "Default Policy"),
            fake_prob_critical_threshold=float(pol_data.get("fake_prob_critical_threshold", 0.85)),
            fake_prob_warn_threshold=float(pol_data.get("fake_prob_warn_threshold", 0.65)),
            transaction_auto_hold_amount=float(pol_data.get("transaction_auto_hold_amount", 50000.0)),
            high_risk_wire_threshold=float(pol_data.get("high_risk_wire_threshold", 10000.0)),
            role_enforcement_strictness=pol_data.get("role_enforcement_strictness", "STRICT"),
            speaker_verification_strictness=float(pol_data.get("speaker_verification_strictness", 0.70)),
            independent_callback_required=bool(pol_data.get("independent_callback_required", True)),
            supervisor_escalation_required=bool(pol_data.get("supervisor_escalation_required", True)),
            otp_verification_required=bool(pol_data.get("otp_verification_required", True)),
            version=int(pol_data.get("version", 1)),
        )

    def get_health(self) -> Dict[str, Any]:
        """
        Checks health status and model readiness.
        """
        url = f"{self.base_url}/api/health"
        response = self.session.get(
            url,
            headers=self._get_headers({"Accept": "application/json"}),
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"VoiceShield health error [HTTP {response.status_code}]: {response.text}")
        return response.json()

    def _parse_analyze_result(self, raw: Dict[str, Any]) -> AnalyzeResult:
        df_raw = raw.get("deepfake_detection", {})
        df_res = DeepfakeResult(
            prediction=df_raw.get("prediction", "UNKNOWN"),
            fake_probability=float(df_raw.get("fake_probability", 0.0)),
            real_probability=float(df_raw.get("real_probability", 0.0)),
            model_type=df_raw.get("model_type", "Wav2Vec2"),
            inference_time_ms=float(df_raw.get("inference_time_ms", 0.0)),
        )

        spk_raw = raw.get("speaker_verification", {})
        spk_res = SpeakerVerificationResult(
            status=spk_raw.get("status", "NOT_EVALUATED"),
            speaker_id=spk_raw.get("speaker_id"),
            similarity_score=float(spk_raw["similarity_score"]) if spk_raw.get("similarity_score") is not None else None,
            threshold=float(spk_raw["threshold"]) if spk_raw.get("threshold") is not None else None,
            is_match=spk_raw.get("is_match"),
            speaker_mismatch_flag=spk_raw.get("speaker_mismatch_flag"),
            sample_count=spk_raw.get("sample_count"),
            inference_time_ms=spk_raw.get("inference_time_ms"),
        )

        rs_raw = raw.get("risk_signals", {})
        rs_res = RiskSignalsResult(
            fake_probability=float(rs_raw.get("fake_probability", 0.0)),
            speaker_mismatch=int(rs_raw.get("speaker_mismatch", 0)),
            acoustic_anomaly=float(rs_raw.get("acoustic_anomaly", 0.0)),
            context_flag=int(rs_raw.get("context_flag", 0)),
            speaker_verification_status=rs_raw.get("speaker_verification_status", "NOT_EVALUATED"),
            acoustic_model_status=rs_raw.get("acoustic_model_status", "ACTIVE"),
            prosody_reasons=rs_raw.get("prosody_reasons", []),
        )

        am_raw = raw.get("audio_metadata", {})
        am_res = AudioMetadataResult(
            sample_rate=int(am_raw.get("sample_rate", 16000)),
            original_duration_sec=float(am_raw.get("original_duration_sec", 0.0)),
            processed_duration_sec=float(am_raw.get("processed_duration_sec", 0.0)),
            estimated_snr_db=float(am_raw.get("estimated_snr_db", 0.0)),
            rms_db=float(am_raw.get("rms_db", 0.0)),
        )

        prosody_res = None
        if "prosody_analysis" in raw and raw["prosody_analysis"]:
            p_raw = raw["prosody_analysis"]
            prosody_res = ProsodyAnalysisResult(
                acoustic_anomaly=float(p_raw.get("acoustic_anomaly", 0.0)),
                features=p_raw.get("features", {}),
                anomaly_reasons=p_raw.get("anomaly_reasons", []),
                status=p_raw.get("status", "COMPLETED"),
            )

        asr_res = None
        if "asr_analysis" in raw and raw["asr_analysis"]:
            a_raw = raw["asr_analysis"]
            asr_res = ASRAnalysisResult(
                language=a_raw.get("language", "en"),
                language_name=a_raw.get("language_name", "English"),
                language_confidence=float(a_raw.get("language_confidence", 0.0)),
                transcript=a_raw.get("transcript", ""),
                is_speech=bool(a_raw.get("is_speech", False)),
                inference_time_ms=float(a_raw.get("inference_time_ms", 0.0)),
                keywords_detected=a_raw.get("keywords_detected", []),
                speech_context_flags=a_raw.get("speech_context_flags", []),
            )

        vs_res = None
        if "verification_session" in raw and raw["verification_session"]:
            v_raw = raw["verification_session"]
            vs_res = VerificationSessionResult(
                call_id=v_raw.get("call_id", raw.get("call_id", "")),
                status=v_raw.get("status", "PENDING"),
                recommended_action=v_raw.get("recommended_action", "ALLOW"),
                risk_score=int(v_raw.get("risk_score", 0)),
                risk_level=v_raw.get("risk_level", "LOW"),
                is_held=bool(v_raw.get("is_held", False)),
                hold_reason=v_raw.get("hold_reason"),
                selected_method=v_raw.get("selected_method"),
                in_progress_step=v_raw.get("in_progress_step"),
                created_at=float(v_raw.get("created_at", 0.0)),
                updated_at=float(v_raw.get("updated_at", 0.0)),
            )

        return AnalyzeResult(
            call_id=raw.get("call_id", ""),
            risk_score=int(raw.get("risk_score", 0)),
            risk_level=raw.get("risk_level", "LOW"),
            recommended_action=raw.get("recommended_action", "ALLOW"),
            deepfake_detection=df_res,
            speaker_verification=spk_res,
            prosody_analysis=prosody_res,
            risk_signals=rs_res,
            flags=raw.get("flags", []),
            audio_metadata=am_res,
            language=raw.get("language"),
            language_name=raw.get("language_name"),
            language_confidence=raw.get("language_confidence"),
            transcript=raw.get("transcript"),
            speech_context_flags=raw.get("speech_context_flags", []),
            asr_analysis=asr_res,
            verification_session=vs_res,
            pipeline_latency_ms=raw.get("pipeline_latency_ms"),
            raw_response=raw,
        )
