# VoiceShield AI — Client SDKs (Integration-Ready)

This directory provides lightweight, reusable, and type-safe client SDKs for integrating **VoiceShield AI** with external banking cores, contact center platforms, and telecom VoIP gateways.

> **Note for Evaluators & Judges**: These are integration-ready local client SDK libraries designed to interface with the VoiceShield AI backend REST and WebSocket streaming APIs.

---

## SDK Features

- **Multi-Signal Deepfake Defense**: Analyze inbound audio for synthetic Wav2Vec2 neural artifacts, acoustic prosody pitch jitter, and ECAPA-TDNN speaker mismatch.
- **Cross-Session Biometric Centroids**: Multi-sample incremental speaker enrollment and verification without raw audio persistence.
- **Multilingual Whisper Live Speech Intelligence**: Native speech recognition, language identification (8 Indian languages + English), and contextual fraud keyword extraction.
- **Real-Time Live Streaming**: Zero-disk binary PCM streaming over WebSocket (`/ws/live-stream`).
- **Zero Third-Party AI API Keys**: Entirely local and offline-capable inference.

---

## 1. TypeScript SDK (`sdk/typescript`)

### Installation (Local Workspace)
```typescript
import { VoiceShieldClient } from "./sdk/typescript/src";
// or import { VoiceShieldClient } from "@voiceshield/sdk";
```

### Initialization
```typescript
const client = new VoiceShieldClient({
  baseUrl: process.env.VOICESHIELD_URL || "http://localhost:3000",
  apiKey: process.env.VOICESHIELD_API_KEY, // Optional runtime X-API-Key
  timeoutMs: 15000,
});
```

### A. Analyze Audio File (Banking Call Example)
```typescript
import * as fs from "fs";

async function evaluateWireTransferCall() {
  const audioBuffer = fs.readFileSync("./samples/wire_request.wav");

  const result = await client.analyzeAudio({
    audio: audioBuffer,
    filename: "wire_request.wav",
    speakerId: "EMP-4102",
    claimedRole: "Chief Financial Officer",
    requestedAmount: 75000,
    normalAmount: 10000,
    isUrgent: true,
    urgencyReason: "Vendor acquisition deadline",
    language: "en",
  });

  console.log(`Risk Score: ${result.risk_score}/100 (${result.risk_level})`);
  console.log(`Deepfake Prob: ${(result.deepfake_detection.fake_probability * 100).toFixed(1)}%`);
  console.log(`Speaker Match: ${result.speaker_verification.is_match}`);
  console.log(`Recommended Action: ${result.recommended_action}`);

  if (result.recommended_action === "BLOCK" || result.risk_score >= 80) {
    // Terminate call and freeze transaction
    console.warn("CRITICAL THREAT: Transaction auto-held by VoiceShield policy!");
  }
}
```

### B. Multi-Sample Speaker Enrollment
```typescript
async function enrollExecutiveVoice() {
  const sampleAudio = fs.readFileSync("./samples/cfo_voice_session2.wav");

  const enrollment = await client.enrollSpeaker({
    audio: sampleAudio,
    speakerId: "EMP-4102",
    speakerName: "Jane Doe (CFO)",
  });

  console.log(`Enrolled sample #${enrollment.sample_count} for ${enrollment.speaker_id}`);
  console.log(`Updated 192-D Centroid: ${enrollment.message}`);
}
```

### C. Verify Speaker Biometric Consistency
```typescript
async function verifyCallerVoice() {
  const queryAudio = fs.readFileSync("./samples/query_audio.wav");

  const verification = await client.verifySpeaker({
    audio: queryAudio,
    speakerId: "EMP-4102",
    threshold: 0.70,
  });

  console.log(`Biometric Similarity: ${verification.similarity_score}`);
  console.log(`Verified Match: ${verification.match}`);
}
```

### D. Real-Time Live Microphone / VoIP Stream
```typescript
function startLiveCallMonitoring(callId: string) {
  const stream = client.startLiveStream({
    sessionId: `SES-${callId}`,
    speakerId: "EMP-4102",
    windowDurationSec: 1.5,
    context: {
      claimed_role: "Treasurer",
      requested_amount: 50000,
    },
  });

  stream.onReady((readyInfo) => {
    console.log(`Live Stream Ready: Window ${readyInfo.window_duration_sec}s`);
  });

  stream.onResult((result, windowIndex) => {
    console.log(`[Window #${windowIndex}] Live Risk: ${result.risk_score} | ASR: "${result.transcript}"`);

    if (result.recommended_action === "SECONDARY_VERIFICATION") {
      console.warn("Triggering Step-Up OTP Challenge on Customer Portal...");
    }
  });

  stream.onError((err) => {
    console.error("Stream error:", err);
  });

  // Stream raw 16kHz Little-Endian PCM16 chunks as received from AudioWorklet or SIP bridge:
  // stream.sendPcm(pcmInt16Buffer);

  // When call ends:
  // stream.close();
}
```

---

## 2. Python SDK (`sdk/python/voiceshield`)

### Installation (Local Workspace)
```python
from sdk.python.voiceshield import VoiceShieldClient
```

### Initialization
```python
import os

client = VoiceShieldClient(
    base_url=os.getenv("VOICESHIELD_URL", "http://localhost:3000"),
    api_key=os.getenv("VOICESHIELD_API_KEY"), # Optional runtime X-API-Key
    timeout=30.0,
)
```

### A. Analyze Audio
```python
result = client.analyze_audio(
    audio="samples/inbound_call.wav",
    speaker_id="EMP-9001",
    claimed_role="Senior VP Operations",
    requested_amount=85000.0,
    normal_amount=5000.0,
    is_urgent=True,
    urgency_reason="Emergency supplier wire",
    language="hi",
)

print(f"Risk Score: {result.risk_score} ({result.risk_level})")
print(f"Deepfake Probability: {result.deepfake_detection.fake_probability:.4f}")
print(f"Speaker Biometric Match: {result.speaker_verification.is_match}")
print(f"Action: {result.recommended_action}")
```

### B. Speaker Enrollment & Verification
```python
# Multi-sample incremental centroid enrollment
enroll_res = client.enroll_speaker(
    audio="samples/genuine_sample_01.wav",
    speaker_id="EMP-9001",
    speaker_name="Dr. Aris Thorne",
)
print(f"Enrolled sample count: {enroll_res.sample_count}")

# Biometric verification
verify_res = client.verify_speaker(
    audio="samples/query_sample.wav",
    speaker_id="EMP-9001",
    threshold=0.70,
)
print(f"Similarity: {verify_res.similarity_score:.4f}, Match: {verify_res.match}")
```

### C. Retrieve Organization Policy & Speaker Store
```python
speakers = client.get_speakers()
for spk in speakers:
    print(f"Speaker {spk.speaker_id} ({spk.speaker_name}): {spk.sample_count} genuine samples enrolled")

policy = client.get_policy()
print(f"Active Auto-Hold Threshold: ${policy.transaction_auto_hold_amount:,.2f}")
```

---

## 3. Security & Privacy Guarantees

1. **No Credentials Committed**: API keys and tokens are supplied solely at runtime via environment variables or configuration objects.
2. **Zero Raw Audio Retention**: The VoiceShield backend extracts numerical embeddings and prosody features in-memory and discards audio buffers immediately.
3. **Transport Security**: Configurable `baseUrl` supports both `http://` / `ws://` (local development) and `https://` / `wss://` (production TLS).
