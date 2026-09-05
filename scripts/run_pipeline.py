"""
VoiceShield Pipeline Runner CLI.
Bridges backend REST/server handlers to the exact Phase 1–5 Python core implementation.
Preserves all Phase 1–5 algorithms, mathematical feature extractors, and risk engines.
"""

import argparse
import base64
import json
import math
import os
import struct
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
import uuid

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SPEAKER_STORE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "speakers.json")

from app.audio.preprocessing import (
    AudioPreprocessor,
    PreprocessedAudio,
)
from app.audio.prosody import (
    ProsodyAnalysisResult,
    ProsodyAnalyzer,
    ProsodyResult,
)
from app.utils.audio_utils import (
    AudioCorruptError,
    AudioError,
    AudioSilentError,
    AudioTooLongError,
    AudioTooShortError,
    FileNotFoundAudioError,
    UnsupportedFormatError,
    calculate_rms,
    calculate_snr_estimate,
    linear_to_db,
)
from app.models.asr import SpeechRecognizer, ASRResult
from app.models.detector import VoiceCloneDetector
from app.models.speaker_verifier import (
    DatabaseSpeakerStore,
    InMemorySpeakerStore,
    PretrainedECAPASpeakerVerifier,
    SpeakerEmbedding,
)
from app.risk.context import CallContext, resolve_speech_profile
from app.risk.scoring import VoiceShieldRiskEngine
from app.risk.verification import SecondaryVerificationStateMachine

def extract_call_context(args: dict) -> CallContext:
    """
    Helper to extract CallContext.
    Enforces strict security hierarchy: If a server-enriched/sanitized context
    dictionary is present, security-critical fields are read exclusively from
    context and cannot be overridden by loose root-level request arguments.
    """
    raw_context = args.get("context", {}) or {}
    if isinstance(raw_context, str):
        try:
            raw_context = json.loads(raw_context)
        except Exception:
            raw_context = {}

    has_enriched_context = isinstance(raw_context, dict) and len(raw_context) > 0

    if has_enriched_context:
        # Protected security-sensitive fields come EXCLUSIVELY from raw_context
        org_id = raw_context.get("organization_id")
        contact_id = raw_context.get("contact_id")
        contact_name = raw_context.get("contact_name")
        contact_role = raw_context.get("contact_role")
        is_verified = raw_context.get("is_verified")
        flag_reason = raw_context.get("flag_reason")
        context_source = raw_context.get("context_source", "SUPABASE_INTELLIGENCE")
        context_available = raw_context.get("context_available", True)

        # Boolean security fields
        is_recog = raw_context.get("is_caller_recognized", True)
        if isinstance(is_recog, str):
            is_recog = is_recog.lower() == "true"

        is_flagged = raw_context.get("is_previously_flagged", False)
        if isinstance(is_flagged, str):
            is_flagged = is_flagged.lower() == "true"

        claimed_role = raw_context.get("claimed_role") or args.get("claimed_role")

        if "role_mismatch" in raw_context:
            role_mis = raw_context.get("role_mismatch")
            if isinstance(role_mis, str):
                role_mis = role_mis.lower() == "true"
        else:
            if claimed_role and contact_role and str(claimed_role).strip().lower() != str(contact_role).strip().lower():
                role_mis = True
            else:
                role_mis = False

        has_fraud_hist = raw_context.get("has_prior_fraud_history", False)
        if isinstance(has_fraud_hist, str):
            has_fraud_hist = has_fraud_hist.lower() == "true"

        fraud_cnt = int(raw_context.get("fraud_history_count", 0) or 0)
        fraud_types = raw_context.get("recent_fraud_types", []) or []

        hold_amt = raw_context.get("transaction_auto_hold_amount")
        hold_amt_val = float(hold_amt) if hold_amt is not None and str(hold_amt).strip() != "" else None

        # Authoritative Organization Policy extraction (Feature 3)
        policy = raw_context.get("policy") if isinstance(raw_context.get("policy"), dict) else {}
        fake_crit_val = float(policy.get("fake_prob_critical_threshold", 0.85))
        fake_warn_val = float(policy.get("fake_prob_warn_threshold", 0.50))
        spk_strict_val = float(policy.get("speaker_verification_strictness", 0.65))
        acoust_sens_val = float(policy.get("acoustic_anomaly_sensitivity", 0.70))
        step_up_val = bool(policy.get("step_up_verification_required", True))
        auto_block_val = bool(policy.get("auto_block_on_critical_deepfake", True))

        if policy.get("transaction_auto_hold_amount") is not None and str(policy.get("transaction_auto_hold_amount")).strip() != "":
            hold_amt_val = float(policy.get("transaction_auto_hold_amount"))

        # User/Session intent fields (can fallback to args if not in raw_context)
        caller_id = raw_context.get("caller_id") or args.get("caller_id")
        claimed_role = raw_context.get("claimed_role") or args.get("claimed_role")

        req_amt = (
            raw_context.get("requested_amount")
            if raw_context.get("requested_amount") is not None
            else raw_context.get("requested_transaction_amount")
            if raw_context.get("requested_transaction_amount") is not None
            else args.get("requested_amount")
            if args.get("requested_amount") is not None
            else args.get("requested_transaction_amount")
        )
        req_amt_val = float(req_amt) if req_amt is not None and str(req_amt).strip() != "" else None

        norm_amt = (
            raw_context.get("normal_amount")
            if raw_context.get("normal_amount") is not None
            else raw_context.get("normal_transaction_amount")
            if raw_context.get("normal_transaction_amount") is not None
            else args.get("normal_amount")
            if args.get("normal_amount") is not None
            else args.get("normal_transaction_amount")
        )
        norm_amt_val = float(norm_amt) if norm_amt is not None and str(norm_amt).strip() != "" else None

        tx_ref = raw_context.get("transaction_reference") or args.get("transaction_reference")

        is_urg = raw_context.get("is_urgent") if raw_context.get("is_urgent") is not None else args.get("is_urgent", False)
        if isinstance(is_urg, str):
            is_urg = is_urg.lower() == "true"

        urg_reason = raw_context.get("urgency_reason") or args.get("urgency_reason")
        transcript = raw_context.get("transcript_text") or args.get("transcript_text")
        susp_keys = raw_context.get("suspicious_keywords_found") or args.get("suspicious_keywords_found", []) or []

        # Multilingual / Indian Speech Metadata (Non-Authoritative)
        sel_lang = (
            raw_context.get("selected_language")
            or raw_context.get("language")
            or args.get("selected_language")
            or args.get("language")
            or "Auto Detect"
        )
        det_lang = raw_context.get("detected_language") or args.get("detected_language")
        lang_conf = raw_context.get("language_confidence") or args.get("language_confidence")
        lang_conf_val = float(lang_conf) if lang_conf is not None and str(lang_conf).strip() != "" else None
        accent_reg = (
            raw_context.get("accent_region")
            or raw_context.get("accent_profile")
            or args.get("accent_region")
            or args.get("accent_profile")
        )
        trans_lang = raw_context.get("transcript_language") or args.get("transcript_language")

        return CallContext(
            caller_id=caller_id,
            is_caller_recognized=bool(is_recog),
            is_previously_flagged=bool(is_flagged),
            claimed_role=claimed_role,
            requested_transaction_amount=req_amt_val,
            normal_transaction_amount=norm_amt_val,
            is_urgent=bool(is_urg),
            urgency_reason=urg_reason,
            transcript_text=transcript,
            suspicious_keywords_found=susp_keys,
            organization_id=org_id,
            contact_id=contact_id,
            contact_name=contact_name,
            contact_role=contact_role,
            is_verified=is_verified,
            role_mismatch=bool(role_mis),
            flag_reason=flag_reason,
            transaction_reference=tx_ref,
            transaction_auto_hold_amount=hold_amt_val,
            has_prior_fraud_history=bool(has_fraud_hist),
            fraud_history_count=fraud_cnt,
            recent_fraud_types=fraud_types,
            context_source=context_source,
            context_available=context_available,
            fake_prob_critical_threshold=fake_crit_val,
            fake_prob_warn_threshold=fake_warn_val,
            speaker_verification_strictness=spk_strict_val,
            acoustic_anomaly_sensitivity=acoust_sens_val,
            step_up_verification_required=step_up_val,
            auto_block_on_critical_deepfake=auto_block_val,
            selected_language=sel_lang,
            language=raw_context.get("language") or args.get("language") or sel_lang,
            detected_language=det_lang,
            language_confidence=lang_conf_val,
            accent_region=accent_reg,
            accent_profile=accent_reg,
            transcript_language=trans_lang,
        )

    # Legacy flat args fallback (only when no nested context was provided)
    req_amt = args.get("requested_amount") if args.get("requested_amount") is not None else args.get("requested_transaction_amount")
    req_amt_val = float(req_amt) if req_amt is not None and str(req_amt).strip() != "" else None

    norm_amt = args.get("normal_amount") if args.get("normal_amount") is not None else args.get("normal_transaction_amount")
    norm_amt_val = float(norm_amt) if norm_amt is not None and str(norm_amt).strip() != "" else None

    hold_amt = args.get("transaction_auto_hold_amount")
    hold_amt_val = float(hold_amt) if hold_amt is not None and str(hold_amt).strip() != "" else None

    is_recog = args.get("is_caller_recognized", True)
    if isinstance(is_recog, str):
        is_recog = is_recog.lower() == "true"

    is_flagged = args.get("is_previously_flagged", False)
    if isinstance(is_flagged, str):
        is_flagged = is_flagged.lower() == "true"

    is_urg = args.get("is_urgent", False)
    if isinstance(is_urg, str):
        is_urg = is_urg.lower() == "true"

    role_mis = args.get("role_mismatch", False)
    if isinstance(role_mis, str):
        role_mis = role_mis.lower() == "true"

    has_fraud_hist = args.get("has_prior_fraud_history", False)
    if isinstance(has_fraud_hist, str):
        has_fraud_hist = has_fraud_hist.lower() == "true"

    fraud_cnt = int(args.get("fraud_history_count", 0) or 0)
    fraud_types = args.get("recent_fraud_types", []) or []

    sel_lang = args.get("selected_language") or args.get("language") or "Auto Detect"
    det_lang = args.get("detected_language")
    lang_conf = args.get("language_confidence")
    lang_conf_val = float(lang_conf) if lang_conf is not None and str(lang_conf).strip() != "" else None
    accent_reg = args.get("accent_region") or args.get("accent_profile")
    trans_lang = args.get("transcript_language")

    return CallContext(
        caller_id=args.get("caller_id"),
        is_caller_recognized=bool(is_recog),
        is_previously_flagged=bool(is_flagged),
        claimed_role=args.get("claimed_role"),
        requested_transaction_amount=req_amt_val,
        normal_transaction_amount=norm_amt_val,
        is_urgent=bool(is_urg),
        urgency_reason=args.get("urgency_reason"),
        transcript_text=args.get("transcript_text"),
        suspicious_keywords_found=args.get("suspicious_keywords_found", []) or [],
        organization_id=args.get("organization_id"),
        contact_id=args.get("contact_id"),
        contact_name=args.get("contact_name"),
        contact_role=args.get("contact_role"),
        is_verified=args.get("is_verified"),
        role_mismatch=bool(role_mis),
        flag_reason=args.get("flag_reason"),
        transaction_reference=args.get("transaction_reference"),
        transaction_auto_hold_amount=hold_amt_val,
        has_prior_fraud_history=bool(has_fraud_hist),
        fraud_history_count=fraud_cnt,
        recent_fraud_types=fraud_types,
        context_source=args.get("context_source", "DEFAULT"),
        context_available=args.get("context_available", True),
        selected_language=sel_lang,
        language=args.get("language") or sel_lang,
        detected_language=det_lang,
        language_confidence=lang_conf_val,
        accent_region=accent_reg,
        accent_profile=accent_reg,
        transcript_language=trans_lang,
    )


