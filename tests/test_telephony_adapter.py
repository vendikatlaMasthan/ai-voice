"""
Unit Tests for VoiceShield Python Telephony & VoIP Integration Adapter.
Validates:
1. 8kHz to 16kHz PCM16 linear interpolation resampling
2. G.711 mu-law decoding directly to 16kHz
3. TelephonyCallSession streaming ingestion and chunk callbacks
4. Audio boundary and zero-length buffer safety
"""

import struct
import unittest

from sdk.python.voiceshield.telephony import (
    TelephonyAudioAdapter,
    TelephonyCallMetadata,
    TelephonyCallSession,
)


class TestTelephonyAudioAdapter(unittest.TestCase):
    def test_1_resample_8k_to_16k_doubles_sample_count(self):
        """Verify 8kHz PCM16 audio is correctly upsampled to 2x sample count at 16kHz."""
        # 800 samples at 8kHz = 100ms
        samples_8k = [int(1000 * (i % 10)) for i in range(800)]
        raw_8k = struct.pack(f"<{len(samples_8k)}h", *samples_8k)

        raw_16k = TelephonyAudioAdapter.resample_8k_to_16k(raw_8k)
        num_samples_16k = len(raw_16k) // 2

        self.assertEqual(num_samples_16k, 1600)
        samples_16k = struct.unpack(f"<{num_samples_16k}h", raw_16k)

        # Check that original samples are preserved at even indices
        self.assertEqual(samples_16k[0], samples_8k[0])
        self.assertEqual(samples_16k[2], samples_8k[1])
        # Check that odd indices are linear interpolation
        expected_interp = int(round((samples_8k[0] + samples_8k[1]) / 2.0))
        self.assertEqual(samples_16k[1], expected_interp)

    def test_2_empty_and_single_sample_safety(self):
        """Verify empty and minimal buffers are handled gracefully."""
        self.assertEqual(TelephonyAudioAdapter.resample_8k_to_16k(b""), b"")

        # Single 16-bit sample
        single_sample = struct.pack("<h", 500)
        res = TelephonyAudioAdapter.resample_8k_to_16k(single_sample)
        self.assertEqual(len(res), 4)  # 2 samples = 4 bytes
        unpacked = struct.unpack("<2h", res)
        self.assertEqual(unpacked[0], 500)
        self.assertEqual(unpacked[1], 500)

    def test_3_decode_mulaw_to_16k(self):
        """Verify 8-bit G.711 mu-law audio is decoded to 16kHz PCM16."""
        # 160 bytes of mu-law = 20ms at 8kHz
        mulaw_bytes = bytes([0xFF, 0x7F, 0x00, 0x80] * 40)
        pcm_16k = TelephonyAudioAdapter.decode_mulaw_to_16k(mulaw_bytes)

        # 160 samples -> 320 samples at 16kHz -> 640 bytes
        self.assertEqual(len(pcm_16k), 640)

    def test_4_telephony_call_session_streaming(self):
        """Verify TelephonyCallSession tracks duration and dispatches processed chunks."""
        meta = TelephonyCallMetadata(
            call_id="TEL-CALL-9001",
            caller_ani="+18005550199",
            callee_dnis="+18005550100",
            sip_trunk_id="TRUNK-US-EAST-01",
            claimed_role="Treasurer",
            requested_amount=50000.0,
        )
        session = TelephonyCallSession(meta)

        received_chunks = []
        session.on_processed_chunk(lambda chunk: received_chunks.append(chunk))

        # Feed three 20ms frames (160 samples = 320 bytes each at 8kHz)
        frame = struct.pack("<160h", *([100] * 160))
        session.ingest_8k_chunk(frame)
        session.ingest_8k_chunk(frame)
        session.ingest_8k_chunk(frame)

        self.assertEqual(len(received_chunks), 3)
        self.assertAlmostEqual(session.total_audio_ms, 60.0)
        self.assertEqual(len(received_chunks[0]), 640)  # 320 samples * 2 bytes


if __name__ == "__main__":
    unittest.main()
