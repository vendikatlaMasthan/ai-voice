"""
Unit tests for VoiceShield Phase 3: Risk Scoring & Context Engine.
Tests all signal combinations, bounding constraints, context rules, and the roadmap reference case.
"""

import unittest

from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import (
    RiskEngineConfig,
    RiskSignals,
    VoiceShieldRiskEngine,
)


class TestRiskEngine(unittest.TestCase):
    """Test suite for multi-signal fusion and risk calculation."""

    def setUp(self):
        self.engine = VoiceShieldRiskEngine()
        self.context_analyzer = RuleBasedContextAnalyzer()

    def test_1_completely_normal_call(self):
        """1. Completely normal call -> LOW risk (0-39 range) with ALLOW action."""
        signals = RiskSignals(
            fake_probability=0.02,
            speaker_mismatch=0,
            acoustic_anomaly=0.0,
            context_flag=0.0,
        )
        result = self.engine.evaluate_signals(signals)

        # Expected: 0.5*100*0.02 = 1.0 -> score = 1
        self.assertEqual(result.risk_score, 1)
        self.assertEqual(result.risk_level, "LOW")
        self.assertEqual(result.recommended_action, "ALLOW")
        self.assertFalse(any("mismatch" in f.lower() for f in result.flags))

    def test_2_high_fake_probability_alone(self):
        """2. High fake probability alone -> Elevated risk score."""
        signals = RiskSignals(
            fake_probability=0.90,
            speaker_mismatch=0,
            acoustic_anomaly=0.0,
            context_flag=0.0,
        )
        result = self.engine.evaluate_signals(signals)

        # Expected: 0.5*100*0.9 = 45.0 -> score = 45 (MEDIUM)
        self.assertEqual(result.risk_score, 45)
        self.assertEqual(result.risk_level, "MEDIUM")
        self.assertIn("High synthetic voice probability", result.flags[0])

    def test_3_speaker_mismatch_alone(self):
        """3. Speaker mismatch alone -> Increased risk."""
        signals = RiskSignals(
            fake_probability=0.05,
            speaker_mismatch=1,
            acoustic_anomaly=0.0,
            context_flag=0.0,
        )
        result = self.engine.evaluate_signals(signals)

        # Expected: 0.5*100*0.05 + 0.3*100*1 = 2.5 + 30 = 32.5
        self.assertEqual(result.risk_score, 32)
        self.assertEqual(result.risk_level, "LOW")
        self.assertTrue(any("Speaker mismatch" in f for f in result.flags))

    def test_4_suspicious_transaction_context(self):
        """4. Suspicious transaction context alone increases risk."""
        signals = RiskSignals(
            fake_probability=0.10,
            speaker_mismatch=0,
            acoustic_anomaly=0.0,
            context_flag=1.0,
        )
        result = self.engine.evaluate_signals(signals)

        # Expected: 0.5*100*0.10 + 0.1*50*1.0 = 5.0 + 5.0 = 10.0
        self.assertEqual(result.risk_score, 10)
        self.assertEqual(result.signals["context_flag"], 1.0)

    def test_5_multiple_suspicious_signals_compound_to_high_risk(self):
        """5. Multiple suspicious signals -> HIGH risk (70-100)."""
        signals = RiskSignals(
            fake_probability=0.95,
            speaker_mismatch=1,
            acoustic_anomaly=0.8,
            context_flag=1.0,
        )
        result = self.engine.evaluate_signals(signals)

        # Expected: 0.5*100*0.95 + 0.3*100*1 + 0.1*50*0.8 + 0.1*50*1 = 47.5 + 30 + 4 + 5 = 86.5
        self.assertEqual(result.risk_score, 86)
        self.assertEqual(result.risk_level, "HIGH")
        self.assertEqual(result.recommended_action, "SECONDARY_VERIFICATION")
        self.assertGreaterEqual(len(result.flags), 3)

    def test_6_risk_score_lower_bound_clamping(self):
        """6. Risk score never goes below 0 with negative or zero inputs."""
        signals = RiskSignals(
            fake_probability=-0.5,
            speaker_mismatch=0,
            acoustic_anomaly=-1.0,
            context_flag=-0.8,
        )
        score = self.engine.calculate_score(signals)
        self.assertEqual(score, 0.0)

        result = self.engine.evaluate_signals(signals)
        self.assertGreaterEqual(result.risk_score, 0)
        self.assertEqual(result.risk_level, "LOW")

    def test_7_risk_score_upper_bound_clamping(self):
        """7. Risk score never exceeds 100 when custom high weights or extreme inputs are provided."""
        # Test with custom high weights that would sum above 100 without clamping
        high_weight_config = RiskEngineConfig(w_fake=1.0, w_mismatch=1.0, w_acoustic=1.0, w_context=1.0)
        high_weight_engine = VoiceShieldRiskEngine(config=high_weight_config)

        signals = RiskSignals(
            fake_probability=1.0,
            speaker_mismatch=1,
            acoustic_anomaly=1.0,
            context_flag=1.0,
        )
        score = high_weight_engine.calculate_score(signals)
        self.assertEqual(score, 100.0)

        result = high_weight_engine.evaluate_signals(signals)
        self.assertEqual(result.risk_score, 100)
        self.assertEqual(result.risk_level, "HIGH")

    def test_8_context_rules_produce_expected_flags(self):
        """8. Context rules accurately catch executive impersonation, transaction spikes, and urgent keywords."""
        # Case A: Unrecognized caller claiming to be CEO requesting urgent wire transfer
        context_ceo = CallContext(
            caller_id="+1-555-0199",
            is_caller_recognized=False,
            claimed_role="CEO",
            requested_transaction_amount=75000.0,
            normal_transaction_amount=5000.0,
            is_urgent=True,
            urgency_reason="Secret acquisition deadline",
            transcript_text="Please wire immediately to the vendor, do not tell anyone until finalized.",
        )
        eval_ceo = self.context_analyzer.analyze(context_ceo)
        self.assertEqual(eval_ceo.context_flag, 1.0)
        self.assertTrue(eval_ceo.is_suspicious)
        
        # Verify key flags are present
        flag_text = " ".join(eval_ceo.flags).lower()
        self.assertIn("ceo", flag_text)
        self.assertIn("higher than normal", flag_text)
        self.assertIn("urgency", flag_text)
        self.assertIn("wire immediately", flag_text)

        # Case B: Benign recognized contact with normal amount
        context_normal = CallContext(
            caller_id="+1-555-0100",
            is_caller_recognized=True,
            claimed_role="Accountant",
            requested_transaction_amount=1200.0,
            normal_transaction_amount=1500.0,
            is_urgent=False,
            transcript_text="Sending the monthly utility invoice.",
        )
        eval_normal = self.context_analyzer.analyze(context_normal)
        self.assertEqual(eval_normal.context_flag, 0.0)
        self.assertFalse(eval_normal.is_suspicious)
        self.assertEqual(len(eval_normal.flags), 0)

    def test_9_roadmap_reference_benchmark(self):
        """
        9. Exact benchmark from SIH Roadmap:
           P_fake = 0.8, M = 1, A = 0, C = 1
           Expected score calculation:
           RiskScore = (0.5 * 100 * 0.8) + (0.3 * 100 * 1) + (0.1 * 50 * 0) + (0.1 * 50 * 1)
                     = 40 + 30 + 0 + 5
                     = 75
           Expected level: HIGH (70-100)
           Expected action: SECONDARY_VERIFICATION
        """
        signals = RiskSignals(
            fake_probability=0.8,
            speaker_mismatch=1,
            acoustic_anomaly=0.0,
            context_flag=1.0,
        )
        assessment = self.engine.evaluate_signals(signals)

        # Verify mathematical accuracy
        self.assertEqual(assessment.risk_score, 75)
        self.assertEqual(assessment.risk_level, "HIGH")
        self.assertEqual(assessment.recommended_action, "SECONDARY_VERIFICATION")
        self.assertEqual(assessment.signals["fake_probability"], 0.8)
        self.assertEqual(assessment.signals["speaker_mismatch"], 1)
        self.assertEqual(assessment.signals["acoustic_anomaly"], 0.0)
        self.assertEqual(assessment.signals["context_flag"], 1.0)
        self.assertEqual(len(assessment.flags), 3)

    def test_convenience_evaluate_method_with_context_object(self):
        """Test full pipeline invocation using evaluate() with both detector score and CallContext."""
        context = CallContext(
            is_caller_recognized=False,
            claimed_role="Chief Financial Officer",
            requested_transaction_amount=250000.0,
            normal_transaction_amount=10000.0,
            is_urgent=True,
            transcript_text="Please wire transfer the security code right away",
        )
        result = self.engine.evaluate(
            fake_probability=0.85,
            speaker_mismatch=1,
            acoustic_anomaly=0.4,
            context=context,
        )

        # Expected score: (0.5*100*0.85) + (0.3*100*1) + (0.1*50*0.4) + (0.1*50*1.0)
        #               = 42.5 + 30 + 2.0 + 5.0 = 79.5 -> 80
        self.assertEqual(result.risk_score, 80)
        self.assertEqual(result.risk_level, "HIGH")
        self.assertEqual(result.recommended_action, "SECONDARY_VERIFICATION")
        self.assertTrue(any("Chief Financial Officer" in f for f in result.flags))

    def test_regression_sih_linear_formula_and_tier_invariants(self):
        """
        Regression Test: Ensure multi-signal risk fusion strictly adheres to the linear
        formula RiskScore = (0.5*100*P_fake) + (0.3*100*M) + (0.1*50*A) + (0.1*50*C)
        and canonical 3-tier classification (LOW <= 39, MEDIUM 40-69, HIGH >= 70).
        """
        cases = [
            # (P_fake, M, A, C, expected_score, expected_tier)
            (0.0, 0, 0.0, 0.0, 0, "LOW"),
            (0.78, 0, 0.0, 0.0, 39, "LOW"),      # 0.5*100*0.78 = 39 -> LOW
            (0.80, 0, 0.0, 0.0, 40, "MEDIUM"),   # 0.5*100*0.80 = 40 -> MEDIUM
            (0.90, 0, 0.0, 0.0, 45, "MEDIUM"),   # 0.5*100*0.90 = 45 -> MEDIUM
            (0.0, 1, 0.0, 0.0, 30, "LOW"),       # 0.3*100*1 = 30 -> LOW
            (0.60, 1, 0.0, 0.0, 60, "MEDIUM"),   # 30 + 30 = 60 -> MEDIUM
            (0.80, 1, 0.0, 0.0, 70, "HIGH"),     # 40 + 30 = 70 -> HIGH
            (0.80, 1, 0.0, 1.0, 75, "HIGH"),     # 40 + 30 + 0 + 5 = 75 -> HIGH
            (0.95, 1, 0.8, 1.0, 86, "HIGH"),     # 47.5 + 30 + 4 + 5 = 86.5 -> 86 -> HIGH
            (1.0, 1, 1.0, 1.0, 90, "HIGH"),      # 50 + 30 + 5 + 5 = 90 -> HIGH
        ]

        for p_fake, m, a, c, exp_score, exp_tier in cases:
            signals = RiskSignals(fake_probability=p_fake, speaker_mismatch=m, acoustic_anomaly=a, context_flag=c)
            res = self.engine.evaluate_signals(signals)
            self.assertEqual(res.risk_score, exp_score, f"Mismatch for inputs ({p_fake}, {m}, {a}, {c})")
            self.assertEqual(res.risk_level, exp_tier, f"Tier mismatch for inputs ({p_fake}, {m}, {a}, {c})")


if __name__ == "__main__":
    unittest.main()

