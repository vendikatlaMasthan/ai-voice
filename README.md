# VoiceShield: Real-time AI Voice-Cloning Detection & Fraud Prevention

**Smart India Hackathon (SIH 2026) — Problem Statement 26104**  
**Phase 1–5: Preprocessing, Pretrained Deepfake Detector, Multi-Signal Risk Engine, FastAPI Backend & Neural Speaker Verification**

---

## 1. Project Overview

VoiceShield is an anti-fraud security engine designed to detect synthetic speech, AI voice clones (e.g., ElevenLabs, Kokoro, Hume AI, Amazon Polly, Speechify, Tortoise-TTS, RVC), and deepfake audio streams to prevent impersonation fraud in real-time communication.

The system combines:
1. **Audio Preprocessing (Phase 1)**: Standardizes audio to 16 kHz mono, validates duration bounds (1.0s–30.0s), trims silence, and computes acoustic metrics (SNR, RMS).
2. **Deepfake Detector (Phase 2)**: Fine-tuned transformer classification (Wav2Vec2) extracting synthetic artifact likelihood ($P_{\text{fake}}$).
3. **Risk & Context Engine (Phase 3)**: Combines detection signals ($P_{\text{fake}}, M, A, C$) into a calibrated 0–100 risk score with automated action triggers (`ALLOW`, `WARN`, `SECONDARY_VERIFICATION`, `BLOCK`).
4. **FastAPI Backend (Phase 4)**: High-performance REST endpoints for audio ingestion, analysis, speaker enrollment, and health monitoring.
5. **Biometric Speaker Verification (Phase 5)**: Pretrained neural speaker embedding model (ECAPA-TDNN via SpeechBrain) with cosine similarity comparison against enrolled speaker profiles.

---

## 2. Phase 5: Pretrained Neural Speaker Verification

### Architecture & Approach
VoiceShield utilizes **ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`):
- **Embedding Dimension**: 192-dimensional L2-normalized vector.
- **Hardware Profile**: ~80MB weight footprint, <250MB RAM during inference, running comfortably on CPU or NVIDIA MX450 GPU.
- **Cosine Metric**: Similarity is computed as:
  $$\text{sim}(\mathbf{e}_1, \mathbf{e}_2) = \frac{\mathbf{e}_1 \cdot \mathbf{e}_2}{\|\mathbf{e}_1\|_2 \|\mathbf{e}_2\|_2} = \sum_{i=1}^{192} e_{1,i} e_{2,i}$$
- **Decision Logic**:
  - If $\text{sim} \ge \tau$ (Default threshold $\tau = 0.70$): Biometric **Match** ($M = 0$).
  - If $\text{sim} < \tau$: Biometric **Mismatch** ($M = 1$), which penalizes the risk score by $w_2 \cdot 100 \cdot 1 = 30$ points.

### Threshold Calibration Notes
- **Default Baseline**: $\tau = 0.70$ achieves balanced Equal Error Rate (EER) on VoxCeleb benchmark evaluation.
- **High-Security Banking & Executive Operations**: Set threshold to $\tau \in [0.75, 0.85]$ to minimize False Acceptance Rate (FAR).
- **Noisy / Cellular Acoustic Environments**: Set threshold to $\tau \in [0.60, 0.68]$ to minimize False Rejection Rate (FRR).

### Privacy & Biometric Data Handling
- **Zero Raw Audio Retention**: The original voice sample is discarded immediately once the 192-D numerical embedding is extracted.
- **Ephemeral Registry**: Profiles are indexed in-memory (`InMemorySpeakerStore`) by `speaker_id` with non-reversible floating-point representations.

---

## 3. API Endpoints & Specification

FastAPI automatically generates interactive OpenAPI documentation:
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc UI**: `http://localhost:8000/redoc`

### Available Endpoints:

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service status, active version (`1.0.0 (Phase 5)`), and supported models |
| `POST` | `/analyze` | Preprocesses audio, runs deepfake detector, evaluates biometric speaker verification (if `speaker_id` given), checks context rules, and computes composite risk score |
| `POST` | `/enroll` | Enrolls genuine speaker: extracts 192-D embedding and registers into store |
| `POST` | `/verify-speaker` | Standalone biometric speaker verification endpoint comparing query audio against enrolled voice profile |

