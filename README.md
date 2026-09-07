# VoiceShield: Real-time AI Voice-Cloning Detection & Fraud Prevention

**Smart India Hackathon (SIH 2026) — Problem Statement 26104**  
**Real-Time Audio Deepfake Detection & Multi-Signal Risk Engine**

---

## 1. Project Overview

VoiceShield is an anti-fraud security engine designed to detect synthetic speech, AI voice clones (e.g., ElevenLabs, Kokoro, Hume AI, Amazon Polly, Speechify, Tortoise-TTS, RVC), replay attacks, and audio deepfakes to prevent impersonation fraud in real-time communication.

The system combines:
1. **Audio Preprocessing**: Standardizes audio to 16 kHz mono, validates duration bounds (1.0s–30.0s), trims silence, and computes acoustic metrics (SNR, RMS).
2. **Tiered Voice Clone Detection**:
   - **Tier 1 (Primary)**: Reality Defender API integration for high-accuracy cloud deepfake detection.
   - **Tier 2 (Fallback)**: Uses the pretrained `garystafford/wav2vec2-deepfake-voice-detector` transformer model for local inference.
   - **Tier 3 (Baseline)**: Deterministic spectral analysis fallback if deep learning runtimes are unavailable.
3. **Prosody & Acoustic Anomaly Analysis**: Computes pitch variations, jitter, spectral centroid shifts, and high-frequency roll-off to flag replay attacks and abnormal vocal signatures.
4. **Risk & Context Engine**: Combines detection signals ($P_{\text{fake}}, A, C$) into an explainable 0–100 risk score with actionable triggers (`ALLOW`, `WARN`, `SECONDARY_VERIFICATION`, `BLOCK`).
5. **Unified Classification Contract**: Authoritative verdict categorization into `GENUINE_LIVE`, `REPLAYED_RECORDED`, `SYNTHETIC_AI_GENERATED`, and `UNCERTAIN`.

---

## 2. Detection Architecture & Multi-Tier Strategy

### Multi-Tier Detection Flow
VoiceShield enforces strict hierarchical inference fallback:
- **Tier 1 — Reality Defender API**: When configured with `REALITY_DEFENDER_API_KEY`, audio is submitted to Reality Defender. A 6-second timeout and handling for rate limits (429) ensure rapid response.
- **Tier 2 — Pretrained Local Wav2Vec2**: If Reality Defender is unconfigured, times out, or fails, the pipeline automatically falls back to the pretrained `garystafford/wav2vec2-deepfake-voice-detector` model.
- **Tier 3 — Baseline Spectral Detector**: If GPU/CPU transformer dependencies fail, deterministic spectral feature analysis is utilized.

### Unified Classification Contract
Every analysis produces one of four standardized verdicts:
- `GENUINE_LIVE`: Natural vocal variations, pauses, and acoustics characteristic of authentic live human speech.
- `REPLAYED_RECORDED`: Acoustic signatures indicating audio played back through a loudspeaker or re-recorded with room acoustics.
- `SYNTHETIC_AI_GENERATED`: Digital synthesis artifacts characteristic of AI voice cloning models.
- `UNCERTAIN`: Borderline or mixed acoustic signals, or low SNR audio, preventing conclusive determination.

### Calibrated Empirical Performance
Accuracy metrics are reported honestly based on empirical evaluation test sets without fabricated or unverified 99% accuracy claims. Inconclusive or borderline samples are transparently labeled as `UNCERTAIN` rather than forcing false certainty.

---

## 3. API Specification

### Available Endpoints:

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service status, active version, and supported models |
| `POST` | `/analyze` | Preprocesses audio, runs tiered deepfake detection, evaluates prosody/context, and returns unified classification and risk assessment |
| `POST` | `/api/analyze` | Frontend gateway endpoint forwarding to persistent inference daemon with timeout protection |

---

### Example Workflow: Analyze Audio

```bash
curl -X POST "http://localhost:3000/api/analyze" \
  -F "file=@test_samples/ai/fake_01.wav" \
  -F "caller_id=+1-555-0199" \
  -F "is_caller_recognized=false" \
  -F "claimed_role=CEO" \
  -F "requested_transaction_amount=75000" \
  -F "normal_transaction_amount=5000" \
  -F "is_urgent=true" \
  -F "urgency_reason=Immediate vendor acquisition deadline"
```

**Response:**
```json
{
  "call_id": "CALL-B812F90A",
  "classification": "SYNTHETIC_AI_GENERATED",
  "verdict": "SYNTHETIC_AI_GENERATED",
  "risk_score": 92,
  "risk_level": "HIGH",
  "deepfake_detection": {
    "prediction": "FAKE",
    "classification": "SYNTHETIC_AI_GENERATED",
    "verdict": "SYNTHETIC_AI_GENERATED",
    "fake_probability": 0.86,
    "real_probability": 0.14,
    "model_type": "Wav2Vec2",
    "model_id": "garystafford/wav2vec2-deepfake-voice-detector",
    "inference_time_ms": 110.2
  },
  "prosody_analysis": {
    "acoustic_anomaly": 0.22,
    "anomaly_reasons": ["Acoustic characteristics consistent with digital speech synthesis"]
  },
  "flags": [
    "High synthetic voice probability (86.0%)",
    "Unrecognized caller asserting high-authority executive role: 'CEO'",
    "Requested transaction amount ($75,000.00) is 15.0x higher than normal baseline ($5,000.00)",
    "High urgency and immediate execution pressure detected"
  ],
  "recommended_action": "SECONDARY_VERIFICATION",
  "audio_metadata": {
    "sample_rate": 16000,
    "original_duration_sec": 3.0,
    "processed_duration_sec": 3.0,
    "estimated_snr_db": 34.2,
    "rms_db": -12.4
  }
}
```

---

## 4. Running Tests

Run all automated unit and integration tests across Preprocessing, Detector, Risk Engine, and API:

```bash
python -m unittest discover -v -s tests -p "test_*.py"
```

To evaluate the test set against the running server:

```bash
python scripts/evaluate_test_set.py
```