def load_persistent_store() -> DatabaseSpeakerStore:
    """
    Returns the persistent SQLite database-backed speaker store.
    Directly persists 192-D biometric vectors with multi-tenant scoping.
    """
    return DatabaseSpeakerStore()


def save_persistent_store(store: Any):
    """
    DatabaseSpeakerStore automatically commits records directly to SQLite.
    If an in-memory store is passed, saves to file as fallback.
    """
    if isinstance(store, DatabaseSpeakerStore):
        return
    try:
        data = {}
        for spk_id in store.list_speakers():
            emb = store.get(spk_id)
            if emb:
                data[spk_id] = {
                    "speaker_id": emb.speaker_id,
                    "embedding": emb.embedding,
                    "created_at": emb.created_at,
                    "updated_at": emb.updated_at,
                    "sample_count": emb.sample_count,
                    "dimension": emb.dimension,
                    "metadata": emb.metadata,
                }
        with open(SPEAKER_STORE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning saving speaker store: {e}\n")


def cmd_health():
    res = {
        "status": "ok",
        "service": "VoiceShield API",
        "version": "1.0.0 (Phase 5)",
        "supported_models": [
            "garystafford/wav2vec2-deepfake-voice-detector",
            "speechbrain/spkrec-ecapa-voxceleb",
        ],
        "hardware_profile": "8GB RAM + NVIDIA MX450 / CPU Optimized",
        "phases_active": [1, 2, 3, 4, 5],
    }
    print(json.dumps(res))


class PipelineWorker:
    """
    Persistent inference worker that keeps ML models in memory.
    Prevents repeated expensive disk and weight loading per analysis request.
    """

    def __init__(self):
        self.preprocessor = AudioPreprocessor()
        self.prosody_analyzer = ProsodyAnalyzer()
        self.detector = VoiceCloneDetector()
        self.detector.load()
        self.speaker_verifier = PretrainedECAPASpeakerVerifier()
        self.speaker_verifier.load_model()
        self.speaker_store = load_persistent_store()
        self.speech_recognizer = SpeechRecognizer.get_instance()
        self.risk_engine = VoiceShieldRiskEngine()
        self.model_load_count = 1
        self._warmup()

    def _warmup(self) -> None:
        """
        Performs a safe, one-time in-memory warmup inference pass across initialized models
        to eliminate lazy initialization latency before live streaming begins.
        """
        t0 = time.perf_counter()
        try:
            # 1.0s valid in-memory sine tone (16kHz mono, 16000 samples)
            warmup_waveform = [0.1 * math.sin(2.0 * math.pi * 220.0 * i / 16000.0) for i in range(16000)]
            warmup_audio = PreprocessedAudio(
                waveform=warmup_waveform,
                sample_rate=16000,
                original_duration_sec=1.0,
                processed_duration_sec=1.0,
                rms_energy_db=-20.0,
                estimated_snr_db=30.0,
                channels=1,
                metadata={"warmup": True},
            )
            # Warmup Wav2Vec2 detector
            if hasattr(self, "detector") and self.detector is not None:
                self.detector.predict(warmup_audio)

            # Warmup ProsodyAnalyzer
            if hasattr(self, "prosody_analyzer") and self.prosody_analyzer is not None:
                self.prosody_analyzer.analyze(warmup_audio)

            # Warmup SpeakerVerifier embedding path
            if hasattr(self, "speaker_verifier") and self.speaker_verifier is not None:
                self.speaker_verifier.extract_embedding(warmup_audio, speaker_id="__warmup__")

            # Warmup SpeechRecognizer (Whisper-Tiny)
            if hasattr(self, "speech_recognizer") and self.speech_recognizer is not None:
                self.speech_recognizer.transcribe(warmup_audio, max_new_tokens=16)

            warmup_ms = (time.perf_counter() - t0) * 1000.0
            sys.stderr.write(f"[PipelineWorker] One-time model warmup (Wav2Vec2 + ECAPA + Whisper) completed in {warmup_ms:.1f}ms.\n")
        except Exception as err:
            # Fail gracefully without blocking daemon startup
            sys.stderr.write(f"[PipelineWorker:WarmupWarning] Warmup skipped: {err}\n")

    def sync_store(self):
        """Synchronize in-memory speaker store with persistent storage."""
        self.speaker_store = load_persistent_store()

    def handle_health(self) -> dict:
        return {
            "status": "ok",
            "service": "VoiceShield API",
            "version": "1.0.0 (Phase 5)",
            "supported_models": [
                "garystafford/wav2vec2-deepfake-voice-detector",
                "speechbrain/spkrec-ecapa-voxceleb",
            ],
            "hardware_profile": "8GB RAM + NVIDIA MX450 / CPU Optimized",
            "phases_active": [1, 2, 3, 4, 5],
            "persistent_daemon": True,
            "model_load_count": self.model_load_count,
        }

    def handle_list_speakers(self) -> dict:
        self.sync_store()
        speakers = []
        for spk_id, emb in self.speaker_store._store.items():
            speakers.append({
                "speaker_id": emb.speaker_id,
                "speaker_name": emb.metadata.get("speaker_name"),
                "sample_count": emb.sample_count,
                "dimension": emb.dimension,
                "created_at": emb.created_at,
                "updated_at": emb.updated_at,
            })
        return {"status": "ok", "speakers": speakers}

    def handle_analyze(self, args: dict) -> dict:
        audio_path = args.get("file")
        speaker_id = args.get("speaker_id")
        threshold = args.get("threshold")
        caller_id = args.get("caller_id")
        is_caller_recognized = args.get("is_caller_recognized", True)
        is_previously_flagged = args.get("is_previously_flagged", False)
        claimed_role = args.get("claimed_role")
        requested_amount = args.get("requested_amount")
        normal_amount = args.get("normal_amount")
        is_urgent = args.get("is_urgent", False)
        urgency_reason = args.get("urgency_reason")
        transcript_text = args.get("transcript_text")
        raw_acoustic_override = args.get("acoustic_anomaly")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundAudioError(f"Audio file not found: {audio_path}")

        preprocessed = self.preprocessor.process(audio_path)
        prediction_result = self.detector.predict(preprocessed)
        prosody_result = self.prosody_analyzer.analyze(preprocessed)

        # Use explicit override if passed and > 0.0, otherwise use calculated dynamic acoustic anomaly
        if raw_acoustic_override is not None and float(raw_acoustic_override) > 0.0:
            acoustic_anomaly = float(raw_acoustic_override)
        else:
            acoustic_anomaly = prosody_result.acoustic_anomaly

        call_context = extract_call_context(args)
        effective_speaker_threshold = (
            float(threshold) if threshold is not None and str(threshold).strip() != ""
            else float(call_context.speaker_verification_strictness)
        )

        self.sync_store()
        speaker_mismatch_signal = 0
        speaker_verification_status = "NOT_EVALUATED (No speaker_id supplied)"
        speaker_detail = {
            "status": "NOT_EVALUATED",
            "speaker_id": speaker_id,
            "similarity_score": None,
            "threshold": None,
            "is_match": None,
            "speaker_mismatch_flag": None,
            "inference_time_ms": None,
        }

        if speaker_id:
            enrolled = self.speaker_store.get(speaker_id)
            if enrolled:
                ver_res = self.speaker_verifier.verify(
                    audio=preprocessed,
                    enrolled_embedding=enrolled,
                    threshold=effective_speaker_threshold,
                )
                speaker_mismatch_signal = ver_res.speaker_mismatch_flag
                speaker_verification_status = "EVALUATED (MATCH)" if ver_res.is_match else "EVALUATED (MISMATCH)"
                speaker_detail = {
                    "status": "EVALUATED",
                    "speaker_id": speaker_id,
                    "similarity_score": round(ver_res.similarity_score, 4),
                    "threshold": round(ver_res.threshold, 4),
                    "is_match": ver_res.is_match,
                    "speaker_mismatch_flag": ver_res.speaker_mismatch_flag,
                    "sample_count": enrolled.sample_count,
                    "inference_time_ms": round(ver_res.inference_time_ms, 2),
                }
            else:
                speaker_verification_status = f"NOT_ENROLLED (Speaker '{speaker_id}' not found in registry)"
                speaker_detail = {
                    "status": "NOT_ENROLLED",
                    "speaker_id": speaker_id,
                    "similarity_score": None,
                    "threshold": None,
                    "is_match": None,
                    "speaker_mismatch_flag": None,
                    "inference_time_ms": None,
                }

        # 4. Local Multilingual Speech Recognition (ASR) & Language Identification
        asr_res = ASRResult()
        try:
            if hasattr(self, "speech_recognizer") and self.speech_recognizer is not None:
                asr_res = self.speech_recognizer.transcribe(preprocessed, sample_rate=preprocessed.sample_rate)
        except Exception as e:
            sys.stderr.write(f"[PipelineWorker:ASRError] {e}\n")

        call_context = extract_call_context(args)

        # Merge speech-derived transcript and keywords into context
        if asr_res.is_speech and asr_res.transcript:
            if not call_context.transcript_text:
                call_context.transcript_text = asr_res.transcript
            if asr_res.keywords_detected:
                for kw in asr_res.keywords_detected:
                    if kw not in call_context.suspicious_keywords_found:
                        call_context.suspicious_keywords_found.append(kw)

        risk_assessment = self.risk_engine.evaluate(
            fake_probability=prediction_result.fake_probability,
            speaker_mismatch=speaker_mismatch_signal,
            acoustic_anomaly=acoustic_anomaly,
            context=call_context,
            prosody_reasons=prosody_result.anomaly_reasons,
        )

        call_id = f"CALL-{uuid.uuid4().hex[:8].upper()}"

        verification_session = SecondaryVerificationStateMachine.initialize_session(
            call_id=call_id,
            recommended_action=risk_assessment.recommended_action,
            risk_score=risk_assessment.risk_score,
            risk_level=risk_assessment.risk_level,
            context=call_context,
            flags=risk_assessment.flags,
        )

        speech_prof = resolve_speech_profile(
            selected_language=call_context.selected_language or call_context.language,
            detected_language=asr_res.language_name if asr_res.is_speech else call_context.detected_language,
            language_confidence=asr_res.language_confidence if asr_res.is_speech else call_context.language_confidence,
            transcript_text=call_context.transcript_text or asr_res.transcript,
            transcript_language=asr_res.language if asr_res.is_speech else call_context.transcript_language,
        )

        return {
            "call_id": call_id,
            "risk_score": risk_assessment.risk_score,
            "risk_level": risk_assessment.risk_level,
            "verification_session": verification_session.to_dict(),
            "speech_profile": speech_prof,
            "language_profile": speech_prof,
            "language": asr_res.language,
            "language_name": asr_res.language_name,
            "language_confidence": asr_res.language_confidence,
            "transcript": asr_res.transcript or call_context.transcript_text or "",
            "speech_context_flags": asr_res.speech_context_flags,
            "asr_analysis": asr_res.to_dict(),
            "deepfake_detection": {
                "prediction": prediction_result.prediction,
                "fake_probability": round(prediction_result.fake_probability, 4),
                "real_probability": round(prediction_result.real_probability, 4),
                "model_type": prediction_result.metadata.get("model_type", "Wav2Vec2"),
                "model_id": prediction_result.metadata.get("model_id", "garystafford/wav2vec2-deepfake-voice-detector"),
                "inference_time_ms": round(prediction_result.metadata.get("inference_time_ms", 0.0), 2),
                "disclaimer": prediction_result.metadata.get("disclaimer"),
            },
            "speaker_verification": speaker_detail,
            "prosody_analysis": prosody_result.to_dict(),
            "risk_signals": {
                "fake_probability": round(prediction_result.fake_probability, 4),
                "speaker_mismatch": speaker_mismatch_signal,
                "acoustic_anomaly": round(float(acoustic_anomaly), 4),
                "context_flag": risk_assessment.signals.get("context_flag", 0.0),
                "speaker_verification_status": speaker_verification_status,
                "acoustic_model_status": "DETERMINISTIC_PROSODY_ANALYSIS",
                "prosody_reasons": prosody_result.anomaly_reasons,
            },
            "context_intelligence": {
                "context_source": call_context.context_source,
                "context_available": call_context.context_available,
                "organization_id": call_context.organization_id,
                "contact_id": call_context.contact_id,
                "contact_name": call_context.contact_name,
                "contact_role": call_context.contact_role,
                "is_caller_recognized": call_context.is_caller_recognized,
                "is_previously_flagged": call_context.is_previously_flagged,
                "is_verified": call_context.is_verified,
                "role_mismatch": call_context.role_mismatch,
                "has_prior_fraud_history": call_context.has_prior_fraud_history,
                "fraud_history_count": call_context.fraud_history_count,
            },
            "flags": risk_assessment.flags,
            "prosody_reasons": prosody_result.anomaly_reasons,
            "prosody_metrics": {k: round(float(v), 4) for k, v in prosody_result.features.items()},
            "recommended_action": risk_assessment.recommended_action,
            "audio_metadata": {
                "sample_rate": preprocessed.sample_rate,
                "original_duration_sec": round(preprocessed.original_duration_sec, 2),
                "processed_duration_sec": round(preprocessed.processed_duration_sec, 2),
                "estimated_snr_db": round(preprocessed.estimated_snr_db, 2),
                "rms_db": round(preprocessed.rms_energy_db, 2),
            },
        }

    def handle_stream_chunk(self, args: dict) -> dict:
        """
        Processes a live streaming microphone audio window (~1.5–2.0s) in-memory without disk I/O.
        Reuses loaded Wav2Vec2 detector, ProsodyAnalyzer, Speaker Verifier, and Risk Engine.
        """
        start_time = time.perf_counter()
        samples: List[float] = []

        if "pcm_bytes_b64" in args and args["pcm_bytes_b64"]:
            raw_bytes = base64.b64decode(args["pcm_bytes_b64"])
            total_samples = len(raw_bytes) // 2
            if total_samples > 0:
                ints = struct.unpack(f"<{total_samples}h", raw_bytes[: total_samples * 2])
                samples = [float(v) / 32768.0 for v in ints]
        elif "samples" in args and isinstance(args["samples"], list):
            samples = [float(x) for x in args["samples"]]
        elif "file" in args and args["file"] and os.path.exists(args["file"]):
            preprocessed_temp = self.preprocessor.process(args["file"])
            samples = preprocessed_temp.waveform
        else:
            raise ValueError("No audio payload provided. Supply 'pcm_bytes_b64', 'samples', or 'file'.")

        if not samples or len(samples) < 8000:  # Minimum 0.5s at 16kHz
            raise AudioTooShortError(len(samples) / 16000.0, 0.5)

        sr = 16000
        duration_sec = len(samples) / float(sr)

        rms = calculate_rms(samples)
        rms_db = linear_to_db(rms)
        peak_amp = max(abs(s) for s in samples) if samples else 0.0
        snr_db = calculate_snr_estimate(samples)

        # Silence / Background Voice Activity Gate
        # Consistent with AudioConfig.silence_threshold_db (-45.0 dB)
        silence_threshold_db = getattr(self.preprocessor.config, "silence_threshold_db", -45.0)
        is_silence = (rms_db < silence_threshold_db) and (peak_amp < 0.005)

        if is_silence:
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0
            call_id = args.get("call_id") or f"LIVE-{uuid.uuid4().hex[:6].upper()}"
            return {
                "status": "SILENCE_OR_BACKGROUND",
                "call_id": call_id,
                "window_index": args.get("window_index", 0),
                "fake_probability": 0.0,
                "real_probability": 0.0,
                "acoustic_anomaly": 0.0,
                "risk_score": 0,
                "risk_level": "LOW",
                "recommended_action": "ALLOW",
                "flags": ["VAD_SILENCE_WINDOW"],
                "language": "unknown",
                "language_name": "Silence",
                "language_confidence": 0.0,
                "transcript": "",
                "speech_context_flags": [],
                "asr_analysis": {
                    "language": "unknown",
                    "language_name": "Silence",
                    "language_confidence": 0.0,
                    "transcript": "",
                    "is_speech": False,
                    "inference_time_ms": 0.0,
                    "keywords_detected": [],
                    "speech_context_flags": [],
                },
                "prosody_reasons": ["Background silence / no active speech detected"],
                "prosody_metrics": {
                    "f0_mean_hz": 0.0,
                    "f0_std_hz": 0.0,
                    "f0_cv": 0.0,
                    "energy_mean": 0.0,
                    "energy_std": 0.0,
                    "energy_dynamics": 0.0,
                    "zcr_mean": 0.0,
                    "spectral_centroid_hz": 0.0,
                    "spectral_spread_hz": 0.0,
                    "hf_energy_ratio": 0.0,
                    "speech_ratio": 0.0,
                    "syllable_rate_proxy": 0.0,
                },
                "prosody_analysis": {
                    "acoustic_anomaly": 0.0,
                    "anomaly_reasons": ["Background silence / no active speech detected"],
                    "features": {},
                    "is_anomalous": False,
                },
                "deepfake_detection": {
                    "prediction": "SILENCE",
                    "fake_probability": 0.0,
                    "real_probability": 0.0,
                    "model_type": "VoiceActivityGated",
                    "status": "SILENCE_NO_SPEECH_DETECTED",
                    "inference_time_ms": 0.0,
                },
                "speaker_verification": {
                    "status": "SKIPPED_SILENCE",
                    "speaker_id": args.get("speaker_id"),
                    "similarity_score": None,
                    "threshold": None,
                    "is_match": None,
                    "speaker_mismatch_flag": 0,
                    "inference_time_ms": 0.0,
                },
                "audio_metrics": {
                    "window_duration_sec": round(duration_sec, 2),
                    "sample_rate": sr,
                    "estimated_snr_db": round(snr_db, 2),
                    "rms_db": round(rms_db, 2),
                    "peak_amplitude": round(peak_amp, 4),
                    "vad_status": "SILENCE_OR_BACKGROUND",
                },
                "pipeline_latency_ms": round(total_latency_ms, 2),
            }

        # Apply standard peak amplitude normalization matching AudioPreprocessor
        if peak_amp > 1e-5 and getattr(self.preprocessor.config, "normalize_amplitude", True):
            norm_target = getattr(self.preprocessor.config, "target_peak_amplitude", 0.95)
            scale = norm_target / peak_amp
            samples = [min(1.0, max(-1.0, s * scale)) for s in samples]
            peak_amp = max(abs(s) for s in samples)
            rms = calculate_rms(samples)
            rms_db = linear_to_db(rms)
            snr_db = calculate_snr_estimate(samples)

        preprocessed = PreprocessedAudio(
            waveform=samples,
            sample_rate=sr,
            original_duration_sec=round(duration_sec, 3),
            processed_duration_sec=round(duration_sec, 3),
            rms_energy_db=round(rms_db, 2),
            estimated_snr_db=round(snr_db, 2),
            channels=1,
            metadata={"stream_window": True, "samples": len(samples)},
        )

        # 1. Wav2Vec2 Deepfake Inference
        prediction_result = self.detector.predict(preprocessed)

        # 2. Deterministic Prosody & Acoustic Anomaly Analysis (single authoritative run)
        prosody_res = self.prosody_analyzer.analyze(preprocessed)

        # 3. Context & Speaker Biometric Verification (if enrolled)
        call_context = extract_call_context(args)
        speaker_id = args.get("speaker_id")
        threshold = args.get("threshold")
        effective_speaker_threshold = (
            float(threshold) if threshold is not None and str(threshold).strip() != ""
            else float(call_context.speaker_verification_strictness)
        )
        self.sync_store()
        speaker_mismatch_signal = 0
        speaker_verification_status = "NOT_EVALUATED"
        speaker_detail = {
            "status": "NOT_EVALUATED",
            "speaker_id": speaker_id,
            "similarity_score": None,
            "threshold": None,
            "is_match": None,
            "speaker_mismatch_flag": None,
            "inference_time_ms": None,
        }

        if speaker_id:
            enrolled = self.speaker_store.get(speaker_id)
            if enrolled:
                ver_res = self.speaker_verifier.verify(
                    audio=preprocessed,
                    enrolled_embedding=enrolled,
                    threshold=effective_speaker_threshold,
                )
                speaker_mismatch_signal = ver_res.speaker_mismatch_flag
                speaker_verification_status = "MATCH" if ver_res.is_match else "MISMATCH"
                speaker_detail = {
                    "status": "EVALUATED",
                    "speaker_id": speaker_id,
                    "similarity_score": round(ver_res.similarity_score, 4),
                    "threshold": round(ver_res.threshold, 4),
                    "is_match": ver_res.is_match,
                    "speaker_mismatch_flag": ver_res.speaker_mismatch_flag,
                    "sample_count": enrolled.sample_count,
                    "inference_time_ms": round(ver_res.inference_time_ms, 2),
                }
            else:
                speaker_verification_status = "NOT_ENROLLED"
                speaker_detail = {
                    "status": "NOT_ENROLLED",
                    "speaker_id": speaker_id,
                    "similarity_score": None,
                    "threshold": None,
                    "is_match": None,
                    "speaker_mismatch_flag": None,
                    "inference_time_ms": None,
                }

        # 4. Local Multilingual Speech Recognition (ASR) & Language Identification
        asr_res = ASRResult()
        try:
            if hasattr(self, "speech_recognizer") and self.speech_recognizer is not None:
                asr_res = self.speech_recognizer.transcribe(preprocessed, sample_rate=sr)
        except Exception as e:
            sys.stderr.write(f"[PipelineWorker:ASRError] {e}\n")

        # Merge speech-derived transcript and keywords into context
        if asr_res.is_speech and asr_res.transcript:
            if not call_context.transcript_text:
                call_context.transcript_text = asr_res.transcript
            if asr_res.keywords_detected:
                for kw in asr_res.keywords_detected:
                    if kw not in call_context.suspicious_keywords_found:
                        call_context.suspicious_keywords_found.append(kw)

        # 5. Context & Risk Engine Fusion
        risk_assessment = self.risk_engine.evaluate(
            fake_probability=prediction_result.fake_probability,
            speaker_mismatch=speaker_mismatch_signal,
            acoustic_anomaly=prosody_res.acoustic_anomaly,
            context=call_context,
            prosody_reasons=prosody_res.anomaly_reasons,
        )

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0
        call_id = args.get("call_id") or f"LIVE-{uuid.uuid4().hex[:6].upper()}"

        verification_session = SecondaryVerificationStateMachine.initialize_session(
            call_id=call_id,
            recommended_action=risk_assessment.recommended_action,
            risk_score=risk_assessment.risk_score,
            risk_level=risk_assessment.risk_level,
            context=call_context,
            flags=risk_assessment.flags,
        )

        speech_prof = resolve_speech_profile(
            selected_language=call_context.selected_language or call_context.language,
            detected_language=asr_res.language_name if asr_res.is_speech else call_context.detected_language,
            language_confidence=asr_res.language_confidence if asr_res.is_speech else call_context.language_confidence,
            transcript_text=call_context.transcript_text or asr_res.transcript,
            transcript_language=asr_res.language if asr_res.is_speech else call_context.transcript_language,
        )

        return {
            "call_id": call_id,
            "window_index": args.get("window_index", 0),
            "fake_probability": round(prediction_result.fake_probability, 4),
            "real_probability": round(prediction_result.real_probability, 4),
            "acoustic_anomaly": round(prosody_res.acoustic_anomaly, 4),
            "risk_score": risk_assessment.risk_score,
            "risk_level": risk_assessment.risk_level,
            "recommended_action": risk_assessment.recommended_action,
            "verification_session": verification_session.to_dict(),
            "speech_profile": speech_prof,
            "language_profile": speech_prof,
            "language": asr_res.language,
            "language_name": asr_res.language_name,
            "language_confidence": asr_res.language_confidence,
            "transcript": asr_res.transcript or call_context.transcript_text or "",
            "speech_context_flags": asr_res.speech_context_flags,
            "asr_analysis": asr_res.to_dict(),
            "flags": risk_assessment.flags,
            "prosody_reasons": prosody_res.anomaly_reasons,
            "prosody_metrics": {k: round(float(v), 4) for k, v in prosody_res.features.items()},
            "prosody_analysis": prosody_res.to_dict(),
            "context_intelligence": {
                "context_source": call_context.context_source,
                "context_available": call_context.context_available,
                "organization_id": call_context.organization_id,
                "contact_id": call_context.contact_id,
                "contact_name": call_context.contact_name,
                "contact_role": call_context.contact_role,
                "is_caller_recognized": call_context.is_caller_recognized,
                "is_previously_flagged": call_context.is_previously_flagged,
                "is_verified": call_context.is_verified,
                "role_mismatch": call_context.role_mismatch,
                "has_prior_fraud_history": call_context.has_prior_fraud_history,
                "fraud_history_count": call_context.fraud_history_count,
            },
            "deepfake_detection": {
                "prediction": prediction_result.prediction,
                "fake_probability": round(prediction_result.fake_probability, 4),
                "real_probability": round(prediction_result.real_probability, 4),
                "model_type": prediction_result.metadata.get("model_type", "Wav2Vec2"),
                "inference_time_ms": round(prediction_result.metadata.get("inference_time_ms", 0.0), 2),
            },
            "speaker_verification": speaker_detail,
            "audio_metrics": {
                "window_duration_sec": round(duration_sec, 2),
                "sample_rate": sr,
                "estimated_snr_db": round(snr_db, 2),
                "rms_db": round(rms_db, 2),
            },
            "pipeline_latency_ms": round(total_latency_ms, 2),
        }

    def handle_enroll(self, args: dict) -> dict:
        audio_path = args.get("file")
        speaker_id = args.get("speaker_id")
        speaker_name = args.get("speaker_name")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundAudioError(f"Audio file not found: {audio_path}")
        if not speaker_id:
            raise ValueError("Field 'speaker_id' is required for enrollment.")

        preprocessed = self.preprocessor.process(audio_path)
        self.sync_store()

        start_time = time.perf_counter()
        raw_emb = self.speaker_verifier.extract_embedding(preprocessed, speaker_id=speaker_id)

        sample_meta = {
            "processed_duration_sec": round(preprocessed.processed_duration_sec, 2),
            "snr_db": round(preprocessed.estimated_snr_db, 2),
            "rms_db": round(preprocessed.rms_energy_db, 2),
        }
        enrolled = self.speaker_store.enroll_sample(
            speaker_id=speaker_id,
            embedding=raw_emb.embedding,
            speaker_name=speaker_name,
            sample_metadata=sample_meta,
        )
        save_persistent_store(self.speaker_store)
        total_time_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "status": "ENROLLED",
            "speaker_id": speaker_id,
            "speaker_name": speaker_name or enrolled.metadata.get("speaker_name"),
            "sample_count": enrolled.sample_count,
            "embedding_dimension": enrolled.dimension,
            "created_at": enrolled.created_at,
            "updated_at": enrolled.updated_at,
            "message": f"Speaker '{speaker_id}' sample #{enrolled.sample_count} successfully enrolled ({preprocessed.processed_duration_sec:.2f}s audio processed; multi-sample centroid updated).",
            "sample_rate_verified": preprocessed.sample_rate,
            "inference_time_ms": round(total_time_ms, 2),
        }

    def handle_verify_speaker(self, args: dict) -> dict:
        audio_path = args.get("file")
        speaker_id = args.get("speaker_id")
        threshold = args.get("threshold")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundAudioError(f"Audio file not found: {audio_path}")

        self.sync_store()
        enrolled_embedding = self.speaker_store.get(speaker_id)
        if not enrolled_embedding:
            return {
                "status": 404,
                "data": {
                    "error_type": "SpeakerNotEnrolledError",
                    "message": f"Speaker '{speaker_id}' has not been enrolled. Please enroll reference audio first.",
                    "status": 404,
                }
            }

        preprocessed = self.preprocessor.process(audio_path)
        ver_result = self.speaker_verifier.verify(
            audio=preprocessed,
            enrolled_embedding=enrolled_embedding,
            threshold=threshold,
        )

        match_desc = "MATCH (Voice verified)" if ver_result.is_match else "MISMATCH (Voice biometric discrepancy)"

        return {
            "status": "SUCCESS",
            "speaker_id": speaker_id,
            "similarity_score": round(ver_result.similarity_score, 4),
            "threshold": round(ver_result.threshold, 4),
            "match": ver_result.is_match,
            "speaker_mismatch_flag": ver_result.speaker_mismatch_flag,
            "sample_count": enrolled_embedding.sample_count,
            "inference_time_ms": round(ver_result.inference_time_ms, 2),
            "message": f"Verification completed for speaker '{speaker_id}' (against {enrolled_embedding.sample_count}-sample centroid): {match_desc}.",
        }

    def dispatch(self, req: dict) -> dict:
        cmd = req.get("command")
        args = req.get("args", {})

        try:
            if cmd == "health":
                data = self.handle_health()
                return {"status": 200, "data": data}
            elif cmd == "list-speakers":
                data = self.handle_list_speakers()
                return {"status": 200, "data": data}
            elif cmd == "analyze":
                data = self.handle_analyze(args)
                return {"status": 200, "data": data}
            elif cmd in ("stream-chunk", "live-chunk"):
                data = self.handle_stream_chunk(args)
                return {"status": 200, "data": data}
            elif cmd == "enroll":
                data = self.handle_enroll(args)
                return {"status": 200, "data": data}
            elif cmd == "verify-speaker":
                res = self.handle_verify_speaker(args)
                if isinstance(res, dict) and "status" in res and isinstance(res["status"], int) and res["status"] != 200:
                    return res
                return {"status": 200, "data": res}
            else:
                return {
                    "status": 400,
                    "data": {"error_type": "UnknownCommandError", "message": f"Unknown command: {cmd}"},
                }
        except AudioTooShortError as err:
            return {"status": 422, "data": {"error_type": "AudioTooShortError", "message": str(err), "status": 422}}
        except AudioTooLongError as err:
            return {"status": 422, "data": {"error_type": "AudioTooLongError", "message": str(err), "status": 422}}
        except AudioSilentError as err:
            return {"status": 422, "data": {"error_type": "AudioSilentError", "message": str(err), "status": 422}}
        except (AudioCorruptError, UnsupportedFormatError) as err:
            return {"status": 400, "data": {"error_type": "AudioCorruptError", "message": str(err), "status": 400}}
        except FileNotFoundAudioError as err:
            return {"status": 404, "data": {"error_type": "FileNotFoundAudioError", "message": str(err), "status": 404}}
        except Exception as err:
            return {"status": 500, "data": {"error_type": "InferenceError", "message": str(err), "status": 500}}


