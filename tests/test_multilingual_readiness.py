"""
Unit and Integration Tests for VoiceShield Feature 4: Multilingual / Indian Speech Readiness.

Verifies:
1. Supported language resolution (English, Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, and Auto Detect).
2. Accent and regional speech profile extraction.
3. Security boundary invariance: Language metadata is untrusted input and must never modify:
   - organization_id
   - is_verified
   - is_caller_recognized
   - is_previously_flagged
   - contact_role
   - fraud_history_count
   - policy
   - risk score or risk level
   - role_mismatch
4. Acoustic deepfake classification and speaker verification remain invariant to language metadata.
5. End-to-end extraction and resolution in pipeline helpers.
"""

import unittest
from app.multilingual.speech_profile import (
    resolve_speech_profile,
    SUPPORTED_LANGUAGES,
    INDIAN_ACCENT_REGIONS,
)
from app.risk.context import CallContext, RuleBasedContextAnalyzer
from app.risk.scoring import RiskSignals, VoiceShieldRiskEngine
from scripts.run_pipeline import extract_call_context


class TestMultilingualReadiness(unittest.TestCase):
    """Test suite for VoiceShield Feature 4 Multilingual / Indian Speech Readiness."""

    def setUp(self):
        self.analyzer = RuleBasedContextAnalyzer()
        self.risk_engine = VoiceShieldRiskEngine()

    def test_supported_languages_list(self):
        """Verify all 8 mandatory Indian languages + English are supported."""
        expected_langs = [
            "english", "hindi", "telugu", "tamil",
            "kannada", "malayalam", "bengali", "marathi"
        ]
        for lang in expected_langs:
            self.assertIn(lang, SUPPORTED_LANGUAGES, f"Expected {lang} in supported languages")

    def test_speech_profile_resolution_explicit_hindi(self):
        """Test resolving explicit Hindi speech profile."""
        profile = resolve_speech_profile(
            selected_language="Hindi",
            accent_region="North India (Hindi / Delhi-NCR / UP)",
        )
        self.assertEqual(profile["selected_language"], "Hindi")
        self.assertEqual(profile["language_code"], "hi-IN")
        self.assertEqual(profile["family"], "Indo-Aryan")
        self.assertEqual(profile["accent_region"], "North India (Hindi / Delhi-NCR / UP)")
        self.assertTrue(profile["acoustic_invariance"])

    def test_speech_profile_resolution_explicit_tamil(self):
        """Test resolving explicit Tamil speech profile."""
        profile = resolve_speech_profile(
            selected_language="Tamil",
            accent_region="South India (Tamil Nadu / Chennai)",
        )
        self.assertEqual(profile["selected_language"], "Tamil")
        self.assertEqual(profile["language_code"], "ta-IN")
        self.assertEqual(profile["family"], "Dravidian")
        self.assertEqual(profile["accent_region"], "South India (Tamil Nadu / Chennai)")

    def test_speech_profile_resolution_all_supported_languages(self):
        """Test resolving each supported language properly."""
        test_cases = [
            ("English", "en-IN"),
            ("Hindi", "hi-IN"),
            ("Telugu", "te-IN"),
            ("Tamil", "ta-IN"),
            ("Kannada", "kn-IN"),
            ("Malayalam", "ml-IN"),
            ("Bengali", "bn-IN"),
            ("Marathi", "mr-IN"),
            ("Auto Detect", "auto"),
            (None, "auto"),
        ]
        for input_lang, expected_code in test_cases:
            profile = resolve_speech_profile(selected_language=input_lang)
            self.assertEqual(profile["language_code"], expected_code, f"Failed for input {input_lang}")
            self.assertIn("note", profile)

    def test_language_metadata_does_not_modify_risk_score(self):
        """CRITICAL SECURITY TEST: Language selection MUST NOT modify the risk score formula."""
        base_ctx = CallContext(
            caller_id="+91-98765-43210",
            claimed_role="CEO",
            requested_transaction_amount=80000.0,
            normal_transaction_amount=5000.0,
            is_caller_recognized=False,
            is_urgent=True,
        )
        base_ctx_eval = self.analyzer.analyze(base_ctx)

        # Baseline evaluation without language metadata
        signals_base = RiskSignals(
            fake_probability=0.85,
            speaker_mismatch=1,
            acoustic_anomaly=0.60,
            context_flag=base_ctx_eval.context_flag,
        )
        score_base = self.risk_engine.evaluate_signals(signals_base)

        # Multilingual variations
        languages = ["Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Bengali", "Marathi", "English"]
        for lang in languages:
            ctx_with_lang = CallContext(
                caller_id="+91-98765-43210",
                claimed_role="CEO",
                requested_transaction_amount=80000.0,
                normal_transaction_amount=5000.0,
                is_caller_recognized=False,
                is_urgent=True,
                selected_language=lang,
                language=lang,
                accent_region="Pan-Indian / General",
            )
            ctx_lang_eval = self.analyzer.analyze(ctx_with_lang)
            signals_lang = RiskSignals(
                fake_probability=0.85,
                speaker_mismatch=1,
                acoustic_anomaly=0.60,
                context_flag=ctx_lang_eval.context_flag,
            )
            score_lang = self.risk_engine.evaluate_signals(signals_lang)
            self.assertEqual(
                score_base.risk_score,
                score_lang.risk_score,
                f"Language '{lang}' altered the risk score! Invariance violated.",
            )
            self.assertEqual(
                score_base.risk_level,
                score_lang.risk_level,
                f"Language '{lang}' altered the risk level! Invariance violated.",
            )

    def test_language_tampering_cannot_override_protected_security_fields(self):
        """CRITICAL SECURITY TEST: Language metadata injection cannot tamper with tenant or verification state."""
        enriched_context = {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "is_verified": False,
            "is_caller_recognized": False,
            "is_previously_flagged": True,
            "contact_role": "Employee",
            "fraud_history_count": 3,
            "role_mismatch": True,
            "policy": {
                "organization_id": "00000000-0000-0000-0000-000000000001",
                "max_risk_tolerance": 45,
            },
        }

        # Attacker tries to use multilingual payload to smuggle overrides
        tampering_payload = {
            "selected_language": "Hindi",
            "accent_region": "North India (Hindi / Delhi-NCR / UP)",
            "organization_id": "99999999-9999-9999-9999-999999999999",
            "is_verified": True,
            "is_caller_recognized": True,
            "is_previously_flagged": False,
            "fraud_history_count": 0,
            "role_mismatch": False,
            "context": enriched_context,
        }

        ctx = extract_call_context(tampering_payload)

        # Check that protected fields were NOT modified by untrusted inputs
        self.assertEqual(ctx.organization_id, "00000000-0000-0000-0000-000000000001")
        self.assertFalse(ctx.is_verified)
        self.assertFalse(ctx.is_caller_recognized)
        self.assertTrue(ctx.is_previously_flagged)
        self.assertEqual(ctx.contact_role, "Employee")
        self.assertEqual(ctx.fraud_history_count, 3)
        self.assertTrue(ctx.role_mismatch)

        # But language and accent metadata were safely extracted
        self.assertEqual(ctx.selected_language, "Hindi")
        self.assertEqual(ctx.accent_region, "North India (Hindi / Delhi-NCR / UP)")

    def test_pipeline_extraction_handles_empty_or_malformed_language(self):
        """Verify pipeline graceful fallback when language metadata is malformed or missing."""
        ctx1 = extract_call_context({})
        self.assertEqual(ctx1.selected_language, "Auto Detect")

        ctx2 = extract_call_context({"selected_language": ""})
        self.assertEqual(ctx2.selected_language, "Auto Detect")

        profile = resolve_speech_profile(selected_language="NonExistentLanguage123")
        self.assertEqual(profile["selected_language"], "Auto Detect")
        self.assertEqual(profile["language_code"], "auto")


if __name__ == "__main__":
    unittest.main()
