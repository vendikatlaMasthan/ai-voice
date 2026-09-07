"""
Reality Defender Integration Module for VoiceShield.
Implements primary deepfake detection tier with explicit handling for all terminal states:
- Success (200 OK)
- Failure (HTTP 4xx / 5xx error)
- Timeout (hard deadline ~6 seconds)
- Quota Exhausted (HTTP 429)
- Invalid / unparseable response
- Missing API key (immediate fallback)

When Reality Defender fails for ANY reason, the detection tier safely falls back
to the local Wav2Vec2 transformer without stalling or raising uncaught exceptions.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from app.audio.preprocessing import PreprocessedAudio

logger = logging.getLogger("VoiceShield.RealityDefender")


class RealityDefenderClient:
    """Client for Reality Defender Audio Deepfake Detection API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout_sec: float = 6.0,
    ):
        self.api_key = api_key or os.getenv("REALITY_DEFENDER_API_KEY")
        self.api_url = (
            api_url
            or os.getenv("REALITY_DEFENDER_API_URL")
            or "https://api.realitydefender.com/v2/media/audio"
        )
        self.timeout_sec = float(timeout_sec)

    @property
    def is_configured(self) -> bool:
        """Returns True only if a non-empty API key is present."""
        return bool(self.api_key and str(self.api_key).strip())

    def predict(
        self, audio: PreprocessedAudio, audio_path: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Submits audio to Reality Defender API.

        Returns:
            Tuple[bool, Optional[Dict[str, Any]], str]:
                - success: bool (True if valid API prediction obtained)
                - result: dict or None (contains fake_probability, real_probability, prediction)
                - terminal_state: str ("SUCCESS", "NO_API_KEY", "TIMEOUT", "QUOTA_EXHAUSTED", "API_ERROR", "INVALID_RESPONSE")
        """
        if not self.is_configured:
            return False, None, "NO_API_KEY"

        start_time = time.perf_counter()

        try:
            # Read audio bytes to upload
            audio_bytes: bytes
            filename = "audio.wav"
            if audio_path and os.path.exists(audio_path):
                filename = os.path.basename(audio_path)
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
            else:
                # If path not available, serialize preprocessed waveform
                import io
                import wave
                import numpy as np

                bio = io.BytesIO()
                waveform_arr = (np.array(audio.waveform, dtype=np.float32) * 32767.0).clip(-32768, 32767).astype(np.int16)
                with wave.open(bio, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(audio.sample_rate)
                    wf.writeframes(waveform_arr.tobytes())
                audio_bytes = bio.getvalue()

            boundary = f"----VoiceShieldBoundary{int(time.time() * 1000)}"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

            req = urllib.request.Request(self.api_url, data=body, method="POST")
            req.add_header("X-API-KEY", self.api_key)
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            req.add_header("User-Agent", "VoiceShield-AI/1.0")

            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                status_code = resp.getcode()
                raw_body = resp.read().decode("utf-8")

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if status_code != 200:
                logger.warning(f"[RealityDefender] Non-200 response: {status_code}")
                return False, None, f"API_ERROR_{status_code}"

            parsed = json.loads(raw_body)

            # Handle standard Reality Defender response structures:
            # e.g., {"status": "success", "score": 0.85, ...} or {"fake_probability": 0.85}
            fake_prob: float
            if "fake_probability" in parsed:
                fake_prob = float(parsed["fake_probability"])
            elif "score" in parsed:
                fake_prob = float(parsed["score"])
            elif "probability" in parsed:
                fake_prob = float(parsed["probability"])
            elif "results" in parsed and isinstance(parsed["results"], dict):
                fake_prob = float(parsed["results"].get("score", 0.5))
            else:
                logger.warning(f"[RealityDefender] Invalid response structure: {raw_body[:200]}")
                return False, None, "INVALID_RESPONSE"

            fake_prob = max(0.0, min(1.0, fake_prob))
            real_prob = round(1.0 - fake_prob, 4)
            prediction = "FAKE" if fake_prob >= 0.5 else "REAL"

            return True, {
                "prediction": prediction,
                "fake_probability": round(fake_prob, 4),
                "real_probability": real_prob,
                "model_type": "RealityDefenderAPI",
                "model_id": "reality-defender-v2",
                "inference_time_ms": round(latency_ms, 2),
                "disclaimer": "Analysis provided by Reality Defender Tier 1 Detection.",
                "raw_response": parsed,
            }, "SUCCESS"

        except urllib.error.HTTPError as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            if err.code == 429:
                logger.warning(f"[RealityDefender] Quota exhausted (HTTP 429) after {latency_ms:.1f}ms. Falling back to local model.")
                return False, None, "QUOTA_EXHAUSTED"
            logger.warning(f"[RealityDefender] HTTP {err.code} error after {latency_ms:.1f}ms. Falling back to local model.")
            return False, None, f"HTTP_ERROR_{err.code}"

        except (urllib.error.URLError, TimeoutError, OSError) as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            is_timeout = "timed out" in str(err).lower() or isinstance(err, TimeoutError)
            state = "TIMEOUT" if is_timeout else "NETWORK_FAILURE"
            logger.warning(f"[RealityDefender] {state} after {latency_ms:.1f}ms: {err}. Falling back to local model.")
            return False, None, state

        except (json.JSONDecodeError, ValueError) as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning(f"[RealityDefender] Invalid response after {latency_ms:.1f}ms: {err}. Falling back to local model.")
            return False, None, "INVALID_RESPONSE"

        except Exception as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning(f"[RealityDefender] Unexpected failure after {latency_ms:.1f}ms: {err}. Falling back to local model.")
            return False, None, "UNEXPECTED_FAILURE"
