"""
Authoritative Security Events & Alert Center Engine for VoiceShield (Feature 2).
Provides event classification, severity grading, threat intelligence aggregation,
multi-tenant isolation, and event filtering.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid

from app.risk.context import CallContext
from app.risk.verification import (
    SecondaryVerificationStatus,
    VerificationSession,
)


class SecurityEventSeverity(str, Enum):
    """
    Standardized security event severities for VoiceShield operations.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventType(str, Enum):
    """
    Authoritative event types supported by VoiceShield threat intelligence.
    """
    HIGH_RISK_CALL = "HIGH_RISK_CALL"
    DEEPFAKE_VOICE_CLONE = "DEEPFAKE_VOICE_CLONE"
    EXECUTIVE_IMPERSONATION = "EXECUTIVE_IMPERSONATION"
    ROLE_MISMATCH = "ROLE_MISMATCH"
    PREVIOUS_FRAUD_HISTORY = "PREVIOUS_FRAUD_HISTORY"
    TRANSACTION_AUTO_HOLD = "TRANSACTION_AUTO_HOLD"
    SPEAKER_MISMATCH = "SPEAKER_MISMATCH"
    ACOUSTIC_ANOMALY = "ACOUSTIC_ANOMALY"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_ESCALATED = "VERIFICATION_ESCALATED"
    CALL_BLOCKED = "CALL_BLOCKED"


@dataclass
class SecurityEvent:
    """
    Authoritative representation of a security incident or threat intelligence event.
    """
    id: str
    call_id: str
    organization_id: str
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    timestamp: float = field(default_factory=time.time)
    caller_id: Optional[str] = None
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    claimed_role: Optional[str] = None
    speaker_id: Optional[str] = None
    risk_score: int = 0
    risk_level: str = "LOW"
    explanation: str = ""
    recommended_action: str = "ALLOW"
    verification_status: Optional[str] = None
    is_held: bool = False
    transaction_amount: Optional[float] = None
    hold_reason: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    contributing_signals: Dict[str, Any] = field(default_factory=dict)
    status: str = "OPEN"  # "OPEN" | "RESOLVED" | "ESCALATED" | "INVESTIGATING"
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    is_simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "call_id": self.call_id,
            "organization_id": self.organization_id,
            "event_type": self.event_type.value if isinstance(self.event_type, SecurityEventType) else str(self.event_type),
            "severity": self.severity.value if isinstance(self.severity, SecurityEventSeverity) else str(self.severity),
            "timestamp": self.timestamp,
            "caller_id": self.caller_id,
            "contact_id": self.contact_id,
            "contact_name": self.contact_name,
            "claimed_role": self.claimed_role,
            "speaker_id": self.speaker_id,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "explanation": self.explanation,
            "recommended_action": self.recommended_action,
            "verification_status": self.verification_status,
            "is_held": self.is_held,
            "transaction_amount": self.transaction_amount,
            "hold_reason": self.hold_reason,
            "flags": list(self.flags),
            "contributing_signals": dict(self.contributing_signals),
            "status": self.status,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "is_simulated": self.is_simulated,
        }


def classify_event_severity(
    risk_score: int,
    event_type: SecurityEventType,
    fake_prob: float = 0.0,
    is_held: bool = False,
    verification_status: str = "PENDING",
) -> SecurityEventSeverity:
    """
    Authoritative severity classification based on risk score, threat category, and verification state.
    """
    if (
        event_type == SecurityEventType.CALL_BLOCKED
        or verification_status == SecondaryVerificationStatus.BLOCKED.value
        or fake_prob >= 0.85
        or risk_score >= 85
    ):
        return SecurityEventSeverity.CRITICAL

    if (
        event_type in (
            SecurityEventType.DEEPFAKE_VOICE_CLONE,
            SecurityEventType.EXECUTIVE_IMPERSONATION,
            SecurityEventType.VERIFICATION_FAILED,
            SecurityEventType.VERIFICATION_ESCALATED,
        )
        or risk_score >= 70
        or is_held
        or fake_prob >= 0.65
    ):
        return SecurityEventSeverity.HIGH

    if (
        event_type in (
            SecurityEventType.ROLE_MISMATCH,
            SecurityEventType.SPEAKER_MISMATCH,
            SecurityEventType.ACOUSTIC_ANOMALY,
            SecurityEventType.PREVIOUS_FRAUD_HISTORY,
            SecurityEventType.TRANSACTION_AUTO_HOLD,
        )
        or risk_score >= 35
    ):
        return SecurityEventSeverity.MEDIUM

    return SecurityEventSeverity.LOW


