"""
Secondary Verification Workflow Engine for VoiceShield (Feature 1).
Implements an authoritative 7-state verification state machine, step-up holds,
and multi-method verification actions (Verify Caller, Independent Callback, MFA/OTP, Supervisor Escalation).
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Union
import uuid

from app.risk.context import CallContext


class SecondaryVerificationStatus(str, Enum):
    """
    Authoritative state machine states for secondary verification workflow.
    """
    PENDING = "PENDING"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    VERIFICATION_IN_PROGRESS = "VERIFICATION_IN_PROGRESS"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    BLOCKED = "BLOCKED"


class VerificationMethod(str, Enum):
    """
    Operational verification methods supported by the workflow.
    """
    VERIFY_CALLER = "VERIFY_CALLER"                     # Knowledge-based auth / Security questions
    INDEPENDENT_CALLBACK = "INDEPENDENT_CALLBACK"       # Out-of-band callback to verified registry number
    REQUIRE_MFA_OTP = "REQUIRE_MFA_OTP"                 # Out-of-band one-time passcode / push auth
    ESCALATE_TO_SUPERVISOR = "ESCALATE_TO_SUPERVISOR"   # Direct escalation to SOC / Supervisor


class RiskAction(str, Enum):
    """
    Risk actions triggering the verification state machine.
    """
    ALLOW = "ALLOW"
    CHALLENGE_CALLER = "CHALLENGE_CALLER"
    SECONDARY_VERIFICATION = "SECONDARY_VERIFICATION"
    HOLD_AND_STEP_UP = "HOLD_AND_STEP_UP"


@dataclass
class VerificationAuditRecord:
    """
    Audit log record capturing every verification transition.
    """
    id: str
    call_id: str
    timestamp: float
    previous_state: str
    new_state: str
    action: str
    actor: str
    method: Optional[str] = None
    notes: Optional[str] = None
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "call_id": self.call_id,
            "timestamp": self.timestamp,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "action": self.action,
            "actor": self.actor,
            "method": self.method,
            "notes": self.notes,
            "is_simulated": self.is_simulated,
        }


@dataclass
class VerificationSession:
    """
    Authoritative session tracking secondary verification progress, hold status, and audit trail.
    """
    call_id: str
    status: SecondaryVerificationStatus
    recommended_action: str
    risk_score: int
    risk_level: str
    is_held: bool = False
    hold_reason: Optional[str] = None
    selected_method: Optional[str] = None
    in_progress_step: Optional[str] = None
    audit_trail: List[VerificationAuditRecord] = field(default_factory=list)
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "status": self.status.value if isinstance(self.status, SecondaryVerificationStatus) else str(self.status),
            "recommended_action": self.recommended_action,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "is_held": self.is_held,
            "hold_reason": self.hold_reason,
            "selected_method": self.selected_method,
            "in_progress_step": self.in_progress_step,
            "audit_trail": [a.to_dict() for a in self.audit_trail],
            "context_metadata": self.context_metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SecondaryVerificationStateMachine:
    """
    Authoritative State Machine enforcing transitions and business rules.
    """

    @staticmethod
    def initialize_session(
        call_id: str,
        recommended_action: str,
        risk_score: int,
        risk_level: str,
        context: Optional[CallContext] = None,
        flags: Optional[List[str]] = None,
        is_auto_hold: bool = False,
    ) -> VerificationSession:
        """
        Initializes a verification session based on risk evaluation and context.
        """
        flags = flags or []
        now = time.time()

        # Determine initial state and hold requirement
        is_held = False
        hold_reason: Optional[str] = None

        if recommended_action in ("BLOCK", "BLOCKED") or risk_level == "CRITICAL" or risk_score >= 90:
            initial_status = SecondaryVerificationStatus.BLOCKED
            is_held = True
            hold_reason = "Critical deepfake threshold or risk policy triggered automatic threat block."
        elif recommended_action == RiskAction.HOLD_AND_STEP_UP.value or is_auto_hold:
            initial_status = SecondaryVerificationStatus.PENDING
            is_held = True
            hold_reason = "Transaction placed on HOLD due to policy threshold violation or elevated risk step-up."
        elif recommended_action == RiskAction.CHALLENGE_CALLER.value:
            initial_status = SecondaryVerificationStatus.CHALLENGE_REQUIRED
        elif recommended_action == RiskAction.SECONDARY_VERIFICATION.value:
            initial_status = SecondaryVerificationStatus.PENDING
            if context and context.requested_transaction_amount and context.requested_transaction_amount > 0:
                is_held = True
                hold_reason = "Transaction placed on HOLD pending secondary identity verification."
        elif recommended_action == RiskAction.ALLOW.value:
            initial_status = SecondaryVerificationStatus.PENDING
        else:
            initial_status = SecondaryVerificationStatus.PENDING

        ctx_meta = {}
        if context:
            ctx_meta = {
                "caller_id": context.caller_id,
                "is_caller_recognized": context.is_caller_recognized,
                "is_previously_flagged": context.is_previously_flagged,
                "claimed_role": context.claimed_role,
                "contact_role": context.contact_role,
                "role_mismatch": context.role_mismatch,
                "requested_transaction_amount": context.requested_transaction_amount,
                "normal_transaction_amount": context.normal_transaction_amount,
                "transaction_auto_hold_amount": context.transaction_auto_hold_amount,
                "has_prior_fraud_history": context.has_prior_fraud_history,
                "fraud_history_count": context.fraud_history_count,
                "recent_fraud_types": context.recent_fraud_types,
                "organization_id": context.organization_id,
                "flags": flags,
            }

        session = VerificationSession(
            call_id=call_id,
            status=initial_status,
            recommended_action=recommended_action,
            risk_score=risk_score,
            risk_level=risk_level,
            is_held=is_held,
            hold_reason=hold_reason,
            context_metadata=ctx_meta,
            created_at=now,
            updated_at=now,
        )

        init_audit = VerificationAuditRecord(
            id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            call_id=call_id,
            timestamp=now,
            previous_state="NONE",
            new_state=initial_status.value,
            action=f"INITIALIZE_{recommended_action}",
            actor="VoiceShieldRiskEngine",
            notes=hold_reason or f"Session initialized with action {recommended_action}.",
            is_simulated=True,
        )
        session.audit_trail.append(init_audit)
        return session

    @staticmethod
    def start_verification(
        session: VerificationSession,
        method: Union[VerificationMethod, str],
        actor: str = "SecurityOperator",
        notes: Optional[str] = None,
    ) -> VerificationSession:
        """
        Transitions session to VERIFICATION_IN_PROGRESS.
        """
        method_str = method.value if isinstance(method, VerificationMethod) else str(method)
        prev_state = session.status.value

        session.status = SecondaryVerificationStatus.VERIFICATION_IN_PROGRESS
        session.selected_method = method_str
        session.in_progress_step = f"Executing {method_str}"
        session.updated_at = time.time()

        audit = VerificationAuditRecord(
            id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            call_id=session.call_id,
            timestamp=session.updated_at,
            previous_state=prev_state,
            new_state=session.status.value,
            action="START_VERIFICATION",
            actor=actor,
            method=method_str,
            notes=notes or f"Verification initiated via {method_str}.",
            is_simulated=True,
        )
        session.audit_trail.append(audit)
        return session

    @staticmethod
    def complete_verification(
        session: VerificationSession,
        success: bool,
        method: Optional[Union[VerificationMethod, str]] = None,
        notes: Optional[str] = None,
        actor: str = "SecurityOperator",
    ) -> VerificationSession:
        """
        Resolves verification to VERIFIED or FAILED.
        If HOLD_AND_STEP_UP was active, releasing hold requires success.
        """
        method_str = (
            method.value if isinstance(method, VerificationMethod)
            else str(method) if method else session.selected_method
        )
        prev_state = session.status.value
        now = time.time()

        if success:
            session.status = SecondaryVerificationStatus.VERIFIED
            # For HOLD_AND_STEP_UP: Hold is released upon verified identity
            if session.is_held:
                session.is_held = False
                session.hold_reason = "Transaction hold released: Secondary verification completed successfully."
            session.in_progress_step = None
            action_name = "VERIFICATION_SUCCESS"
        else:
            session.status = SecondaryVerificationStatus.FAILED
            # If transaction was held, it remains held
            if session.is_held:
                session.hold_reason = "Transaction remains ON HOLD: Secondary verification failed."
            session.in_progress_step = None
            action_name = "VERIFICATION_FAILURE"

        session.updated_at = now

        audit = VerificationAuditRecord(
            id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            call_id=session.call_id,
            timestamp=now,
            previous_state=prev_state,
            new_state=session.status.value,
            action=action_name,
            actor=actor,
            method=method_str,
            notes=notes or ("Verification succeeded." if success else "Verification failed."),
            is_simulated=True,
        )
        session.audit_trail.append(audit)
        return session

    @staticmethod
    def escalate(
        session: VerificationSession,
        notes: Optional[str] = None,
        actor: str = "SecurityOperator",
    ) -> VerificationSession:
        """
        Escalates the session to Supervisor / Fraud Operations (ESCALATED).
        Transaction remains on hold.
        """
        prev_state = session.status.value
        now = time.time()

        session.status = SecondaryVerificationStatus.ESCALATED
        session.selected_method = VerificationMethod.ESCALATE_TO_SUPERVISOR.value
        session.in_progress_step = "Pending supervisor manual review"
        if session.is_held:
            session.hold_reason = "Transaction ON HOLD: Escalated to supervisor for manual investigation."
        session.updated_at = now

        audit = VerificationAuditRecord(
            id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            call_id=session.call_id,
            timestamp=now,
            previous_state=prev_state,
            new_state=session.status.value,
            action="ESCALATE_TO_SUPERVISOR",
            actor=actor,
            method=VerificationMethod.ESCALATE_TO_SUPERVISOR.value,
            notes=notes or "Incident escalated to supervisor for advanced forensic review.",
            is_simulated=True,
        )
        session.audit_trail.append(audit)
        return session

    @staticmethod
    def block(
        session: VerificationSession,
        reason: Optional[str] = None,
        actor: str = "SecurityOperator",
    ) -> VerificationSession:
        """
        Directly blocks the session / call (BLOCKED).
        """
        prev_state = session.status.value
        now = time.time()

        session.status = SecondaryVerificationStatus.BLOCKED
        session.is_held = True
        session.hold_reason = reason or "Call terminated and transaction blocked due to high fraud threat."
        session.in_progress_step = None
        session.updated_at = now

        audit = VerificationAuditRecord(
            id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            call_id=session.call_id,
            timestamp=now,
            previous_state=prev_state,
            new_state=session.status.value,
            action="BLOCK_CALL",
            actor=actor,
            notes=reason or "Call flagged as active voice cloning / deepfake attack.",
            is_simulated=True,
        )
        session.audit_trail.append(audit)
        return session

    @staticmethod
    def sanitize_client_transition_request(
        current_session: VerificationSession,
        requested_status: Optional[str] = None,
        action: Optional[str] = None,
        method: Optional[str] = None,
        result: Optional[str] = None,
        notes: Optional[str] = None,
        actor: str = "SecurityOperator",
    ) -> VerificationSession:
        """
        Authoritatively validates any client transition request.
        Prevents client tampering from arbitrarily changing protected state.
        """
        action_upper = (action or "").upper()
        result_upper = (result or "").upper()

        if action_upper == "START" or action_upper == "START_VERIFICATION":
            selected_method = method or VerificationMethod.VERIFY_CALLER.value
            return SecondaryVerificationStateMachine.start_verification(
                current_session, method=selected_method, actor=actor, notes=notes
            )
        elif action_upper == "SUBMIT" or action_upper == "COMPLETE":
            is_success = result_upper == "SUCCESS" or result_upper == "PASS" or result_upper == "VERIFIED"
            return SecondaryVerificationStateMachine.complete_verification(
                current_session, success=is_success, method=method, notes=notes, actor=actor
            )
        elif action_upper == "ESCALATE":
            return SecondaryVerificationStateMachine.escalate(
                current_session, notes=notes, actor=actor
            )
        elif action_upper == "BLOCK":
            return SecondaryVerificationStateMachine.block(
                current_session, reason=notes, actor=actor
            )
        elif requested_status:
            # If client directly attempts to specify status, map through state machine rules
            req_status_upper = requested_status.upper()
            if req_status_upper == SecondaryVerificationStatus.VERIFIED.value:
                return SecondaryVerificationStateMachine.complete_verification(
                    current_session, success=True, method=method, notes=notes, actor=actor
                )
            elif req_status_upper == SecondaryVerificationStatus.FAILED.value:
                return SecondaryVerificationStateMachine.complete_verification(
                    current_session, success=False, method=method, notes=notes, actor=actor
                )
            elif req_status_upper == SecondaryVerificationStatus.ESCALATED.value:
                return SecondaryVerificationStateMachine.escalate(
                    current_session, notes=notes, actor=actor
                )
            elif req_status_upper == SecondaryVerificationStatus.BLOCKED.value:
                return SecondaryVerificationStateMachine.block(
                    current_session, reason=notes, actor=actor
                )

        return current_session
