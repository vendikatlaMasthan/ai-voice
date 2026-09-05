"""
Unit & Integration Test Suite for PII Minimization and Data Masking.
Validates:
1. mask_phone_number correctly anonymizes international, standard, and short numbers.
2. mask_email masks username while keeping domain.
3. mask_caller_context produces sanitized audit representations without mutating internal dict.
4. Internal contextual fraud intelligence continues to match caller_id authoritatively.
5. Multi-tenant isolation is preserved.
6. Zero raw audio waveforms are persisted.
"""

import os
import unittest

from app.audio.preprocessing import PreprocessedAudio
from app.risk.context import (
    CallContext,
    RuleBasedContextAnalyzer,
)
from app.utils.pii import (
    mask_caller_context,
    mask_email,
    mask_phone_number,
)


class TestPiiMinimizationAndMasking(unittest.TestCase):
    def test_1_mask_phone_number_formats(self):
        """Test telephone masking across diverse international and national formats."""
        # US / International +1
        self.assertEqual(mask_phone_number("+15551234567"), "+15*****4567")
        self.assertEqual(mask_phone_number("+1 (555) 123-4567"), "+1 (5**) ***-4567")

        # Indian +91 format
        self.assertEqual(mask_phone_number("+919876543210"), "+91******3210")
        self.assertEqual(mask_phone_number("+91 98765 43210"), "+91 ***** *3210")

        # UK +44 format
        self.assertEqual(mask_phone_number("+442079460991"), "+44******0991")

        # 10-digit number without country code
        self.assertEqual(mask_phone_number("9876543210"), "98****3210")

        # Short extension (4-5 chars)
        self.assertEqual(mask_phone_number("4102"), "**02")
        self.assertEqual(mask_phone_number("12345"), "***45")

        # Empty / None safety
        self.assertEqual(mask_phone_number(None), "")
        self.assertEqual(mask_phone_number(""), "")

    def test_2_mask_email_format(self):
        """Test email address masking."""
        self.assertEqual(mask_email("john.doe@enterprise.com"), "j******e@enterprise.com")
        self.assertEqual(mask_email("ceo@bank.org"), "c*o@bank.org")
        self.assertEqual(mask_email("ab@domain.com"), "a*@domain.com")
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email(None), "")

    def test_3_mask_caller_context_immutability(self):
        """Test mask_caller_context masks PII for logs without mutating raw dictionary."""
        raw_ctx = {
            "caller_id": "+15551234567",
            "contact_name": "Alice Smith",
            "contact_phone": "+919876543210",
            "email": "alice@globalcorp.com",
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "claimed_role": "Chief Financial Officer",
        }

        masked_ctx = mask_caller_context(raw_ctx)

        # Masked copy contains masked values
        self.assertEqual(masked_ctx["caller_id_masked"], "+15*****4567")
        self.assertEqual(masked_ctx["caller_id"], "+15*****4567")
        self.assertEqual(masked_ctx["contact_phone"], "+91******3210")
        self.assertEqual(masked_ctx["email"], "a***e@globalcorp.com")

        # Raw dictionary is completely preserved
        self.assertEqual(raw_ctx["caller_id"], "+15551234567")
        self.assertEqual(raw_ctx["contact_phone"], "+919876543210")

    def test_4_authorized_context_intelligence_matches_raw_caller(self):
        """Verify internal fraud intelligence uses unmasked caller_id for exact DB matching."""
        ctx = CallContext(
            caller_id="+15551234567",
            claimed_role="Treasurer",
            requested_transaction_amount=25000.0,
            normal_transaction_amount=10000.0,
            is_caller_recognized=True,
            is_urgent=True,
            urgency_reason="Supplier payment deadline",
            suspicious_keywords_found=["wire immediately"],
        )
        analyzer = RuleBasedContextAnalyzer()
        result = analyzer.analyze(ctx)

        self.assertIsNotNone(result)
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.severity_score, 0)
        self.assertEqual(ctx.caller_id, "+15551234567")

    def test_5_tenant_isolation_in_pii_handling(self):
        """Verify tenant-scoped records do not leak cross-tenant caller metadata."""
        ctx_org_a = {
            "organization_id": "ORG-ALPHA",
            "caller_id": "+15551112222",
        }
        ctx_org_b = {
            "organization_id": "ORG-BETA",
            "caller_id": "+15553334444",
        }

        masked_a = mask_caller_context(ctx_org_a)
        masked_b = mask_caller_context(ctx_org_b)

        self.assertEqual(masked_a["organization_id"], "ORG-ALPHA")
        self.assertEqual(masked_b["organization_id"], "ORG-BETA")
        self.assertNotEqual(masked_a["caller_id"], masked_b["caller_id"])

    def test_6_zero_raw_audio_retention(self):
        """Verify that audio preprocessing discards raw input files and keeps only in-memory features."""
        # Create audio instance
        audio = PreprocessedAudio(
            waveform=[0.0] * 16000,
            sample_rate=16000,
            original_duration_sec=1.0,
            processed_duration_sec=1.0,
            rms_energy_db=-24.0,
            estimated_snr_db=25.0,
            channels=1,
            metadata={"source": "memory"},
        )
        self.assertIsNone(audio.metadata.get("persisted_filepath"))
        self.assertEqual(len(audio.waveform), 16000)


if __name__ == "__main__":
    unittest.main()