def generate_security_events_from_analysis(
    call_id: str,
    risk_score: int,
    risk_level: str,
    deepfake_result: Dict[str, Any],
    speaker_result: Dict[str, Any],
    prosody_result: Dict[str, Any],
    context: CallContext,
    flags: List[str],
    recommended_action: str,
    verification_session: Optional[VerificationSession] = None,
    org_id: str = "00000000-0000-0000-0000-000000000001",
) -> List[SecurityEvent]:
    """
    Analyzes multi-signal inference and context to authoritatively emit structured security events.
    """
    events: List[SecurityEvent] = []
    now = time.time()
    fake_prob = float(deepfake_result.get("fake_probability", 0.0))
    speaker_match = speaker_result.get("is_match")
    speaker_sim = speaker_result.get("similarity_score")
    speaker_id = speaker_result.get("speaker_id") or getattr(context, "speaker_id", None)
    acoustic_anomaly = float(prosody_result.get("acoustic_anomaly", 0.0))
    is_held = verification_session.is_held if verification_session else (
        context.requested_transaction_amount is not None
        and context.transaction_auto_hold_amount is not None
        and context.requested_transaction_amount >= context.transaction_auto_hold_amount
    )
    v_status = verification_session.status.value if verification_session else "PENDING"
    hold_reason = verification_session.hold_reason if verification_session else (
        f"Transaction on hold: Amount ${context.requested_transaction_amount:,.2f} exceeds auto-hold threshold."
        if is_held else None
    )

    signals_dict = {
        "fake_probability": fake_prob,
        "deepfake_prediction": deepfake_result.get("prediction"),
        "speaker_similarity": speaker_sim,
        "speaker_match": speaker_match,
        "speaker_id": speaker_id,
        "acoustic_anomaly": acoustic_anomaly,
        "role_mismatch": context.role_mismatch,
        "claimed_role": context.claimed_role,
        "has_prior_fraud": context.has_prior_fraud_history,
        "is_urgent": context.is_urgent,
        "transaction_amount": context.requested_transaction_amount,
    }

    # 1. Critical/High Risk Call Alert
    if risk_score >= 50 or recommended_action in ("BLOCK", "SECONDARY_VERIFICATION", "HOLD_AND_STEP_UP"):
        main_event_type = SecurityEventType.HIGH_RISK_CALL
        if recommended_action == "BLOCK" or v_status == "BLOCKED":
            main_event_type = SecurityEventType.CALL_BLOCKED

        severity = classify_event_severity(
            risk_score=risk_score,
            event_type=main_event_type,
            fake_prob=fake_prob,
            is_held=is_held,
            verification_status=v_status,
        )

        explanation = (
            f"Multi-signal threat detected with risk score {risk_score}/100 ({risk_level}). "
            + (f"Action: {recommended_action}. " if recommended_action else "")
            + (f"Flags: {'; '.join(flags[:2])}." if flags else "Acoustic or context anomaly flagged.")
        )

        events.append(
            SecurityEvent(
                id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                call_id=call_id,
                organization_id=org_id,
                event_type=main_event_type,
                severity=severity,
                timestamp=now,
                caller_id=context.caller_id,
                contact_id=context.contact_id,
                claimed_role=context.claimed_role,
                speaker_id=speaker_id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=explanation,
                recommended_action=recommended_action,
                verification_status=v_status,
                is_held=is_held,
                transaction_amount=context.requested_transaction_amount,
                hold_reason=hold_reason,
                flags=flags,
                contributing_signals=signals_dict,
            )
        )

    # 2. Deepfake Voice Clone Indicator
    if fake_prob >= 0.70:
        events.append(
            SecurityEvent(
                id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                call_id=call_id,
                organization_id=org_id,
                event_type=SecurityEventType.DEEPFAKE_VOICE_CLONE,
                severity=SecurityEventSeverity.CRITICAL if fake_prob >= 0.85 else SecurityEventSeverity.HIGH,
                timestamp=now,
                caller_id=context.caller_id,
                contact_id=context.contact_id,
                claimed_role=context.claimed_role,
                speaker_id=speaker_id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=f"Neural acoustic synthesis detected by Wav2Vec2 model (Synthetic Probability: {fake_prob*100:.1f}%).",
                recommended_action=recommended_action,
                verification_status=v_status,
                is_held=is_held,
                transaction_amount=context.requested_transaction_amount,
                hold_reason=hold_reason,
                flags=[f"Wav2Vec2 high neural synthesis probability ({fake_prob*100:.1f}%)"],
                contributing_signals=signals_dict,
            )
        )

    # 3. Executive Impersonation / Role Mismatch
    if context.role_mismatch:
        is_exec = any(r in (context.claimed_role or "").lower() for r in ["ceo", "cfo", "director", "executive", "treasurer", "president", "chief"])
        evt_type = SecurityEventType.EXECUTIVE_IMPERSONATION if is_exec else SecurityEventType.ROLE_MISMATCH
        events.append(
            SecurityEvent(
                id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                call_id=call_id,
                organization_id=org_id,
                event_type=evt_type,
                severity=SecurityEventSeverity.HIGH if is_exec else SecurityEventSeverity.MEDIUM,
                timestamp=now,
                caller_id=context.caller_id,
                contact_id=context.contact_id,
                claimed_role=context.claimed_role,
                speaker_id=speaker_id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=f"Claimed role '{context.claimed_role}' conflicts with authorized identity records.",
                recommended_action=recommended_action,
                verification_status=v_status,
                is_held=is_held,
                transaction_amount=context.requested_transaction_amount,
                hold_reason=hold_reason,
                flags=[f"Role mismatch: claimed '{context.claimed_role}'"],
                contributing_signals=signals_dict,
            )
        )

    # 4. Transaction Auto-Hold Event
    if is_held and context.requested_transaction_amount is not None:
        events.append(
            SecurityEvent(
                id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                call_id=call_id,
                organization_id=org_id,
                event_type=SecurityEventType.TRANSACTION_AUTO_HOLD,
                severity=SecurityEventSeverity.HIGH if risk_score >= 60 else SecurityEventSeverity.MEDIUM,
                timestamp=now,
                caller_id=context.caller_id,
                contact_id=context.contact_id,
                claimed_role=context.claimed_role,
                speaker_id=speaker_id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=f"Transaction of ${context.requested_transaction_amount:,.2f} placed on auto-hold pending secondary verification.",
                recommended_action=recommended_action,
                verification_status=v_status,
                is_held=True,
                transaction_amount=context.requested_transaction_amount,
                hold_reason=hold_reason,
                flags=[f"Financial wire amount on hold (${context.requested_transaction_amount:,.2f})"],
                contributing_signals=signals_dict,
            )
        )

    # 5. Speaker Biometric Mismatch
    if speaker_match is False and speaker_sim is not None:
        events.append(
            SecurityEvent(
                id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                call_id=call_id,
                organization_id=org_id,
                event_type=SecurityEventType.SPEAKER_MISMATCH,
                severity=SecurityEventSeverity.HIGH if fake_prob > 0.5 else SecurityEventSeverity.MEDIUM,
                timestamp=now,
                caller_id=context.caller_id,
                contact_id=context.contact_id,
                claimed_role=context.claimed_role,
                speaker_id=speaker_id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=f"Biometric voiceprint distance mismatch (Cosine similarity: {speaker_sim:.2f} < threshold).",
                recommended_action=recommended_action,
                verification_status=v_status,
                is_held=is_held,
                transaction_amount=context.requested_transaction_amount,
                hold_reason=hold_reason,
                flags=[f"ECAPA-TDNN biometric cosine distance mismatch ({speaker_sim:.2f})"],
                contributing_signals=signals_dict,
            )
        )

    # 6. Verification Specific State Events
    if verification_session:
        if verification_session.status == SecondaryVerificationStatus.FAILED:
            events.append(
                SecurityEvent(
                    id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                    call_id=call_id,
                    organization_id=org_id,
                    event_type=SecurityEventType.VERIFICATION_FAILED,
                    severity=SecurityEventSeverity.HIGH,
                    timestamp=now,
                    caller_id=context.caller_id,
                    contact_id=context.contact_id,
                    claimed_role=context.claimed_role,
                    speaker_id=speaker_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    explanation="Secondary identity challenge failed. Step-up hold retained.",
                    recommended_action="SECONDARY_VERIFICATION",
                    verification_status=verification_session.status.value,
                    is_held=True,
                    transaction_amount=context.requested_transaction_amount,
                    hold_reason=verification_session.hold_reason,
                    flags=["Identity verification challenge failed"],
                    contributing_signals=signals_dict,
                )
            )
        elif verification_session.status == SecondaryVerificationStatus.ESCALATED:
            events.append(
                SecurityEvent(
                    id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                    call_id=call_id,
                    organization_id=org_id,
                    event_type=SecurityEventType.VERIFICATION_ESCALATED,
                    severity=SecurityEventSeverity.HIGH,
                    timestamp=now,
                    caller_id=context.caller_id,
                    contact_id=context.contact_id,
                    claimed_role=context.claimed_role,
                    speaker_id=speaker_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    explanation="Incident escalated to supervisor for high-risk forensic investigation.",
                    recommended_action="SECONDARY_VERIFICATION",
                    verification_status=verification_session.status.value,
                    is_held=True,
                    transaction_amount=context.requested_transaction_amount,
                    hold_reason=verification_session.hold_reason,
                    flags=["Escalated to Fraud Operations supervisor"],
                    contributing_signals=signals_dict,
                )
            )
        elif verification_session.status == SecondaryVerificationStatus.BLOCKED:
            events.append(
                SecurityEvent(
                    id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
                    call_id=call_id,
                    organization_id=org_id,
                    event_type=SecurityEventType.CALL_BLOCKED,
                    severity=SecurityEventSeverity.CRITICAL,
                    timestamp=now,
                    caller_id=context.caller_id,
                    contact_id=context.contact_id,
                    claimed_role=context.claimed_role,
                    speaker_id=speaker_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    explanation="Call terminated and caller blacklisted due to active voice clone attack.",
                    recommended_action="BLOCK",
                    verification_status=verification_session.status.value,
                    is_held=True,
                    transaction_amount=context.requested_transaction_amount,
                    hold_reason=verification_session.hold_reason,
                    flags=["Terminated & blacklisted as active voice attack"],
                    contributing_signals=signals_dict,
                )
            )

    return events