def cmd_daemon():
    """
    Long-running daemon loop over stdio.
    Loads models once at startup and services incoming requests via JSON lines.
    """
    real_stdout = sys.stdout
    # Route standard prints/logs to stderr so they do not corrupt the stdio JSON-RPC protocol
    sys.stdout = sys.stderr

    sys.stderr.write("[PipelineDaemon] Initializing persistent ML models...\n")
    worker = PipelineWorker()
    sys.stderr.write("[PipelineDaemon] ML models initialized and ready in memory.\n")

    # Output ready sentinel
    real_stdout.write(json.dumps({"status": "READY", "message": "VoiceShield persistent pipeline ready"}) + "\n")
    real_stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            result = worker.dispatch(req)
            result["id"] = req_id
            real_stdout.write(json.dumps(result) + "\n")
            real_stdout.flush()
        except Exception as err:
            err_res = {
                "id": req.get("id") if "req" in locals() and isinstance(req, dict) else None,
                "status": 500,
                "data": {"error_type": "DaemonDispatchError", "message": str(err)},
            }
            real_stdout.write(json.dumps(err_res) + "\n")
            real_stdout.flush()


def cmd_analyze(args):
    audio_path = args.file
    speaker_id = args.speaker_id
    threshold = args.threshold
    caller_id = args.caller_id
    is_caller_recognized = args.is_caller_recognized
    is_previously_flagged = args.is_previously_flagged
    claimed_role = args.claimed_role
    requested_amount = args.requested_amount
    normal_amount = args.normal_amount
    is_urgent = args.is_urgent
    urgency_reason = args.urgency_reason
    transcript_text = args.transcript_text
    acoustic_anomaly = args.acoustic_anomaly or 0.0

    try:
        preprocessor = AudioPreprocessor()
        preprocessed = preprocessor.process(audio_path)

        prosody_analyzer = ProsodyAnalyzer()
        prosody_result = prosody_analyzer.analyze(preprocessed)

        if args.acoustic_anomaly is not None and float(args.acoustic_anomaly) > 0.0:
            acoustic_anomaly = float(args.acoustic_anomaly)
        else:
            acoustic_anomaly = prosody_result.acoustic_anomaly

        detector = VoiceCloneDetector()
        detector.load()
        prediction_result = detector.predict(preprocessed)

        speaker_store = load_persistent_store()
        speaker_verifier = PretrainedECAPASpeakerVerifier()
        speaker_verifier.load_model()

        speaker_mismatch_signal = 0
        speaker_verification_status = "NOT_EVALUATED (No speaker_id supplied)"
        speaker_detail = {
            "status": "NOT_EVALUATED",
            "speaker_id": speaker_id,
            "similarity_score": None,
            "threshold": None,
            "is_match": None,
            "speaker_mismatch_flag": None,
            "inference_time_ms": None,
        }

        if speaker_id:
            enrolled = speaker_store.get(speaker_id)
            if enrolled:
                ver_res = speaker_verifier.verify(
                    audio=preprocessed,
                    enrolled_embedding=enrolled,
                    threshold=threshold,
                )
                speaker_mismatch_signal = ver_res.speaker_mismatch_flag
                speaker_verification_status = "EVALUATED (MATCH)" if ver_res.is_match else "EVALUATED (MISMATCH)"
                speaker_detail = {
                    "status": "EVALUATED",
                    "speaker_id": speaker_id,
                    "similarity_score": round(ver_res.similarity_score, 4),
                    "threshold": round(ver_res.threshold, 4),
                    "is_match": ver_res.is_match,
                    "speaker_mismatch_flag": ver_res.speaker_mismatch_flag,
                    "inference_time_ms": round(ver_res.inference_time_ms, 2),
                }
            else:
                speaker_verification_status = f"NOT_ENROLLED (Speaker '{speaker_id}' not found in registry)"
                speaker_detail = {
                    "status": "NOT_ENROLLED",
                    "speaker_id": speaker_id,
                    "similarity_score": None,
                    "threshold": None,
                    "is_match": None,
                    "speaker_mismatch_flag": None,
                    "inference_time_ms": None,
                }

        call_context = extract_call_context(vars(args))

        risk_engine = VoiceShieldRiskEngine()
        risk_assessment = risk_engine.evaluate(
            fake_probability=prediction_result.fake_probability,
            speaker_mismatch=speaker_mismatch_signal,
            acoustic_anomaly=acoustic_anomaly,
            context=call_context,
            prosody_reasons=prosody_result.anomaly_reasons,
        )

        call_id = f"CALL-{uuid.uuid4().hex[:8].upper()}"

        res = {
            "call_id": call_id,
            "risk_score": risk_assessment.risk_score,
            "risk_level": risk_assessment.risk_level,
            "deepfake_detection": {
                "prediction": prediction_result.prediction,
                "fake_probability": round(prediction_result.fake_probability, 4),
                "real_probability": round(prediction_result.real_probability, 4),
                "model_type": prediction_result.metadata.get("model_type", "Wav2Vec2"),
                "model_id": prediction_result.metadata.get("model_id", "garystafford/wav2vec2-deepfake-voice-detector"),
                "inference_time_ms": round(prediction_result.metadata.get("inference_time_ms", 0.0), 2),
                "disclaimer": prediction_result.metadata.get("disclaimer"),
            },
            "speaker_verification": speaker_detail,
            "prosody_analysis": prosody_result.to_dict(),
            "risk_signals": {
                "fake_probability": round(prediction_result.fake_probability, 4),
                "speaker_mismatch": speaker_mismatch_signal,
                "acoustic_anomaly": round(float(acoustic_anomaly), 4),
                "context_flag": risk_assessment.signals.get("context_flag", 0.0),
                "speaker_verification_status": speaker_verification_status,
                "acoustic_model_status": "DETERMINISTIC_PROSODY_ANALYSIS",
                "prosody_reasons": prosody_result.anomaly_reasons,
            },
            "flags": risk_assessment.flags,
            "recommended_action": risk_assessment.recommended_action,
            "audio_metadata": {
                "sample_rate": preprocessed.sample_rate,
                "original_duration_sec": round(preprocessed.original_duration_sec, 2),
                "processed_duration_sec": round(preprocessed.processed_duration_sec, 2),
                "estimated_snr_db": round(preprocessed.estimated_snr_db, 2),
                "rms_db": round(preprocessed.rms_energy_db, 2),
            },
        }

        print(json.dumps(res))
    except AudioTooShortError as err:
        sys.stderr.write(json.dumps({"error_type": "AudioTooShortError", "message": str(err), "status": 422}))
        sys.exit(1)
    except AudioTooLongError as err:
        sys.stderr.write(json.dumps({"error_type": "AudioTooLongError", "message": str(err), "status": 422}))
        sys.exit(1)
    except AudioSilentError as err:
        sys.stderr.write(json.dumps({"error_type": "AudioSilentError", "message": str(err), "status": 422}))
        sys.exit(1)
    except (AudioCorruptError, UnsupportedFormatError) as err:
        sys.stderr.write(json.dumps({"error_type": "AudioCorruptError", "message": str(err), "status": 400}))
        sys.exit(1)
    except FileNotFoundAudioError as err:
        sys.stderr.write(json.dumps({"error_type": "FileNotFoundAudioError", "message": str(err), "status": 404}))
        sys.exit(1)
    except Exception as err:
        sys.stderr.write(json.dumps({"error_type": "InferenceError", "message": str(err), "status": 500}))
        sys.exit(1)


