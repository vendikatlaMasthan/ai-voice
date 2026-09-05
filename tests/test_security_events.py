"""
Comprehensive Unit and Integration Tests for VoiceShield Feature 2:
Security Events & Alert Center Engine, Multi-Tenant Isolation, Severity Classification,
Filtering, Transaction Hold Events, and Audit Verification Linking.
"""

import unittest
import time
from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import VoiceShieldRiskEngine
from app.risk.verification import (
    RiskAction,
    SecondaryVerificationStateMachine,
    SecondaryVerificationStatus,
    VerificationSession,
)
from app.risk.events import (
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
    classify_event_severity,
    generate_security_events_from_analysis,
    filter_security_events,
    calculate_event_metrics,
)


class TestSecurityEventsAndAlertCenter(unittest.TestCase):
    """Test suite verifying Feature 2: Security Events & Alert Center."""

    def setUp(self):
        self.org_a = "00000000-0000-0000-0000-000000000001"
        self.org_b = "00000000-0000-0000-0000-000000000002"

    def test_1_event_severity_classification(self):
        """1. Verify authoritative classification across LOW, MEDIUM, HIGH, CRITICAL."""
        # Critical cases
        self.assertEqual(
            classify_event_severity(risk_score=95, event_type=SecurityEventType.HIGH_RISK_CALL, fake_prob=0.96),
            SecurityEventSeverity.CRITICAL,
        )
        self.assertEqual(
            classify_event_severity(risk_score=50, event_type=SecurityEventType.CALL_BLOCKED),
            SecurityEventSeverity.CRITICAL,
        )
        self.assertEqual(
            classify_event_severity(risk_score=50, event_type=SecurityEventType.HIGH_RISK_CALL, verification_status="BLOCKED"),
            SecurityEventSeverity.CRITICAL,
        )

        # High cases
        self.assertEqual(
            classify_event_severity(risk_score=75, event_type=SecurityEventType.DEEPFAKE_VOICE_CLONE, fake_prob=0.78),
            SecurityEventSeverity.HIGH,
        )
        self.assertEqual(
            classify_event_severity(risk_score=60, event_type=SecurityEventType.EXECUTIVE_IMPERSONATION),
            SecurityEventSeverity.HIGH,
        )
        self.assertEqual(
            classify_event_severity(risk_score=40, event_type=SecurityEventType.VERIFICATION_FAILED),
            SecurityEventSeverity.HIGH,
        )

        # Medium cases
        self.assertEqual(
            classify_event_severity(risk_score=45, event_type=SecurityEventType.SPEAKER_MISMATCH),
            SecurityEventSeverity.MEDIUM,
        )
        self.assertEqual(
            classify_event_severity(risk_score=40, event_type=SecurityEventType.ROLE_MISMATCH),
            SecurityEventSeverity.MEDIUM,
        )
        self.assertEqual(
            classify_event_severity(risk_score=38, event_type=SecurityEventType.ACOUSTIC_ANOMALY),
            SecurityEventSeverity.MEDIUM,
        )

        # Low cases
        self.assertEqual(
            classify_event_severity(risk_score=12, event_type=SecurityEventType.HIGH_RISK_CALL),
            SecurityEventSeverity.LOW,
        )

    def test_2_generate_critical_deepfake_and_executive_events(self):
        """2. Verify critical deepfake + executive impersonation generates rich event data."""
        ctx = CallContext(
            caller_id="+1 (415) 890-2100",
            contact_id="EMP-9001",
            claimed_role="Chief Executive Officer",
            is_caller_recognized=False,
            role_mismatch=True,
            requested_transaction_amount=85000.0,
            transaction_auto_hold_amount=5000.0,
            is_urgent=True,
        )

        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-2026-9082-AZ",
            recommended_action=RiskAction.HOLD_AND_STEP_UP.value,
            risk_score=94,
            risk_level="CRITICAL",
            context=ctx,
            flags=["Wav2Vec2 high neural synthesis probability (96.2%)", "High financial wire anomaly"],
        )

        events = generate_security_events_from_analysis(
            call_id="CALL-2026-9082-AZ",
            risk_score=94,
            risk_level="CRITICAL",
            deepfake_result={"prediction": "FAKE", "fake_probability": 0.962},
            speaker_result={"is_match": False, "similarity_score": 0.38, "speaker_id": "EMP-9001"},
            prosody_result={"acoustic_anomaly": 0.82},
            context=ctx,
            flags=["Wav2Vec2 high neural synthesis probability (96.2%)", "High financial wire anomaly"],
            recommended_action="BLOCK",
            verification_session=session,
            org_id=self.org_a,
        )

        self.assertGreaterEqual(len(events), 3)
        event_types = [e.event_type for e in events]
        self.assertIn(SecurityEventType.CALL_BLOCKED, event_types)
        self.assertIn(SecurityEventType.DEEPFAKE_VOICE_CLONE, event_types)
        self.assertIn(SecurityEventType.EXECUTIVE_IMPERSONATION, event_types)
        self.assertIn(SecurityEventType.TRANSACTION_AUTO_HOLD, event_types)

        # Check critical event data integrity
        clone_event = next(e for e in events if e.event_type == SecurityEventType.DEEPFAKE_VOICE_CLONE)
        self.assertEqual(clone_event.severity, SecurityEventSeverity.CRITICAL)
        self.assertEqual(clone_event.organization_id, self.org_a)
        self.assertTrue(clone_event.is_held)
        self.assertEqual(clone_event.transaction_amount, 85000.0)

    def test_3_transaction_hold_event_linking(self):
        """3. Verify transaction hold status is reflected in emitted events."""
        ctx = CallContext(
            caller_id="+15550199",
            contact_id="EMP-4102",
            claimed_role="Treasurer",
            requested_transaction_amount=34500.0,
            transaction_auto_hold_amount=10000.0,
        )
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-2026-HOLD",
            recommended_action=RiskAction.HOLD_AND_STEP_UP.value,
            risk_score=76,
            risk_level="HIGH",
            context=ctx,
            flags=["Synthetic acoustic artifact anomalies detected"],
        )

        events = generate_security_events_from_analysis(
            call_id="CALL-2026-HOLD",
            risk_score=76,
            risk_level="HIGH",
            deepfake_result={"prediction": "FAKE", "fake_probability": 0.784},
            speaker_result={"is_match": False, "similarity_score": 0.52},
            prosody_result={"acoustic_anomaly": 0.65},
            context=ctx,
            flags=["Synthetic acoustic artifact anomalies detected"],
            recommended_action="SECONDARY_VERIFICATION",
            verification_session=session,
            org_id=self.org_a,
        )

        hold_event = next(e for e in events if e.event_type == SecurityEventType.TRANSACTION_AUTO_HOLD)
        self.assertTrue(hold_event.is_held)
        self.assertEqual(hold_event.transaction_amount, 34500.0)
        self.assertEqual(hold_event.severity, SecurityEventSeverity.HIGH)
        self.assertIn("hold", hold_event.explanation.lower())

    def test_4_verification_state_events(self):
        """4. Verify state transitions (FAILED, ESCALATED, BLOCKED) generate corresponding events."""
        ctx = CallContext(caller_id="+15550200", requested_transaction_amount=12000.0)
        session = SecondaryVerificationStateMachine.initialize_session(
            call_id="CALL-2026-STATE",
            recommended_action=RiskAction.SECONDARY_VERIFICATION.value,
            risk_score=75,
            risk_level="HIGH",
            context=ctx,
            flags=["Acoustic anomaly"],
        )

        # Transition to FAILED
        SecondaryVerificationStateMachine.start_verification(session, method="REQUIRE_MFA_OTP")
        SecondaryVerificationStateMachine.complete_verification(session, success=False, notes="Incorrect MFA token")
        events_failed = generate_security_events_from_analysis(
            call_id="CALL-2026-STATE",
            risk_score=75,
            risk_level="HIGH",
            deepfake_result={"fake_probability": 0.60},
            speaker_result={},
            prosody_result={},
            context=ctx,
            flags=[],
            recommended_action="SECONDARY_VERIFICATION",
            verification_session=session,
            org_id=self.org_a,
        )
        self.assertTrue(any(e.event_type == SecurityEventType.VERIFICATION_FAILED for e in events_failed))

        # Transition to ESCALATED
        SecondaryVerificationStateMachine.escalate(session, notes="Escalated to Tier-2 SOC")
        events_escalated = generate_security_events_from_analysis(
            call_id="CALL-2026-STATE",
            risk_score=80,
            risk_level="HIGH",
            deepfake_result={"fake_probability": 0.60},
            speaker_result={},
            prosody_result={},
            context=ctx,
            flags=[],
            recommended_action="SECONDARY_VERIFICATION",
            verification_session=session,
            org_id=self.org_a,
        )
        self.assertTrue(any(e.event_type == SecurityEventType.VERIFICATION_ESCALATED for e in events_escalated))

        # Transition to BLOCKED
        SecondaryVerificationStateMachine.block(session, reason="Blacklisted voice attack")
        events_blocked = generate_security_events_from_analysis(
            call_id="CALL-2026-STATE",
            risk_score=95,
            risk_level="CRITICAL",
            deepfake_result={"fake_probability": 0.90},
            speaker_result={},
            prosody_result={},
            context=ctx,
            flags=[],
            recommended_action="BLOCK",
            verification_session=session,
            org_id=self.org_a,
        )
        self.assertTrue(any(e.event_type == SecurityEventType.CALL_BLOCKED for e in events_blocked))

    def test_5_event_filtering_categories(self):
        """5. Verify fast filtering by CRITICAL, HIGH, MEDIUM, LOW, UNRESOLVED, VERIFICATION_REQUIRED, BLOCKED."""
        events = [
            SecurityEvent(id="1", call_id="C1", organization_id=self.org_a, event_type=SecurityEventType.CALL_BLOCKED, severity=SecurityEventSeverity.CRITICAL, recommended_action="BLOCK", verification_status="BLOCKED", status="OPEN"),
            SecurityEvent(id="2", call_id="C2", organization_id=self.org_a, event_type=SecurityEventType.DEEPFAKE_VOICE_CLONE, severity=SecurityEventSeverity.HIGH, recommended_action="SECONDARY_VERIFICATION", verification_status="PENDING", status="OPEN"),
            SecurityEvent(id="3", call_id="C3", organization_id=self.org_a, event_type=SecurityEventType.SPEAKER_MISMATCH, severity=SecurityEventSeverity.MEDIUM, recommended_action="CHALLENGE_CALLER", verification_status="CHALLENGE_REQUIRED", status="OPEN"),
            SecurityEvent(id="4", call_id="C4", organization_id=self.org_a, event_type=SecurityEventType.HIGH_RISK_CALL, severity=SecurityEventSeverity.LOW, recommended_action="ALLOW", verification_status="VERIFIED", status="RESOLVED"),
        ]

        crit_filtered = filter_security_events(events, filter_type="CRITICAL")
        self.assertEqual(len(crit_filtered), 1)
        self.assertEqual(crit_filtered[0].id, "1")

        high_filtered = filter_security_events(events, filter_type="HIGH")
        self.assertEqual(len(high_filtered), 1)
        self.assertEqual(high_filtered[0].id, "2")

        med_filtered = filter_security_events(events, filter_type="MEDIUM")
        self.assertEqual(len(med_filtered), 1)
        self.assertEqual(med_filtered[0].id, "3")

        low_filtered = filter_security_events(events, filter_type="LOW")
        self.assertEqual(len(low_filtered), 1)
        self.assertEqual(low_filtered[0].id, "4")

        unresolved_filtered = filter_security_events(events, filter_type="UNRESOLVED")
        self.assertEqual(len(unresolved_filtered), 3)

        ver_req_filtered = filter_security_events(events, filter_type="VERIFICATION_REQUIRED")
        self.assertEqual(len(ver_req_filtered), 2)  # C2 and C3

        blocked_filtered = filter_security_events(events, filter_type="BLOCKED")
        self.assertEqual(len(blocked_filtered), 1)
        self.assertEqual(blocked_filtered[0].id, "1")

    def test_6_search_filtering(self):
        """6. Verify search matching on caller, contact, call_id, claimed_role, and explanation."""
        events = [
            SecurityEvent(id="1", call_id="CALL-ALPHA", organization_id=self.org_a, event_type=SecurityEventType.HIGH_RISK_CALL, severity=SecurityEventSeverity.CRITICAL, caller_id="+1 (415) 890-2100", contact_name="Jane Doe", claimed_role="Chief Executive Officer", explanation="Urgency pressure tactics"),
            SecurityEvent(id="2", call_id="CALL-BETA", organization_id=self.org_a, event_type=SecurityEventType.ROLE_MISMATCH, severity=SecurityEventSeverity.HIGH, caller_id="+1 (212) 555-0199", contact_name="Bob Smith", claimed_role="Treasurer", explanation="Role mismatch"),
        ]

        self.assertEqual(len(filter_security_events(events, search_query="415")), 1)
        self.assertEqual(len(filter_security_events(events, search_query="Jane")), 1)
        self.assertEqual(len(filter_security_events(events, search_query="Treasurer")), 1)
        self.assertEqual(len(filter_security_events(events, search_query="ALPHA")), 1)
        self.assertEqual(len(filter_security_events(events, search_query="Urgency")), 1)
        self.assertEqual(len(filter_security_events(events, search_query="nonexistent")), 0)

    def test_7_tenant_isolation_and_tampering_prevention(self):
        """7. Verify strict multi-tenant boundary: Organization A cannot see Organization B events."""
        events = [
            SecurityEvent(id="1", call_id="C1", organization_id=self.org_a, event_type=SecurityEventType.HIGH_RISK_CALL, severity=SecurityEventSeverity.CRITICAL),
            SecurityEvent(id="2", call_id="C2", organization_id=self.org_b, event_type=SecurityEventType.DEEPFAKE_VOICE_CLONE, severity=SecurityEventSeverity.HIGH),
        ]

        # Query Org A
        org_a_events = filter_security_events(events, org_id=self.org_a)
        self.assertEqual(len(org_a_events), 1)
        self.assertEqual(org_a_events[0].id, "1")

        # Query Org B
        org_b_events = filter_security_events(events, org_id=self.org_b)
        self.assertEqual(len(org_b_events), 1)
        self.assertEqual(org_b_events[0].id, "2")

    def test_8_dashboard_metrics_calculation(self):
        """8. Verify summary metrics calculation matches authoritative security invariants."""
        events = [
            SecurityEvent(id="1", call_id="C1", organization_id=self.org_a, event_type=SecurityEventType.CALL_BLOCKED, severity=SecurityEventSeverity.CRITICAL, recommended_action="BLOCK", verification_status="BLOCKED", is_held=True, status="OPEN"),
            SecurityEvent(id="2", call_id="C2", organization_id=self.org_a, event_type=SecurityEventType.DEEPFAKE_VOICE_CLONE, severity=SecurityEventSeverity.HIGH, recommended_action="SECONDARY_VERIFICATION", verification_status="PENDING", is_held=True, status="OPEN"),
            SecurityEvent(id="3", call_id="C3", organization_id=self.org_a, event_type=SecurityEventType.SPEAKER_MISMATCH, severity=SecurityEventSeverity.MEDIUM, recommended_action="CHALLENGE_CALLER", verification_status="CHALLENGE_REQUIRED", is_held=False, status="OPEN"),
            SecurityEvent(id="4", call_id="C4", organization_id=self.org_a, event_type=SecurityEventType.HIGH_RISK_CALL, severity=SecurityEventSeverity.LOW, recommended_action="ALLOW", verification_status="VERIFIED", is_held=False, status="RESOLVED"),
        ]

        metrics = calculate_event_metrics(events, org_id=self.org_a)
        self.assertEqual(metrics["total_events"], 4)
        self.assertEqual(metrics["active_threats"], 2)  # C1 and C2 (OPEN and HIGH/CRITICAL)
        self.assertEqual(metrics["critical_events"], 1)  # C1
        self.assertEqual(metrics["calls_requiring_verification"], 2)  # C2 and C3
        self.assertEqual(metrics["transactions_on_hold"], 2)  # C1 and C2
        self.assertEqual(metrics["blocked_calls"], 1)  # C1


if __name__ == "__main__":
    unittest.main()