def filter_security_events(
    events: List[SecurityEvent],
    filter_type: str = "ALL",
    search_query: str = "",
    org_id: Optional[str] = None,
) -> List[SecurityEvent]:
    """
    Applies fast filtering and searching with strict organization-level tenant isolation.
    """
    filtered: List[SecurityEvent] = []
    filter_upper = filter_type.upper().strip()
    query_lower = search_query.lower().strip()

    for evt in events:
        # 1. Multi-tenant isolation: reject events from other organizations if org_id is provided
        if org_id and evt.organization_id != org_id:
            continue

        # 2. Fast Filter Categories
        if filter_upper == "CRITICAL" and evt.severity != SecurityEventSeverity.CRITICAL:
            continue
        elif filter_upper == "HIGH" and evt.severity != SecurityEventSeverity.HIGH:
            continue
        elif filter_upper == "MEDIUM" and evt.severity != SecurityEventSeverity.MEDIUM:
            continue
        elif filter_upper == "LOW" and evt.severity != SecurityEventSeverity.LOW:
            continue
        elif filter_upper == "UNRESOLVED" and evt.status != "OPEN":
            continue
        elif filter_upper == "VERIFICATION_REQUIRED":
            is_ver_req = (
                evt.recommended_action in ("SECONDARY_VERIFICATION", "CHALLENGE_CALLER", "HOLD_AND_STEP_UP")
                or evt.verification_status in ("PENDING", "CHALLENGE_REQUIRED", "VERIFICATION_IN_PROGRESS", "FAILED")
            )
            if not is_ver_req:
                continue
        elif filter_upper == "BLOCKED":
            is_blocked = (
                evt.recommended_action == "BLOCK"
                or evt.verification_status == "BLOCKED"
                or evt.event_type == SecurityEventType.CALL_BLOCKED
            )
            if not is_blocked:
                continue

        # 3. Free Text Search (Caller ID, Contact Name/ID, Call ID, Claimed Role, Flags, Event Type)
        if query_lower:
            match_call = query_lower in (evt.call_id or "").lower()
            match_caller = query_lower in (evt.caller_id or "").lower()
            match_contact = query_lower in (evt.contact_name or "").lower() or query_lower in (evt.contact_id or "").lower()
            match_role = query_lower in (evt.claimed_role or "").lower()
            match_type = query_lower in (evt.event_type.value if isinstance(evt.event_type, SecurityEventType) else str(evt.event_type)).lower()
            match_flags = any(query_lower in f.lower() for f in evt.flags)
            match_expl = query_lower in (evt.explanation or "").lower()

            if not (match_call or match_caller or match_contact or match_role or match_type or match_flags or match_expl):
                continue

        filtered.append(evt)

    return filtered


