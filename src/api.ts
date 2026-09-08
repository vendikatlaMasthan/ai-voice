import {
  AnalysisRecord,
  ClassificationType,
  HealthResponse,
  RiskLevel,
  SampleAudio,
  SubScores,
} from "./types";

/**
 * Base URL for the VoiceShield backend.
 * Configured via VITE_API_URL in .env (local) or .env.production (Cloud).
 */
const RAW_API_URL = import.meta.env.VITE_API_URL || "";
const API_BASE = RAW_API_URL.replace(/\/+$/, "");

/**
 * Default sample audio collection for quick testing.
 */
const BUILTIN_SAMPLES: SampleAudio[] = [
  {
    filename: "human_voice_sample.wav",
    url: "./samples/real_02.wav",
    description: "Authentic human speech recording (bonafide benchmark)",
  },
  {
    filename: "synthetic_clone_sample.wav",
    url: "./samples/fake_01.wav",
    description: "AI-generated synthetic voice clone sample (spoof)",
  },
  {
    filename: "synthetic_vocoder_sample.wav",
    url: "./samples/fake_02.wav",
    description: "Synthetic speech sample exhibiting vocoder artifacts (spoof)",
  },
];

/**
 * Safely parses JSON response and verifies content-type header.
 */
async function parseJsonSafely(res: Response): Promise<any> {
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    await res.text().catch(() => "");
    throw new Error("We couldn't process this audio. The server returned an unexpected response.");
  }
  return res.json();
}

/**
 * Health check endpoint for VoiceShield backend.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const url = API_BASE ? `${API_BASE}/api/health` : "/api/health";
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (res.ok) {
      return await parseJsonSafely(res);
    }
  } catch (err) {
    console.warn("[VoiceShield] Backend health check failed:", err);
  }

  return {
    status: "offline",
    architecture: "VoiceShield Engine (Offline)",
  };
}

/**
 * Retrieves audio samples list.
 */
export async function fetchSamples(): Promise<SampleAudio[]> {
  try {
    const url = API_BASE ? `${API_BASE}/api/samples` : "/api/samples";
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (res.ok) {
      const data = await parseJsonSafely(res);
      if (data && Array.isArray(data.samples) && data.samples.length > 0) {
        return data.samples;
      }
    }
  } catch {}
  return BUILTIN_SAMPLES;
}

/**
 * VoiceShield AI Voice Clone & Anti-Spoofing Analysis.
 *
 * Conforms to SPEC.md canonical contract:
 * - classification: GENUINE_LIVE | REPLAYED_RECORDED | SYNTHETIC_AI_GENERATED | UNCERTAIN
 * - sub_scores: { synthetic_voice_score, replay_channel_score, naturalness_score }
 * - detection_source: reality_defender | aasist | wav2vec2 | local_fallback
 * - risk_level: Low | Medium | High
 * - Hard 15-second frontend timeout cap
 */
