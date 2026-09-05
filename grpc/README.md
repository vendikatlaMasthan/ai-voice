# VoiceShield AI — Enterprise gRPC Voice Security Interface

This directory contains the official **gRPC API specification and server implementation** for integrating VoiceShield AI with core banking systems, contact centers, and telecom VoIP gateways.

> **Evaluation Notice**: This is an integration-ready local gRPC interface. It is not a production deployment or live telecom/banking integration.

---

## 1. Overview & Protocol Architecture

The gRPC adapter directly connects to the existing `PipelineWorker` and `PolicyEngine` models without duplicating the ML inference pipeline.

```
External Clients (Banking / Contact Center / PBX)
        │
        ▼ (gRPC HTTP/2 Protobuf)
   [VoiceShieldService]
        │
        ├── AnalyzeAudio        ──┐
        ├── EnrollSpeaker       ──┼──> Existing Shared VoiceShield ML Pipeline
        ├── VerifySpeaker       ──┤     (Wav2Vec2 + Prosody + ECAPA + Whisper LID/ASR)
        ├── GetRiskPolicy       ──┤
        └── StreamLiveAudio     ──┘
```

---

## 2. Service Definition (`proto/voiceshield.proto`)

```protobuf
service VoiceShieldService {
  rpc AnalyzeAudio(AnalyzeAudioRequest) returns (AnalyzeAudioResponse);
  rpc EnrollSpeaker(EnrollSpeakerRequest) returns (EnrollSpeakerResponse);
  rpc VerifySpeaker(VerifySpeakerRequest) returns (VerifySpeakerResponse);
  rpc GetRiskPolicy(GetRiskPolicyRequest) returns (GetRiskPolicyResponse);
  rpc StreamLiveAudio(stream LiveAudioChunk) returns (stream LiveAudioAnalysisResult);
}
```

---

## 3. How to Start the Local gRPC Server

```bash
# Set optional gRPC port (default 50051) and start server:
python -m grpc_server.server
```

---

## 4. Authentication Metadata

gRPC integration clients authenticate using standard gRPC invocation metadata matching REST `X-API-Key`:

| Metadata Key | Value | Description |
| :--- | :--- | :--- |
| `x-api-key` | `string` | Configured organization API key |

When `REQUIRE_API_KEY=true` is set on the server, unauthenticated RPC requests are rejected with `grpc.StatusCode.UNAUTHENTICATED`.

---

## 5. RPC Methods & Python Client Examples

### A. Initialize Client
```python
from grpc_server.client import VoiceShieldGrpcClient

client = VoiceShieldGrpcClient(
    target="localhost:50051",
    api_key="your-api-key-here",
)
```

### B. Analyze Audio (`AnalyzeAudio`)
```python
with open("samples/wire_request.wav", "rb") as f:
    audio_bytes = f.read()

response = client.analyze_audio(
    audio_bytes=audio_bytes,
    speaker_id="EMP-4102",
    claimed_role="Chief Financial Officer",
    requested_amount=75000.0,
    normal_amount=10000.0,
    is_urgent=True,
    urgency_reason="Supplier acquisition deadline",
)

print(f"Risk Score: {response.risk_score} ({response.risk_level})")
print(f"Recommended Action: {response.recommended_action}")
print(f"Deepfake Probability: {response.deepfake_detection.fake_probability:.4f}")
print(f"Speaker Verified: {response.speaker_verification.is_match}")
```

### C. Multi-Sample Centroid Enrollment (`EnrollSpeaker`)
```python
with open("samples/cfo_voice_sample2.wav", "rb") as f:
    audio_bytes = f.read()

enroll_res = client.enroll_speaker(
    audio_bytes=audio_bytes,
    speaker_id="EMP-4102",
    speaker_name="Jane Doe (CFO)",
)
print(f"Enrolled sample #{enroll_res.sample_count} for {enroll_res.speaker_id}")
```

### D. Biometric Verification (`VerifySpeaker`)
```python
with open("samples/caller_sample.wav", "rb") as f:
    audio_bytes = f.read()

verify_res = client.verify_speaker(
    audio_bytes=audio_bytes,
    speaker_id="EMP-4102",
    threshold=0.70,
)
print(f"Cosine Similarity: {verify_res.similarity_score:.4f}, Match: {verify_res.match}")
```

### E. Bidirectional Real-Time Live Stream (`StreamLiveAudio`)
```python
from grpc_server.generated import voiceshield_pb2

def chunk_generator():
    # Stream 16kHz Little-Endian PCM16 chunks:
    with open("samples/live_stream.pcm", "rb") as f:
        while chunk := f.read(3200): # 100ms frames
            yield voiceshield_pb2.LiveAudioChunk(
                session_id="GRPC-SES-1001",
                pcm16_chunk=chunk,
                speaker_id="EMP-4102",
                context=voiceshield_pb2.LiveAudioContext(
                    claimed_role="Treasurer",
                    requested_amount=50000.0,
                )
            )

for result in client.stream_live_audio(chunk_generator()):
    print(f"[Window #{result.window_index}] Risk: {result.risk_score} | ASR: '{result.transcript}' | Action: {result.recommended_action}")
```

---

## 6. Security Guarantees & Disclaimers

1. **Zero Raw Audio Retention**: Audio buffers are processed in-memory for feature extraction and discarded immediately.
2. **Server-Authoritative Tenant Isolation**: Organization policies and access controls are resolved authoritatively on the server.
3. **No External AI APIs**: All models (Wav2Vec2, Prosody, ECAPA-TDNN, Whisper ASR/LID) execute locally without third-party API dependencies.
