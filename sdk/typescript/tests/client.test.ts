/**
 * VoiceShield AI — TypeScript SDK Self-Contained Test Suite
 * Validates VoiceShieldClient and VoiceShieldLiveStream with mock transport.
 */

import * as assert from "assert";
import { VoiceShieldClient } from "../src/client";
import { VoiceShieldLiveStream } from "../src/liveStream";

async function runTests() {
  console.log("[TypeScript SDK Test] Starting validation suite...");

  // 1. Initialization
  const client = new VoiceShieldClient({
    baseUrl: "http://127.0.0.1:3000/",
    apiKey: "test-key-12345",
    timeoutMs: 10000,
  });
  assert.ok(client, "VoiceShieldClient failed to initialize");
  console.log("  ✓ test_1_initialization passed");

  // 2. analyzeAudio
  let fetchCalled = false;
  const mockAnalyzeFetch = async (url: string, init: any) => {
    fetchCalled = true;
    assert.strictEqual(url, "http://127.0.0.1:3000/api/analyze");
    assert.strictEqual(init.method, "POST");
    assert.strictEqual(init.headers["X-API-Key"], "test-key-12345");

    return {
      ok: true,
      status: 200,
      json: async () => ({
        call_id: "CALL-TS-01",
        risk_score: 78,
        risk_level: "HIGH",
        recommended_action: "SECONDARY_VERIFICATION",
        flags: ["Synthetic acoustic anomalies"],
        deepfake_detection: {
          prediction: "FAKE",
          fake_probability: 0.88,
          real_probability: 0.12,
          model_type: "Wav2Vec2",
          inference_time_ms: 15.0,
        },
        speaker_verification: {
          status: "EVALUATED",
          speaker_id: "EMP-4102",
          similarity_score: 0.55,
          threshold: 0.70,
          is_match: false,
          speaker_mismatch_flag: 1,
          sample_count: 2,
        },
        risk_signals: {
          fake_probability: 0.88,
          speaker_mismatch: 1,
          acoustic_anomaly: 0.7,
          context_flag: 1,
          speaker_verification_status: "EVALUATED",
          acoustic_model_status: "ACTIVE",
        },
        audio_metadata: {
          sample_rate: 16000,
          original_duration_sec: 2.5,
          processed_duration_sec: 2.5,
          estimated_snr_db: 30.0,
          rms_db: -18.0,
        },
      }),
    };
  };

  const clientWithMock = new VoiceShieldClient({
    baseUrl: "http://127.0.0.1:3000",
    apiKey: "test-key-12345",
    fetch: mockAnalyzeFetch as any,
  });

  const analyzeRes = await clientWithMock.analyzeAudio({
    audio: new Uint8Array([1, 2, 3]),
    speakerId: "EMP-4102",
    claimedRole: "Treasurer",
    requestedAmount: 45000,
  });

  assert.ok(fetchCalled, "Fetch was not called");
  assert.strictEqual(analyzeRes.call_id, "CALL-TS-01");
  assert.strictEqual(analyzeRes.risk_score, 78);
  assert.strictEqual(analyzeRes.recommended_action, "SECONDARY_VERIFICATION");
  assert.strictEqual(analyzeRes.deepfake_detection.prediction, "FAKE");
  assert.strictEqual(analyzeRes.speaker_verification.sample_count, 2);
  console.log("  ✓ test_2_analyze_audio passed");

  // 3. enrollSpeaker
  const mockEnrollFetch = async (_url: string, _init: any) => ({
    ok: true,
    status: 200,
    json: async () => ({
      status: "ENROLLED",
      speaker_id: "SPK-01",
      speaker_name: "Alice",
      sample_count: 3,
      embedding_dimension: 192,
      created_at: 1725000000,
      updated_at: 1725000200,
      message: "Speaker 'SPK-01' sample #3 successfully enrolled.",
      sample_rate_verified: 16000,
      inference_time_ms: 22.0,
    }),
  });

  const clientEnroll = new VoiceShieldClient({
    baseUrl: "http://127.0.0.1:3000",
    fetch: mockEnrollFetch as any,
  });

  const enrollRes = await clientEnroll.enrollSpeaker({
    audio: new Uint8Array([0, 1]),
    speakerId: "SPK-01",
    speakerName: "Alice",
  });
  assert.strictEqual(enrollRes.sample_count, 3);
  assert.strictEqual(enrollRes.embedding_dimension, 192);
  console.log("  ✓ test_3_enroll_speaker passed");

  // 4. LiveStream
  class MockWebSocket {
    public url: string;
    public readyState = 1;
    public binaryType = "arraybuffer";
    public onopen: any = null;
    public onmessage: any = null;
    public onerror: any = null;
    public onclose: any = null;
    public sentMessages: any[] = [];

    constructor(url: string) {
      this.url = url;
      setTimeout(() => {
        if (this.onopen) this.onopen();
        if (this.onmessage) {
          this.onmessage({
            data: JSON.stringify({
              type: "session_ready",
              session_id: "SES-TEST",
              window_duration_sec: 1.5,
              window_size_bytes: 48000,
              sample_rate: 16000,
            }),
          });
          this.onmessage({
            data: JSON.stringify({
              type: "analysis_result",
              session_id: "SES-TEST",
              window_index: 1,
              data: {
                call_id: "CALL-LIVE-01",
                risk_score: 15,
                risk_level: "LOW",
                recommended_action: "ALLOW",
                deepfake_detection: { fake_probability: 0.05, prediction: "REAL" },
              },
            }),
          });
        }
      }, 10);
    }

    public send(data: any) {
      this.sentMessages.push(data);
    }

    public close() {
      if (this.onclose) this.onclose();
    }
  }

  const liveClient = new VoiceShieldClient({
    baseUrl: "http://localhost:3000",
    WebSocketClass: MockWebSocket,
  });

  const stream = liveClient.startLiveStream({
    sessionId: "SES-TEST",
    speakerId: "EMP-4102",
  });

  await new Promise<void>((resolve) => {
    let readyReceived = false;
    stream.onReady((info) => {
      readyReceived = true;
      assert.strictEqual(info.session_id, "SES-TEST");
    });

    stream.onResult((result, windowIndex) => {
      assert.ok(readyReceived, "Ready should have been received before result");
      assert.strictEqual(windowIndex, 1);
      assert.strictEqual(result.risk_score, 15);
      assert.strictEqual(result.recommended_action, "ALLOW");
      stream.close();
      console.log("  ✓ test_4_live_stream passed");
      resolve();
    });
  });

  console.log("All TypeScript SDK tests passed successfully!");
}

runTests().catch((err) => {
  console.error("TypeScript SDK Test Error:", err);
  process.exit(1);
});