def cmd_enroll(args):
    audio_path = args.file
    speaker_id = args.speaker_id
    speaker_name = args.speaker_name

    try:
        preprocessor = AudioPreprocessor()
        preprocessed = preprocessor.process(audio_path)

        speaker_verifier = PretrainedECAPASpeakerVerifier()
        speaker_verifier.load_model()
        speaker_store = load_persistent_store()

        start_time = time.perf_counter()
        embedding = speaker_verifier.extract_embedding(preprocessed, speaker_id=speaker_id)
        if speaker_name:
            embedding.metadata["speaker_name"] = speaker_name

        speaker_store.save(embedding)
        save_persistent_store(speaker_store)
        total_time_ms = (time.perf_counter() - start_time) * 1000.0

        res = {
            "status": "ENROLLED",
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "embedding_dimension": embedding.dimension,
            "message": f"Speaker '{speaker_id}' successfully enrolled ({preprocessed.processed_duration_sec:.2f}s audio processed).",
            "sample_rate_verified": preprocessed.sample_rate,
            "inference_time_ms": round(total_time_ms, 2),
        }
        print(json.dumps(res))
    except (AudioTooShortError, AudioTooLongError, AudioSilentError) as err:
        sys.stderr.write(json.dumps({"error_type": type(err).__name__, "message": str(err), "status": 422}))
        sys.exit(1)
    except (AudioCorruptError, UnsupportedFormatError) as err:
        sys.stderr.write(json.dumps({"error_type": type(err).__name__, "message": str(err), "status": 400}))
        sys.exit(1)
    except Exception as err:
        sys.stderr.write(json.dumps({"error_type": "InferenceError", "message": str(err), "status": 500}))
        sys.exit(1)