export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string
): Promise<AnalysisRecord> {
  const targetUrl = API_BASE ? `${API_BASE}/api/analyze` : "/api/analyze";

  const formData = new FormData();
  formData.append("file", audioFile, fileName);

  // 15-second hard frontend timeout cap per SPEC.md Phase 5
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);

  let res: Response;
  try {
    res = await fetch(targetUrl, {
      method: "POST",
      body: formData,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
      },
    });
  } catch (err: any) {
    clearTimeout(timeoutId);
    console.error("[VoiceShield Technical Error]:", err);
    if (err.name === "AbortError" || err.message?.includes("timed out")) {
      throw new Error("We couldn't complete the analysis in time. Please try a shorter recording or try again.");
    }
    const raw = String(err.message || "");
    if (
      raw &&
      !raw.includes("0x") &&
      !raw.includes("object at") &&
      !raw.includes("<_io") &&
      !raw.includes("TypeError") &&
      !raw.includes("Failed to fetch")
    ) {
      throw new Error(raw);
    }
    const backendHint = API_BASE
      ? `Cannot reach VoiceShield backend at ${API_BASE}. Please ensure the server is active.`
      : "VoiceShield detection service is not reachable. Please check your connection.";
    throw new Error(backendHint);
  } finally {
    clearTimeout(timeoutId);
  }

  if (!res.ok) {
    let errorDetail = "We couldn't process this audio. Please try again.";
    try {
      const errJson = await parseJsonSafely(res);
      const rawMsg = String(errJson.detail || errJson.message || "");
      if (
        rawMsg &&
        !rawMsg.includes("0x") &&
        !rawMsg.includes("object at") &&
        !rawMsg.includes("<_io") &&
        !rawMsg.includes("Traceback") &&
        !rawMsg.includes("SyntaxError")
      ) {
        errorDetail = rawMsg;
      }
    } catch {
      // Use sanitized fallback
    }
    throw new Error(errorDetail);
  }

  const data = await parseJsonSafely(res);

  // Parse canonical contract fields
  const classification: ClassificationType = (
    ["GENUINE_LIVE", "REPLAYED_RECORDED", "SYNTHETIC_AI_GENERATED", "UNCERTAIN"].includes(data.classification)
      ? data.classification
      : "UNCERTAIN"
  ) as ClassificationType;

  const rawSubScores = data.sub_scores || {};
  const sub_scores: SubScores = {
    synthetic_voice_score: typeof rawSubScores.synthetic_voice_score === "number"
      ? rawSubScores.synthetic_voice_score
      : Math.round((data.spoof_probability ?? 0.5) * 100),
    replay_channel_score: typeof rawSubScores.replay_channel_score === "number"
      ? rawSubScores.replay_channel_score
      : 0,
    naturalness_score: typeof rawSubScores.naturalness_score === "number"
      ? rawSubScores.naturalness_score
      : 50,
  };

  const detection_source = String(data.detection_source || data.model || "aasist");
  const risk_level: RiskLevel = (["Low", "Medium", "High"].includes(data.risk_level) ? data.risk_level : "Medium") as RiskLevel;

  // Derive visual badges and colors
  let verdictLabel = "Uncertain / Borderline Acoustics";
  let verdictColor: "green" | "red" | "amber" | "yellow" = "yellow";

  if (classification === "GENUINE_LIVE") {
    verdictLabel = "Genuine Live Human Voice";
    verdictColor = "green";
  } else if (classification === "SYNTHETIC_AI_GENERATED") {
    verdictLabel = "Synthetic AI Generated Voice";
    verdictColor = "red";
  } else if (classification === "REPLAYED_RECORDED") {
    verdictLabel = "Replayed / Recorded Voice";
    verdictColor = "amber";
  }

  const explanation = String(
    data.explanation ||
    `Analysis completed by ${detection_source} (Synthetic Voice Score: ${sub_scores.synthetic_voice_score}/100).`
  );

  const recommendedAction = String(
    data.recommended_action ||
    (classification === "SYNTHETIC_AI_GENERATED"
      ? "High risk of AI synthesis. Request secondary verification before taking action."
      : "Standard voice validation completed.")
  );

  const flags: string[] = Array.isArray(data.flags) ? data.flags : [];

  const audioUrl = URL.createObjectURL(audioFile);
  const scanId = String(data.scan_id || data.call_id || `VS-${Date.now().toString(36).toUpperCase()}`);

  return {
    id: scanId,
    timestamp: Date.now(),
    fileName,
    durationSec: data.audio_metadata?.processed_duration_sec,
    classification,
    verdict: classification,
    verdictLabel,
    verdictColor,
    sub_scores,
    detection_source,
    risk_level,
    explanation,
    gemini_explanation: data.gemini_explanation || undefined,
    recommendedAction,
    flags,
    audio_metadata: data.audio_metadata,
    input_type: data.input_type || (fileName.toLowerCase().match(/\.(mp4|mov|mkv|webm|avi)$/) ? "video" : (fileName.startsWith("mic_") || fileName.startsWith("live_") ? "live" : "audio")),
    detected_language: data.detected_language || "Unable to confidently identify language",
    language_code: data.language || data.transcript_language || undefined,
    language_confidence: data.language_confidence,
    is_long_recording: !!data.is_long_recording,
    user_notice: data.user_notice || undefined,
    simple_verdict: data.simple_verdict || (classification === "GENUINE_LIVE" ? "LIKELY GENUINE" : (classification === "SYNTHETIC_AI_GENERATED" ? "POSSIBLE AI-GENERATED VOICE" : "UNABLE TO CONFIRM")),
    simple_verdict_badge: data.simple_verdict_badge || (classification === "GENUINE_LIVE" ? "🟢 LIKELY GENUINE" : (classification === "SYNTHETIC_AI_GENERATED" ? "🔴 POSSIBLE AI-GENERATED VOICE" : "🟡 UNABLE TO CONFIRM")),
    aiLikelihood: Math.round(sub_scores.synthetic_voice_score),
    spoofProbability: sub_scores.synthetic_voice_score / 100.0,
    bonafideProbability: (100.0 - sub_scores.synthetic_voice_score) / 100.0,
    modelName: detection_source,
    audioUrl,
    rawResponse: data,
  };
}
