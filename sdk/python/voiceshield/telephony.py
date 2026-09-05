"""
VoiceShield AI — Telephony & VoIP Integration Adapter (Python)
Provides 8kHz narrowband to 16kHz linear PCM resampling and SIP/VoIP trunk metadata normalization.
"""

from dataclasses import dataclass
import math
import struct
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class TelephonyCallMetadata:
    call_id: str
    caller_ani: Optional[str] = None
    callee_dnis: Optional[str] = None
    sip_trunk_id: Optional[str] = None
    claimed_identity: Optional[str] = None
    claimed_role: Optional[str] = None
    requested_amount: Optional[float] = None
    language: Optional[str] = None


class TelephonyAudioAdapter:
    @staticmethod
    def resample_8k_to_16k(input_8k_pcm16: bytes) -> bytes:
        """
        Resamples 8kHz mono 16-bit linear PCM audio to 16kHz mono 16-bit linear PCM
        using linear sample interpolation (2x upsampling).
        """
        if not input_8k_pcm16:
            return b""

        num_samples = len(input_8k_pcm16) // 2
        if num_samples == 0:
            return b""

        samples_8k = struct.unpack(f"<{num_samples}h", input_8k_pcm16)
        samples_16k: List[int] = []

        for i in range(num_samples):
            current_s = samples_8k[i]
            next_s = samples_8k[i + 1] if i + 1 < num_samples else current_s
            interp_s = int(round((current_s + next_s) / 2.0))

            samples_16k.append(current_s)
            samples_16k.append(interp_s)

        return struct.pack(f"<{len(samples_16k)}h", *samples_16k)

    @staticmethod
    def decode_mulaw_sample(u_val: int) -> int:
        """Decodes an 8-bit mu-law sample to 16-bit linear PCM."""
        u_val = ~u_val & 0xFF
        t = ((u_val & 0x0F) << 3) + 0x84
        t <<= (u_val & 0x70) >> 4
        return (0x84 - t) if (u_val & 0x80) != 0 else (t - 0x84)

    @classmethod
    def decode_mulaw_to_16k(cls, mulaw_bytes: bytes) -> bytes:
        """Decodes 8kHz G.711 mu-law byte stream directly to 16kHz linear PCM16."""
        pcm_8k_samples = [cls.decode_mulaw_sample(b) for b in mulaw_bytes]
        pcm_8k_bytes = struct.pack(f"<{len(pcm_8k_samples)}h", *pcm_8k_samples)
        return cls.resample_8k_to_16k(pcm_8k_bytes)


class TelephonyCallSession:
    """
    Stateful telephony session wrapper for streaming 8kHz PBX audio to VoiceShield.
    """

    def __init__(self, metadata: TelephonyCallMetadata):
        self.metadata = metadata
        self.total_audio_ms = 0.0
        self._listeners: List[Callable[[bytes], None]] = []

    def on_processed_chunk(self, listener: Callable[[bytes], None]):
        self._listeners.append(listener)

    def ingest_8k_chunk(self, pcm_8k_bytes: bytes) -> bytes:
        pcm_16k = TelephonyAudioAdapter.resample_8k_to_16k(pcm_8k_bytes)
        num_samples_8k = len(pcm_8k_bytes) // 2
        self.total_audio_ms += (num_samples_8k / 8.0)

        for listener in self._listeners:
            listener(pcm_16k)

        return pcm_16k
