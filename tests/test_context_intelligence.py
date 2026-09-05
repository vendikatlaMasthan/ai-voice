"""
Unit and Integration Tests for VoiceShield Phase 1 Contextual Fraud Intelligence.
Verifies multi-tenant database context fusion, role mismatch detection,
executive impersonation flags, transaction policy auto-hold limits,
and risk engine signal scoring.
"""

import unittest

from app.risk.context import (
    CallContext,
    ContextEvaluation,
    RuleBasedContextAnalyzer,
)
from app.risk.scoring import (
    RiskEngineConfig,
    RiskSignals,
    VoiceShieldRiskEngine,
)


class TestContextualFraudIntelligence(unittest.TestCase):
    """Test suite for contextual fraud intelligence and rule-based evaluation."""

    def setUp(self):
        self.analyzer = RuleBasedContextAnalyzer()
        self.risk_engine = VoiceShieldRiskEngine()

    def test_1_default_benign_context(self):
        """1. Default context for recognized contact without suspicious signals is benign."""
        ctx = CallContext(
            caller_id="+15550100",
            is_caller_recognized=True,
            is_previously_flagged=False,
            claimed_role="Support Engineer",
            contact_role="Support Engineer",
            contact_name="Alice Smith",
            is_verified=True,
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertEqual(eval_res.context_flag, 0.0)
        self.assertFalse(eval_res.is_suspicious)
        self.assertEqual(len(eval_res.flags), 0)

    def test_2_role_mismatch_detection(self):
        """2. Role mismatch between claimed role and registered role triggers explainable flag."""
        ctx = CallContext(
            caller_id="+15550101",
            is_caller_recognized=True,
            claimed_role="Chief Executive Officer",
            contact_role="Junior Accountant",
            contact_name="Bob Jones",
            role_mismatch=True,
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertGreaterEqual(eval_res.context_flag, 0.5)
        self.assertTrue(eval_res.is_suspicious)
        self.assertTrue(any("Role Mismatch" in f for f in eval_res.flags))
        self.assertTrue(any("Chief Executive Officer" in f for f in eval_res.flags))

    def test_3_unrecognized_caller_executive_impersonation(self):
        """3. Unrecognized caller claiming executive role triggers executive impersonation flag."""
        ctx = CallContext(
            caller_id="+15559999",
            is_caller_recognized=False,
            claimed_role="Chief Financial Officer (CFO)",
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertGreaterEqual(eval_res.context_flag, 0.5)
        self.assertTrue(eval_res.is_suspicious)
        self.assertTrue(any("executive role" in f.lower() for f in eval_res.flags))

    def test_4_transaction_exceeds_organization_auto_hold_policy(self):
        """4. Requested transaction amount exceeding org auto-hold limit triggers policy violation flag."""
        ctx = CallContext(
            caller_id="+15550102",
            is_caller_recognized=True,
            requested_transaction_amount=750000.0,
            normal_transaction_amount=50000.0,
            transaction_auto_hold_amount=500000.0,
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertGreaterEqual(eval_res.context_flag, 0.5)
        self.assertTrue(any("auto-hold policy" in f.lower() for f in eval_res.flags))

    def test_5_transaction_spike_above_historical_baseline(self):
        """5. Transaction amount 5x higher than normal baseline triggers anomaly spike flag."""
        ctx = CallContext(
            caller_id="+15550103",
            is_caller_recognized=True,
            requested_transaction_amount=50000.0,
            normal_transaction_amount=5000.0,
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertTrue(any("higher than normal baseline" in f for f in eval_res.flags))

    def test_6_prior_fraud_history_and_threat_intelligence(self):
        """6. Caller with prior unresolved fraud history triggers threat intelligence flag."""
        ctx = CallContext(
            caller_id="+15550104",
            is_caller_recognized=True,
            has_prior_fraud_history=True,
            fraud_history_count=2,
            recent_fraud_types=["DEEPFAKE_VOICE_CLONE", "EXECUTIVE_IMPERSONATION"],
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertGreaterEqual(eval_res.context_flag, 0.5)
        self.assertTrue(any("prior fraud incident" in f.lower() for f in eval_res.flags))

    def test_7_suspicious_transcript_keywords_and_urgency(self):
        """7. Social engineering keywords in transcript combined with urgency trigger compound flags."""
        ctx = CallContext(
            caller_id="+15550105",
            is_caller_recognized=True,
            is_urgent=True,
            urgency_reason="Vendor payment due in 10 minutes",
            transcript_text="Please bypass protocol and wire immediately without telling anyone.",
        )
        eval_res = self.analyzer.analyze(ctx)
        self.assertGreaterEqual(eval_res.context_flag, 0.5)
        self.assertTrue(any("urgency" in f.lower() for f in eval_res.flags))
        self.assertTrue(any("keywords" in f.lower() for f in eval_res.flags))

    def test_8_risk_engine_fuses_contextual_intelligence(self):
        """8. VoiceShieldRiskEngine cleanly fuses deepfake, acoustic anomaly, and context signals."""
        ctx = CallContext(
            caller_id="+15550106",
            is_caller_recognized=False,
            claimed_role="CEO",
            requested_transaction_amount=1000000.0,
            transaction_auto_hold_amount=500000.0,
            is_urgent=True,
        )

        assessment = self.risk_engine.evaluate(
            fake_probability=0.88,
            speaker_mismatch=1,
            acoustic_anomaly=0.75,
            context=ctx,
        )

        # Expected score = 0.5*100*0.88 + 0.3*100*1 + 0.1*50*0.75 + 0.1*50*1.0
        # = 44.0 + 30.0 + 3.75 + 5.0 = 82.75 -> 83 (HIGH risk)
        self.assertGreaterEqual(assessment.risk_score, 80)
        self.assertEqual(assessment.risk_level, "HIGH")
        self.assertEqual(assessment.recommended_action, "SECONDARY_VERIFICATION")
        self.assertTrue(any("executive role" in f.lower() for f in assessment.flags))
        self.assertTrue(any("auto-hold" in f.lower() for f in assessment.flags))

    def test_9_context_availability_representation(self):
        """9. Explicit representation of context availability and source."""
        ctx_db = CallContext(
            context_source="SUPABASE_INTELLIGENCE",
            context_available=True,
            organization_id="00000000-0000-0000-0000-000000000001",
        )
        eval_db = self.analyzer.analyze(ctx_db)
        self.assertEqual(eval_db.context_metadata["context_source"], "SUPABASE_INTELLIGENCE")
        self.assertTrue(eval_db.context_metadata["context_available"])


if __name__ == "__main__":
    unittest.main()