---

### Example Workflow

#### Step 1: Enroll Genuine Speaker
```bash
curl -X POST "http://localhost:8000/enroll" \
  -F "file=@data/samples/ceo_sample.wav" \
  -F "speaker_id=EMP-9001" \
  -F "speaker_name=Jane Doe (CEO)"
```

**Response:**
```json
{
  "status": "ENROLLED",
  "speaker_id": "EMP-9001",
  "speaker_name": "Jane Doe (CEO)",
  "embedding_dimension": 192,
  "message": "Speaker 'EMP-9001' successfully enrolled (3.00s audio processed).",
  "sample_rate_verified": 16000,
  "inference_time_ms": 42.5
}
```

#### Step 2: Analyze Inbound Suspicious Call
```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "file=@data/samples/incoming_call.wav" \
  -F "speaker_id=EMP-9001" \
  -F "caller_id=+1-555-0199" \
  -F "is_caller_recognized=false" \
  -F "claimed_role=CEO" \
  -F "requested_transaction_amount=75000" \
  -F "normal_transaction_amount=5000" \
  -F "is_urgent=true" \
  -F "urgency_reason=Immediate vendor acquisition deadline" \
  -F "transcript_text=Please wire immediately to the overseas vendor"
```

**Response:**
```json
{
  "call_id": "CALL-B812F90A",
  "risk_score": 92,
  "risk_level": "HIGH",
  "deepfake_detection": {
    "prediction": "FAKE",
    "fake_probability": 0.86,
    "real_probability": 0.14,
    "model_type": "HuggingFaceTransformerDetector",
    "model_id": "garystafford/wav2vec2-deepfake-voice-detector",
    "inference_time_ms": 110.2
  },
  "speaker_verification": {
    "status": "EVALUATED",
    "speaker_id": "EMP-9001",
    "similarity_score": 0.21,
    "threshold": 0.70,
    "is_match": false,
    "speaker_mismatch_flag": 1,
    "inference_time_ms": 38.4
  },
  "risk_signals": {
    "fake_probability": 0.86,
    "speaker_mismatch": 1,
    "acoustic_anomaly": 0.0,
    "context_flag": 1.0,
    "speaker_verification_status": "EVALUATED (MISMATCH)",
    "acoustic_model_status": "INPUT_SUPPLIED (Specialized Prosody Model Deferred)"
  },
  "flags": [
    "High synthetic voice probability (86.0%)",
    "Speaker biometric mismatch detected (Claimed: EMP-9001, Sim: 0.21 vs Thresh: 0.70)",
    "Unrecognized caller asserting high-authority executive role: 'CEO'",
    "Requested transaction amount ($75,000.00) is 15.0x higher than normal baseline ($5,000.00)",
    "High urgency and immediate execution pressure detected",
    "Suspicious social engineering keywords detected: 'wire immediately'"
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

Run all unit and integration tests across Preprocessing, Detector, Risk Engine, API, and Speaker Verification:

```bash
python -m unittest discover -v -s tests -p "test_*.py"
```

---

## 5. Roadmap Scope & Next Phases

- **Phase 1 (Complete)**: Audio loading, 16 kHz mono resampling, silence trimming, duration guards.
- **Phase 2 (Complete)**: Wav2Vec2 transformer deepfake detector.
- **Phase 3 (Complete)**: Multi-signal risk fusion engine ($w_1 P_{\text{fake}} + w_2 M + w_3 A + w_4 C$) and rule-based context analysis.
- **Phase 4 (Complete)**: FastAPI backend service and REST endpoints.
- **Phase 5 (Complete)**: Pretrained ECAPA-TDNN neural speaker verification, ephemeral embedding store, and cosine similarity comparison.
- **Phase 6 (Next / Paused per constraint)**: Persistent storage (PostgreSQL/Supabase).
- **Phase 7 (Deferred)**: Real-time WebSocket audio streaming.
- **Phase 8 (Deferred)**: Frontend security dashboard.