def cmd_verify_speaker(args):
    audio_path = args.file
    speaker_id = args.speaker_id
    threshold = args.threshold

    speaker_store = load_persistent_store()
    enrolled_embedding = speaker_store.get(speaker_id)
    if not enrolled_embedding:
        sys.stderr.write(json.dumps({
            "error_type": "SpeakerNotEnrolledError",
            "message": f"Speaker '{speaker_id}' has not been enrolled. Please enroll reference audio first.",
            "status": 404
        }))
        sys.exit(1)

    try:
        preprocessor = AudioPreprocessor()
        preprocessed = preprocessor.process(audio_path)

        speaker_verifier = PretrainedECAPASpeakerVerifier()
        speaker_verifier.load_model()

        ver_result = speaker_verifier.verify(
            audio=preprocessed,
            enrolled_embedding=enrolled_embedding,
            threshold=threshold,
        )

        match_desc = "MATCH (Voice verified)" if ver_result.is_match else "MISMATCH (Voice biometric discrepancy)"

        res = {
            "status": "SUCCESS",
            "speaker_id": speaker_id,
            "similarity_score": round(ver_result.similarity_score, 4),
            "threshold": round(ver_result.threshold, 4),
            "match": ver_result.is_match,
            "speaker_mismatch_flag": ver_result.speaker_mismatch_flag,
            "inference_time_ms": round(ver_result.inference_time_ms, 2),
            "message": f"Verification completed for speaker '{speaker_id}': {match_desc}.",
        }
        print(json.dumps(res))
    except (AudioTooShortError, AudioTooLongError, AudioSilentError) as err:
        sys.stderr.write(json.dumps({"error_type": type(err).__name__, "message": str(err), "status": 422}))
        sys.exit(1)
    except (AudioCorruptError, UnsupportedFormatError) as err:
        sys.stderr.write(json.dumps({"error_type": type(err).__name__, "message": str(err), "status": 400}))
        sys.exit(1)
    except Exception as err:
        sys.stderr.write(json.dumps({"error_type": "InferenceError", "message": str(err), "status": 500}))
        sys.exit(1)


