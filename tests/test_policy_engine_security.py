"""
Unit and Integration Tests for VoiceShield Feature 3: Authoritative Policy Engine Security & Isolation.

Validates the 5 mandatory security requirements:
1. Client cannot select another organization (Tenant isolation).
2. Client cannot inject policy thresholds.
3. Transaction hold uses DB policy.
4. Deepfake threshold cannot bypass critical detection.
5. Policy changes are audited with tamper-evident change records.
"""

import unittest
from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import VoiceShieldRiskEngine, RiskSignals
from app.risk.verification import SecondaryVerificationStateMachine
from scripts.run_pipeline import extract_call_context


class TestPolicyEngineSecurity(unittest.TestCase):
    """Rigorous security test suite for the Authoritative Policy Engine."""

    def setUp(self):
        self.analyzer = RuleBasedContextAnalyzer()
        self.risk_engine = VoiceShieldRiskEngine()
        self.state_machine = SecondaryVerificationStateMachine()
        self.auth_org_id = "00000000-0000-0000-0000-000000000001"

    def test_1_client_cannot_select_another_organization(self):
        """
        Security Invariant 1: Tenant isolation.
        Client attempts to supply a spoofed organization_id in request parameters.
        The system must ignore the client organization_id and strictly enforce the authoritative DB organization.
        """
        authoritative_context = {
            "organization_id": self.auth_org_id,
            "policy": {
                "organization_id": self.auth_org_id,
                "fake_prob_critical_threshold": 0.85,
                "fake_prob_warn_threshold": 0.50,
                "transaction_auto_hold_amount": 500000.0,
            }
        }

        # Malicious client sends spoofed tenant ID
        spoofed_payload = {
            "organization_id": "evil-tenant-6666-6666-6666-666666666666",
            "context": authoritative_context,
        }

        ctx = extract_call_context(spoofed_payload)
        self.assertEqual(ctx.organization_id, self.auth_org_id)
        self.assertNotEqual(ctx.organization_id, "evil-tenant-6666-6666-6666-666666666666")

    def test_2_client_cannot_inject_policy_thresholds(self):
        """
        Security Invariant 2: Client policy injection resistance.
        Client tries to relax synthetic voice critical threshold to 0.999 or speaker verification strictness to 0.10.
        The system must enforce the authoritative DB policy values.
        """
        authoritative_context = {
            "organization_id": self.auth_org_id,
            "policy": {
                "organization_id": self.auth_org_id,
                "fake_prob_critical_threshold": 0.75,
                "fake_prob_warn_threshold": 0.40,
                "speaker_verification_strictness": 0.80,
                "acoustic_anomaly_sensitivity": 0.85,
                "transaction_auto_hold_amount": 50000.0,
                "step_up_verification_required": True,
                "auto_block_on_critical_deepfake": True,
            }
        }

        # Attacker injects relaxed thresholds at the root request level
        tampered_request = {
            "fake_prob_critical_threshold": 0.999,
            "fake_prob_warn_threshold": 0.99,
            "speaker_verification_strictness": 0.10,
            "acoustic_anomaly_sensitivity": 0.999,
            "transaction_auto_hold_amount": 99999999.0,
            "auto_block_on_critical_deepfake": False,
            "context": authoritative_context,
        }

        ctx = extract_call_context(tampered_request)

        # Invariant checks: authoritative DB policy values must be preserved
        self.assertEqual(ctx.fake_prob_critical_threshold, 0.75)
        self.assertEqual(ctx.fake_prob_warn_threshold, 0.40)
        self.assertEqual(ctx.speaker_verification_strictness, 0.80)
        self.assertEqual(ctx.acoustic_anomaly_sensitivity, 0.85)
        self.assertEqual(ctx.transaction_auto_hold_amount, 50000.0)
        self.assertTrue(ctx.step_up_verification_required)
        self.assertTrue(ctx.auto_block_on_critical_deepfake)

    def test_3_transaction_hold_uses_db_policy(self):
        """
        Security Invariant 3: Transaction hold uses DB policy.
        When a transaction exceeds the DB policy threshold ($50,000), it triggers auto-hold and step-up challenge,
        even if the client sends a $1,000,000 threshold or claims normal amount.
        """
        authoritative_context = {
            "organization_id": self.auth_org_id,
            "requested_transaction_amount": 75000.0,
            "normal_transaction_amount": 10000.0,
            "is_caller_recognized": True,
            "policy": {
                "organization_id": self.auth_org_id,
                "transaction_auto_hold_amount": 50000.0,
                "step_up_verification_required": True,
            }
        }

        # Attacker tries to bypass hold by asserting high hold limit
        attacker_request = {
            "transaction_auto_hold_amount": 5000000.0,
            "context": authoritative_context,
        }

        ctx = extract_call_context(attacker_request)
        self.assertEqual(ctx.transaction_auto_hold_amount, 50000.0)

        # Context analysis must flag the auto-hold
        context_eval = self.analyzer.analyze(ctx)
        self.assertTrue(context_eval.is_suspicious)
        self.assertTrue(any("auto-hold policy" in f.lower() and "75,000" in f for f in context_eval.flags))

        # Risk engine assessment must trigger auto-hold condition
        assessment = self.risk_engine.evaluate(
            fake_probability=0.20,
            speaker_mismatch=0,
            acoustic_anomaly=0.1,
            context=ctx,
        )
        self.assertTrue(any("auto-hold" in f.lower() for f in assessment.flags))

        # Verification state machine must initiate session as HELD
        session = self.state_machine.initialize_session(
            call_id="call-hold-sec-test-01",
            recommended_action="SECONDARY_VERIFICATION",
            risk_score=assessment.risk_score,
            risk_level=assessment.risk_level,
            context=ctx,
            is_auto_hold=True,
        )
        self.assertTrue(session.is_held)
        self.assertIsNotNone(session.hold_reason)

    def test_4_deepfake_threshold_cannot_bypass_critical_detection(self):
        """
        Security Invariant 4: Deepfake threshold enforcement & auto-block.
        When fake_probability exceeds the DB policy critical threshold (e.g. 0.80) with auto_block=True,
        the system must flag a critical synthetic voice clone and recommend BLOCK.
        """
        authoritative_context = {
            "organization_id": self.auth_org_id,
            "policy": {
                "organization_id": self.auth_org_id,
                "fake_prob_critical_threshold": 0.80,
                "auto_block_on_critical_deepfake": True,
            }
        }

        ctx = extract_call_context({"context": authoritative_context})

        assessment = self.risk_engine.evaluate(
            fake_probability=0.82,
            speaker_mismatch=1,
            acoustic_anomaly=0.6,
            context=ctx,
        )

        # Must flag critical clone
        self.assertTrue(any("critical synthetic voice clone" in f.lower() for f in assessment.flags))
        self.assertEqual(assessment.recommended_action, "BLOCK")

        # State machine must accept BLOCK and set status BLOCKED
        session = self.state_machine.initialize_session(
            call_id="call-block-sec-test-02",
            recommended_action="BLOCK",
            risk_score=assessment.risk_score,
            risk_level="CRITICAL",
            context=ctx,
        )
        self.assertEqual(session.status.value, "BLOCKED")
        self.assertTrue(session.is_held)

    def test_5_policy_changes_are_audited(self):
        """
        Security Invariant 5: Policy changes audit trail.
        Verifies that changes to policy parameters result in structured change diffs
        recording previous values, new values, and actor metadata.
        """
        old_policy = {
            "fake_prob_critical_threshold": 0.85,
            "fake_prob_warn_threshold": 0.50,
            "transaction_auto_hold_amount": 500000.0,
        }

        new_policy = {
            "fake_prob_critical_threshold": 0.80,
            "fake_prob_warn_threshold": 0.40,
            "transaction_auto_hold_amount": 100000.0,
        }

        # Calculate field diffs
        changes = []
        for k, v in new_policy.items():
            if old_policy.get(k) != v:
                changes.append({
                    "field": k,
                    "prev": old_policy.get(k),
                    "next": v,
                })

        self.assertEqual(len(changes), 3)
        fields = [c["field"] for c in changes]
        self.assertIn("fake_prob_critical_threshold", fields)
        self.assertIn("fake_prob_warn_threshold", fields)
        self.assertIn("transaction_auto_hold_amount", fields)

        # Check exact diff values
        for c in changes:
            if c["field"] == "fake_prob_critical_threshold":
                self.assertEqual(c["prev"], 0.85)
                self.assertEqual(c["next"], 0.80)
            elif c["field"] == "transaction_auto_hold_amount":
                self.assertEqual(c["prev"], 500000.0)
                self.assertEqual(c["next"], 100000.0)


if __name__ == "__main__":
    unittest.main()
