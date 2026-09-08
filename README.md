# VoiceShield AI: Multi-Signal Voice Cloning Detection & Fraud Defense

**Smart India Hackathon (SIH 2026) — Problem Statement 26104**  
**Real-Time Audio Deepfake Detection & Multi-Signal Risk Engine**

---

## 1. Project Overview

VoiceShield AI is an audio anti-spoofing and anti-fraud security engine designed to detect synthetic speech, AI voice clones (e.g., ElevenLabs, Kokoro, Hume AI, Amazon Polly, Speechify, Tortoise-TTS, RVC), replay attacks, and audio deepfakes in real-time communication.

### Key Architectural Pillars (conforming to `SPEC.md`):
1. **Universal Audio Ingestion Pipeline**: Every code path receiving audio converts incoming bytes (WebM, Opus, MP3, WAV, M4A, FLAC, AAC) into standard 16kHz mono float32 PCM via a single shared FFmpeg step before any downstream processing.
2. **Tiered Detection Pipeline (Priority Order)**:
   - **Tier 1 (Primary)**: Reality Defender RealAPI (8-second timeout cap, when API key is configured).
   - **Tier 2 (Secondary)**: AASIST (Spectro-Temporal Graph Attention Network trained on the ASVspoof2019 benchmark).
   - **Tier 3 (Fallback)**: Pretrained Wav2Vec2 transformer (`garystafford/wav2vec2-deepfake-voice-detector`).
   - **Tier 4 (Baseline)**: Deterministic spectral feature analysis fallback.
3. **Local Heuristic Prosody & Replay Analysis**: Computes pitch variation, jitter, spectral centroid dynamics, and high-frequency roll-off to evaluate `replay_channel_score` and `naturalness_score`. Always runs in parallel with model inference.
4. **Unified Classification Contract**: Authoritative classification into:
   - `GENUINE_LIVE`: Authentic human speech with natural prosody and resonance.
   - `REPLAYED_RECORDED`: Loudspeaker playback or room re-recording acoustic signatures.
   - `SYNTHETIC_AI_GENERATED`: Phase discontinuities and digital synthesis artifacts.
   - `UNCERTAIN`: Inconclusive acoustic signals or conflicting detection tier scores.
5. **AASIST Calibration Caveat**: AASIST was trained on ASVspoof2019 (telephone-grade audio) and can miscalibrate on clean microphone recordings. If AASIST indicates synthetic speech but naturalness is high and replay score is low on clean SNR, VoiceShield routes to `UNCERTAIN` rather than forcing a false-positive synthetic verdict.
6. **Hard 15-Second Timeout**: End-to-end hard ceiling on analysis guarantees bounded latency across all tiers.
7. **Complete Error Sanitization**: Raw exceptions, memory addresses (e.g., `<_io.BytesIO object at ...>`), and stack traces are logged on the server only and never exposed to the user.

---

## 2. Classification Contract

Every analysis produces a standardized response conforming to the canonical contract:

```json
{
  "classification": "GENUINE_LIVE",
  "verdict": "GENUINE_LIVE",
  "sub_scores": {
    "synthetic_voice_score": 1.2,
    "replay_channel_score": 15.4,
    "naturalness_score": 84.6
  },
  "detection_source": "aasist",
  "risk_level": "Low",
  "explanation": "Natural speech dynamics, vocal variation, and human resonance verified (Naturalness Score: 84.6/100).",
  "recommended_action": "ALLOW",
  "audio_metadata": {
    "sample_rate": 16000,
    "original_duration_sec": 4.5,
    "processed_duration_sec": 4.5,
    "estimated_snr_db": 24.1,
    "rms_db": -22.3
  },
  "flags": [
    "Natural human vocal tract acoustics verified (Naturalness: 84.6/100)"
  ],
  "scan_id": "VS-1725791200-A9B1C2"
}
```

---

## 3. API Specification

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/health` / `/api/health` | Health status, active architecture, and detection tiers |
| `POST` | `/analyze` / `/api/analyze` | Unified endpoint: converts audio via FFmpeg, runs tiered inference, and returns canonical 4-class contract |

### Example cURL:
```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -F "file=@test_samples/ai/fake_01.wav"
```

---

## 4. Local Development & Testing

```bash
# 1. Install backend dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. Launch FastAPI Backend (port 8000)
uvicorn backend.main_api:app --host 0.0.0.0 --port 8000

# 3. Launch Frontend (port 3000)
npm install
npm run dev
```

---

## 5. Model Weights & Attribution

- **AASIST**: Pretrained on ASVspoof2019 logical access dataset. Weights: `backend/aasist/models/weights/AASIST.pth`.
- **Wav2Vec2**: Pretrained open-source weights (`garystafford/wav2vec2-deepfake-voice-detector`).
- **Reality Defender**: Cloud API integration tier.