def cmd_list_speakers():
    speaker_store = load_persistent_store()
    speakers = []
    for spk_id, emb in speaker_store._store.items():
        speakers.append({
            "speaker_id": emb.speaker_id,
            "speaker_name": emb.metadata.get("speaker_name"),
            "dimension": emb.dimension,
            "created_at": emb.created_at,
        })
    print(json.dumps({"status": "ok", "speakers": speakers}))


def main():
    parser = argparse.ArgumentParser(description="VoiceShield Pipeline CLI Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Health
    subparsers.add_parser("health")

    # Daemon (Persistent Worker)
    subparsers.add_parser("daemon")

    # List Speakers
    subparsers.add_parser("list-speakers")

    # Analyze
    p_analyze = subparsers.add_parser("analyze")
    p_analyze.add_argument("--file", required=True)
    p_analyze.add_argument("--speaker-id", default=None)
    p_analyze.add_argument("--threshold", type=float, default=None)
    p_analyze.add_argument("--caller-id", default=None)
    p_analyze.add_argument("--is-caller-recognized", type=lambda x: str(x).lower() in ("true", "1"), default=True)
    p_analyze.add_argument("--is-previously-flagged", type=lambda x: str(x).lower() in ("true", "1"), default=False)
    p_analyze.add_argument("--claimed-role", default=None)
    p_analyze.add_argument("--requested-amount", type=float, default=None)
    p_analyze.add_argument("--normal-amount", type=float, default=None)
    p_analyze.add_argument("--is-urgent", type=lambda x: str(x).lower() in ("true", "1"), default=False)
    p_analyze.add_argument("--urgency-reason", default=None)
    p_analyze.add_argument("--transcript-text", default=None)
    p_analyze.add_argument("--acoustic-anomaly", type=float, default=0.0)
    p_analyze.add_argument("--context", default=None)

    # Enroll
    p_enroll = subparsers.add_parser("enroll")
    p_enroll.add_argument("--file", required=True)
    p_enroll.add_argument("--speaker-id", required=True)
    p_enroll.add_argument("--speaker-name", default=None)

    # Verify
    p_verify = subparsers.add_parser("verify-speaker")
    p_verify.add_argument("--file", required=True)
    p_verify.add_argument("--speaker-id", required=True)
    p_verify.add_argument("--threshold", type=float, default=None)

    args = parser.parse_args()

    if args.command == "health":
        cmd_health()
    elif args.command == "daemon":
        cmd_daemon()
    elif args.command == "list-speakers":
        cmd_list_speakers()
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "enroll":
        cmd_enroll(args)
    elif args.command == "verify-speaker":
        cmd_verify_speaker(args)


if __name__ == "__main__":
    main()
