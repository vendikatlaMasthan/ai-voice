"""
Unit and Integration Tests for VoiceShield Security Hardening & Trust Boundaries.
Explicitly validates protection against client-side parameter tampering:
A. Client attempts to change organization_id to another tenant.
B. Client sends is_caller_recognized=true for an unknown caller.
C. Client sends is_previously_flagged=false when DB/server says flagged.
D. Client sends role_mismatch=false when claimed role conflicts with DB role.
E. Client sends fake is_verified=true.
F. Client sends fake transaction_auto_hold_amount.
G. Client sends fake fraud_history_count.
H. Root-level request fields attempt to overwrite enriched context in scripts/run_pipeline.py.
I. Context extraction prevents override of protected security fields.
J. Legitimate claimed_role and transaction amount updates still work correctly.
"""

import unittest
from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import VoiceShieldRiskEngine
from scripts.run_pipeline import extract_call_context


class TestSecurityHardeningTrustBoundaries(unittest.TestCase):
    """Test suite verifying trust boundaries and parameter tampering resistance."""

    def setUp(self):
        self.analyzer = RuleBasedContextAnalyzer()
        self.risk_engine = VoiceShieldRiskEngine()

    def test_a_tenant_isolation_boundary(self):
        """A. Client attempts to change organization_id to another tenant."""
        # Enriched context has the authoritative tenant
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "is_previously_flagged": False,
        }
        # Attacker injects another tenant ID at root
        attacker_args = {
            "organization_id": "99999999-9999-9999-9999-999999999999",
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertEqual(ctx.organization_id, "00000000-0000-0000-0000-000000000001")
        self.assertNotEqual(ctx.organization_id, "99999999-9999-9999-9999-999999999999")

    def test_b_unknown_caller_recognition_tampering(self):
        """B. Client sends is_caller_recognized=true for an unknown caller."""
        # Server authoritative context says caller is unknown
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "caller_id": "+15559999",
            "is_caller_recognized": False,
            "claimed_role": "CEO",
        }
        # Attacker tries to bypass unknown caller check by sending True at root
        attacker_args = {
            "is_caller_recognized": True,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertFalse(ctx.is_caller_recognized)

        eval_res = self.analyzer.analyze(ctx)
        self.assertTrue(eval_res.is_suspicious)
        self.assertTrue(any("unrecognized caller" in f.lower() and "executive" in f.lower() for f in eval_res.flags))

    def test_c_suppressed_fraud_history_tampering(self):
        """C. Client sends is_previously_flagged=false when DB says flagged."""
        # Server authoritative context found prior fraud
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "is_previously_flagged": True,
            "has_prior_fraud_history": True,
            "fraud_history_count": 3,
            "recent_fraud_types": ["VOICE_CLONE_ATTEMPT"],
        }
        # Attacker attempts to suppress flag
        attacker_args = {
            "is_previously_flagged": False,
            "has_prior_fraud_history": False,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertTrue(ctx.is_previously_flagged)
        self.assertTrue(ctx.has_prior_fraud_history)
        self.assertEqual(ctx.fraud_history_count, 3)

        eval_res = self.analyzer.analyze(ctx)
        self.assertTrue(eval_res.is_suspicious)
        self.assertTrue(any("prior fraud" in f.lower() or "previously flagged" in f.lower() for f in eval_res.flags))

    def test_d_role_mismatch_server_authoritative(self):
        """D. Client sends role_mismatch=false when claimed role conflicts with DB role."""
        # Authoritative context computes role_mismatch=True
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "contact_name": "Alice Smith",
            "contact_role": "Analyst",
            "claimed_role": "Chief Financial Officer",
            "role_mismatch": True,
            "is_caller_recognized": True,
        }
        # Attacker tries to force role_mismatch=False
        attacker_args = {
            "role_mismatch": False,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertTrue(ctx.role_mismatch)

        eval_res = self.analyzer.analyze(ctx)
        self.assertTrue(eval_res.is_suspicious)
        self.assertTrue(any("role mismatch" in f.lower() for f in eval_res.flags))

    def test_e_fake_is_verified_tampering(self):
        """E. Client sends fake is_verified=true for unverified contact."""
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "is_verified": False,
        }
        attacker_args = {
            "is_verified": True,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertFalse(ctx.is_verified)

    def test_f_fake_transaction_auto_hold_amount_tampering(self):
        """F. Client sends fake transaction_auto_hold_amount to evade policy hold."""
        # Org policy specifies 500,000 threshold
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "requested_transaction_amount": 1000000.0,
            "transaction_auto_hold_amount": 500000.0,
        }
        # Attacker tries to increase hold limit to 10,000,000 at root
        attacker_args = {
            "transaction_auto_hold_amount": 10000000.0,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertEqual(ctx.transaction_auto_hold_amount, 500000.0)

        eval_res = self.analyzer.analyze(ctx)
        self.assertTrue(any("auto-hold policy" in f.lower() for f in eval_res.flags))

    def test_g_fake_fraud_history_count_tampering(self):
        """G. Client sends fake fraud_history_count=0 to hide risk history."""
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "has_prior_fraud_history": True,
            "fraud_history_count": 5,
            "recent_fraud_types": ["ACCOUNT_TAKEOVER", "VOICE_CLONE"],
        }
        attacker_args = {
            "fraud_history_count": 0,
            "has_prior_fraud_history": False,
            "context": enriched_context,
        }
        ctx = extract_call_context(attacker_args)
        self.assertEqual(ctx.fraud_history_count, 5)
        self.assertTrue(ctx.has_prior_fraud_history)

    def test_h_root_level_fields_cannot_override_enriched_context(self):
        """H. Root-level request fields attempt to overwrite enriched context in run_pipeline."""
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "is_previously_flagged": True,
            "role_mismatch": True,
            "is_verified": False,
            "transaction_auto_hold_amount": 250000.0,
            "fraud_history_count": 2,
        }
        root_overrides = {
            "is_caller_recognized": False,
            "is_previously_flagged": False,
            "role_mismatch": False,
            "is_verified": True,
            "transaction_auto_hold_amount": 99999999.0,
            "fraud_history_count": 0,
            "context": enriched_context,
        }
        ctx = extract_call_context(root_overrides)
        self.assertTrue(ctx.is_caller_recognized)
        self.assertTrue(ctx.is_previously_flagged)
        self.assertTrue(ctx.role_mismatch)
        self.assertFalse(ctx.is_verified)
        self.assertEqual(ctx.transaction_auto_hold_amount, 250000.0)
        self.assertEqual(ctx.fraud_history_count, 2)

    def test_i_json_string_context_extraction(self):
        """I. Context supplied as JSON string is properly parsed and protected."""
        json_context = (
            '{"organization_id": "00000000-0000-0000-0000-000000000001",'
            ' "is_caller_recognized": true, "is_previously_flagged": true,'
            ' "role_mismatch": true, "fraud_history_count": 4}'
        )
        args = {
            "is_previously_flagged": False,
            "context": json_context,
        }
        ctx = extract_call_context(args)
        self.assertTrue(ctx.is_previously_flagged)
        self.assertTrue(ctx.role_mismatch)
        self.assertEqual(ctx.fraud_history_count, 4)

    def test_j_legitimate_intent_fields_preserved(self):
        """J. Legitimate claimed_role and transaction amount updates still work properly."""
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_caller_recognized": True,
            "is_previously_flagged": False,
            "claimed_role": "Operations Manager",
            "requested_transaction_amount": 75000.0,
            "normal_transaction_amount": 70000.0,
            "is_urgent": True,
            "urgency_reason": "Urgent vendor payout",
            "transcript_text": "Please release the wire payment immediately.",
        }
        args = {
            "context": enriched_context,
        }
        ctx = extract_call_context(args)
        self.assertEqual(ctx.claimed_role, "Operations Manager")
        self.assertEqual(ctx.requested_transaction_amount, 75000.0)
        self.assertEqual(ctx.normal_transaction_amount, 70000.0)
        self.assertTrue(ctx.is_urgent)
        self.assertEqual(ctx.urgency_reason, "Urgent vendor payout")
        self.assertEqual(ctx.transcript_text, "Please release the wire payment immediately.")


if __name__ == "__main__":
    unittest.main()
