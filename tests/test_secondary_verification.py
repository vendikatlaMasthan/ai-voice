"""
Comprehensive Unit and Integration Tests for VoiceShield Feature 1:
Secondary Verification Workflow, State Machine, Step-Up Holds, and Security Invariants.
"""

import unittest
from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import VoiceShieldRiskEngine
from app.risk.verification import (
    RiskAction,
    SecondaryVerificationStateMachine,
    SecondaryVerificationStatus,
    VerificationMethod,
    VerificationSession,
)
from scripts.run_pipeline import extract_call_context


class TestSecondaryVerificationWorkflow(unittest.TestCase):
    """Test suite verifying Feature 1: Secondary Verification Workflow."""

    def setUp(self):
        self.risk_engine = VoiceShieldRiskEngine()
        self.context_analyzer = RuleBasedContextAnalyzer()

    def test_1_allow_action_no_verification_hold(self):
        """1. ALLOW → no verification required, not held, PENDING state."""
        ctx = CallContext(
            caller_id="+15550100",
            is_caller_recognized=True,
            claimed_role="Support",
            requested_transaction_amount=500.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-001",
            recommended_action=RiskAction.ALLOW.value,
            risk_score=15,
            risk_level="LOW",
            context=ctx,
            flags=[],
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.PENDING)
        self.assertFalse(session.is_held)
        self.assertIsNone(session.hold_reason)
        self.assertGreaterEqual(len(session.audit_trail), 1)
        self.assertEqual(session.audit_trail[0].new_state, "PENDING")

    def test_2_challenge_caller_action(self):
        """2. CHALLENGE_CALLER → CHALLENGE_REQUIRED state."""
        ctx = CallContext(
            caller_id="+15550101",
            is_caller_recognized=False,
            claimed_role="Customer",
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-002",
            recommended_action=RiskAction.CHALLENGE_CALLER.value,
            risk_score=48,
            risk_level="MEDIUM",
            context=ctx,
            flags=["Caller not recognized in registry"],
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.CHALLENGE_REQUIRED)
        self.assertFalse(session.is_held)
        self.assertEqual(len(session.audit_trail), 1)

    def test_3_secondary_verification_action(self):
        """3. SECONDARY_VERIFICATION → verification required / PENDING state."""
        ctx = CallContext(
            caller_id="+15550102",
            is_caller_recognized=False,
            claimed_role="Executive",
            requested_transaction_amount=25000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-003",
            recommended_action=RiskAction.SECONDARY_VERIFICATION.value,
            risk_score=78,
            risk_level="HIGH",
            context=ctx,
            flags=["Synthetic acoustic markers detected", "Executive impersonation risk"],
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.PENDING)
        self.assertTrue(session.is_held)
        self.assertIn("HOLD", session.hold_reason or "")

    def test_4_hold_and_step_up_action(self):
        """4. HOLD_AND_STEP_UP → transaction placed on HOLD."""
        ctx = CallContext(
            caller_id="+15550103",
            is_caller_recognized=True,
            requested_transaction_amount=800000.0,
            transaction_auto_hold_amount=500000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-004",
            recommended_action=RiskAction.HOLD_AND_STEP_UP.value,
            risk_score=85,
            risk_level="HIGH",
            context=ctx,
            flags=["Requested transaction exceeds organization auto-hold policy ($500,000.00)"],
            is_auto_hold=True,
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.PENDING)
        self.assertTrue(session.is_held)
        self.assertIsNotNone(session.hold_reason)
        self.assertIn("HOLD", session.hold_reason)

    def test_5_successful_verification_flow_releases_hold(self):
        """5. Successful verification: PENDING -> IN_PROGRESS -> VERIFIED (releases hold)."""
        ctx = CallContext(
            caller_id="+15550104",
            is_caller_recognized=False,
            requested_transaction_amount=50000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-005",
            recommended_action=RiskAction.SECONDARY_VERIFICATION.value,
            risk_score=75,
            risk_level="HIGH",
            context=ctx,
        )
        self.assertTrue(session.is_held)

        # Step A: Operator starts verification with MFA / OTP
        session = SecondaryVerificationStateMachine.start_verification(
            session=session,
            method=VerificationMethod.REQUIRE_MFA_OTP,
            actor="SecOps_Agent_07",
            notes="Sent out-of-band OTP code to enrolled device.",
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.VERIFICATION_IN_PROGRESS)
        self.assertEqual(session.selected_method, "REQUIRE_MFA_OTP")
        self.assertTrue(session.is_held)

        # Step B: Operator submits successful OTP verification result
        session = SecondaryVerificationStateMachine.complete_verification(
            session=session,
            success=True,
            method=VerificationMethod.REQUIRE_MFA_OTP,
            notes="Caller entered valid 6-digit OTP code 948201.",
            actor="SecOps_Agent_07",
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.VERIFIED)
        self.assertFalse(session.is_held)  # Hold MUST be released
        self.assertIn("released", session.hold_reason.lower())
        self.assertEqual(len(session.audit_trail), 3)

    def test_6_failed_verification_flow_preserves_hold(self):
        """6. Failed verification: PENDING -> IN_PROGRESS -> FAILED (hold remains active)."""
        ctx = CallContext(
            caller_id="+15550105",
            is_caller_recognized=False,
            requested_transaction_amount=120000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-006",
            recommended_action=RiskAction.HOLD_AND_STEP_UP.value,
            risk_score=82,
            risk_level="HIGH",
            context=ctx,
            is_auto_hold=True,
        )
        self.assertTrue(session.is_held)

        # Step A: Operator starts independent callback
        session = SecondaryVerificationStateMachine.start_verification(
            session=session,
            method=VerificationMethod.INDEPENDENT_CALLBACK,
            actor="SecOps_Agent_09",
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.VERIFICATION_IN_PROGRESS)

        # Step B: Callback fails (unreachable / wrong person)
        session = SecondaryVerificationStateMachine.complete_verification(
            session=session,
            success=False,
            method=VerificationMethod.INDEPENDENT_CALLBACK,
            notes="Independent callback rang with no answer.",
            actor="SecOps_Agent_09",
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.FAILED)
        self.assertTrue(session.is_held)  # Hold MUST NOT be released
        self.assertIn("remains on hold", session.hold_reason.lower())

    def test_7_escalation_to_supervisor(self):
        """7. Escalation: transitions to ESCALATED state and retains hold."""
        ctx = CallContext(
            caller_id="+15550106",
            is_caller_recognized=False,
            claimed_role="CFO",
            requested_transaction_amount=350000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-007",
            recommended_action=RiskAction.SECONDARY_VERIFICATION.value,
            risk_score=88,
            risk_level="HIGH",
            context=ctx,
        )
        session = SecondaryVerificationStateMachine.escalate(
            session=session,
            notes="Suspicious acoustic variance; transferring to Fraud Operations Manager.",
            actor="Operator_Jane",
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.ESCALATED)
        self.assertEqual(session.selected_method, "ESCALATE_TO_SUPERVISOR")
        self.assertTrue(session.is_held)
        self.assertTrue(any(a.action == "ESCALATE_TO_SUPERVISOR" for a in session.audit_trail))

    def test_8_critical_block_condition(self):
        """8. Critical / blocking condition: transitions to BLOCKED state."""
        ctx = CallContext(
            caller_id="+15550107",
            is_caller_recognized=False,
            claimed_role="CEO",
            has_prior_fraud_history=True,
            fraud_history_count=4,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-008",
            recommended_action=RiskAction.SECONDARY_VERIFICATION.value,
            risk_score=96,
            risk_level="CRITICAL",
            context=ctx,
        )
        self.assertEqual(session.status, SecondaryVerificationStatus.BLOCKED)
        self.assertTrue(session.is_held)

        # Direct block invocation
        session_manual_block = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-TEST-008-B",
            recommended_action=RiskAction.CHALLENGE_CALLER.value,
            risk_score=50,
            risk_level="MEDIUM",
            context=ctx,
        )
        blocked_session = SecondaryVerificationStateMachine.block(
            session=session_manual_block,
            reason="Confirmed synthetic clone spoofing attempt.",
            actor="SecOps_Lead",
        )
        self.assertEqual(blocked_session.status, SecondaryVerificationStatus.BLOCKED)
        self.assertTrue(blocked_session.is_held)

    def test_9_protected_fields_cannot_be_client_overridden(self):
        """9. Security verification: protected security fields cannot be tampered with."""
        server_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": False,
            "is_previously_flagged": True,
            "contact_role": "Junior Clerk",
            "fraud_history_count": 3,
            "has_prior_fraud_history": True,
            "recent_fraud_types": ["VOICE_CLONE_ATTEMPT"],
            "transaction_auto_hold_amount": 100000.0,
            "role_mismatch": True,
        }
        # Client tries to override all protected fields at root
        client_tamper_payload = {
            "organization_id": "99999999-9999-9999-9999-999999999999",
            "is_caller_recognized": True,
            "is_previously_flagged": False,
            "contact_role": "CEO",
            "fraud_history_count": 0,
            "has_prior_fraud_history": False,
            "recent_fraud_types": [],
            "transaction_auto_hold_amount": 99999999.0,
            "role_mismatch": False,
            "is_verified": True,
            "risk_score": 5,
            "risk_level": "LOW",
            "context": server_context,
        }
        extracted_ctx = extract_call_context(client_tamper_payload)

        # Verify all server-authoritative protections held
        self.assertEqual(extracted_ctx.organization_id, "00000000-0000-0000-0000-000000000001")
        self.assertFalse(extracted_ctx.is_caller_recognized)
        self.assertTrue(extracted_ctx.is_previously_flagged)
        self.assertEqual(extracted_ctx.contact_role, "Junior Clerk")
        self.assertEqual(extracted_ctx.fraud_history_count, 3)
        self.assertTrue(extracted_ctx.has_prior_fraud_history)
        self.assertEqual(extracted_ctx.recent_fraud_types, ["VOICE_CLONE_ATTEMPT"])
        self.assertEqual(extracted_ctx.transaction_auto_hold_amount, 100000.0)

    def test_10_legitimate_transaction_and_role_updates_work(self):
        """10. Legitimate claimed_role and transaction amount updates still work properly."""
        server_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "contact_role": "Analyst",
            "is_caller_recognized": True,
        }
        legitimate_update = {
            "claimed_role": "Treasurer",
            "requested_amount": 45000.0,
            "normal_amount": 5000.0,
            "is_urgent": True,
            "urgency_reason": "Escrow closing",
            "context": server_context,
        }
        extracted_ctx = extract_call_context(legitimate_update)
        self.assertEqual(extracted_ctx.claimed_role, "Treasurer")
        self.assertEqual(extracted_ctx.requested_transaction_amount, 45000.0)
        self.assertEqual(extracted_ctx.normal_transaction_amount, 5000.0)
        self.assertTrue(extracted_ctx.is_urgent)
        self.assertEqual(extracted_ctx.urgency_reason, "Escrow closing")
        self.assertTrue(extracted_ctx.role_mismatch)  # Claimed Treasurer vs Contact Analyst


if __name__ == "__main__":
    unittest.main()