def calculate_event_metrics(events: List[SecurityEvent], org_id: Optional[str] = None) -> Dict[str, int]:
    """
    Computes top-level authoritative summary metrics for the Security Events Dashboard.
    """
    target_events = [e for e in events if (not org_id or e.organization_id == org_id)]

    active_threats = sum(
        1 for e in target_events
        if e.status == "OPEN" and e.severity in (SecurityEventSeverity.HIGH, SecurityEventSeverity.CRITICAL)
    )

    critical_events = sum(
        1 for e in target_events
        if e.severity == SecurityEventSeverity.CRITICAL
    )

    calls_requiring_verification = sum(
        1 for e in target_events
        if (
            e.recommended_action in ("SECONDARY_VERIFICATION", "CHALLENGE_CALLER", "HOLD_AND_STEP_UP")
            or e.verification_status in ("PENDING", "CHALLENGE_REQUIRED", "VERIFICATION_IN_PROGRESS")
        )
    )

    transactions_on_hold = sum(
        1 for e in target_events
        if e.is_held
    )

    blocked_calls = sum(
        1 for e in target_events
        if (
            e.recommended_action == "BLOCK"
            or e.verification_status == "BLOCKED"
            or e.event_type == SecurityEventType.CALL_BLOCKED
        )
    )

    return {
        "total_events": len(target_events),
        "active_threats": active_threats,
        "critical_events": critical_events,
        "calls_requiring_verification": calls_requiring_verification,
        "transactions_on_hold": transactions_on_hold,
        "blocked_calls": blocked_calls,
    }
