import { AnalysisRecord, HealthResponse, SampleAudio, VerdictType } from "./types";

/**
 * Base URL for the AASIST FastAPI backend.
 * Configured via VITE_API_URL in .env (local) or .env.production (Hugging Face Spaces / Cloud).
 * Example: "http://localhost:8000" or "https://username-voiceshield-api.hf.space"
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
 * Health check endpoint for AASIST backend.
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
    model: "AASIST",
    weights_loaded: false,
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
 * Real AASIST Deepfake Voice Analysis.
 *
 * Transmits audio file to the AASIST FastAPI backend:
 * POST ${VITE_API_URL}/api/analyze
 *
 * Returns real inference output:
 * - spoof_probability (0.0 to 1.0)
 * - label: "bonafide" | "spoof"
 * - model: "AASIST"
 */
export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string
): Promise<AnalysisRecord> {
  const targetUrl = API_BASE ? `${API_BASE}/api/analyze` : "/api/analyze";

  const formData = new FormData();
  formData.append("file", audioFile, fileName);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 25000); // 25s timeout

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
      throw new Error("Analysis timed out. The backend model is taking longer than expected.");
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
      ? `Cannot reach backend at ${API_BASE}. Please verify your backend server is running.`
      : "Backend service is not reachable. Please check your connection.";
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
      // Use user-friendly fallback
    }
    throw new Error(errorDetail);
  }

  const data = await parseJsonSafely(res);

  // Parse real AASIST response
  const spoofProb = typeof data.spoof_probability === "number" ? data.spoof_probability : 0.5;
  const bonafideProb = typeof data.bonafide_probability === "number" ? data.bonafide_probability : (1.0 - spoofProb);
  const label: "bonafide" | "spoof" = data.label === "spoof" ? "spoof" : "bonafide";
  const modelName = data.model || "AASIST";

  const aiLikelihood = Math.round(spoofProb * 100);

  const verdict: VerdictType = label === "spoof" ? "SYNTHETIC_AI" : "GENUINE_LIVE";
  const verdictLabel = label === "spoof" ? "Spoof (AI Synthetic Voice)" : "Bonafide (Genuine Human Voice)";
  const verdictColor = label === "spoof" ? "red" : "green";

  const explanation = label === "spoof"
    ? `AASIST spectro-temporal graph attention network detected spoofing artifacts characteristic of synthetic speech synthesis or voice cloning (Spoof Probability: ${(spoofProb * 100).toFixed(1)}%).`
    : `AASIST spectro-temporal graph attention network validated natural acoustic spectral properties consistent with a genuine live human speaker (Spoof Probability: ${(spoofProb * 100).toFixed(1)}%).`;

  const recommendedAction = label === "spoof"
    ? "High risk of voice cloning or deepfake synthesis. Request secondary verification before taking action."
    : "Audio demonstrates bonafide vocal tract characteristics. Standard biometric verification passed.";

  const audioUrl = URL.createObjectURL(audioFile);
  const scanId = `AASIST-${Date.now().toString(36).toUpperCase()}`;

  return {
    id: scanId,
    timestamp: Date.now(),
    fileName,
    verdict,
    verdictLabel,
    verdictColor,
    explanation,
    recommendedAction,
    aiLikelihood,
    spoofProbability: Math.round(spoofProb * 10000) / 10000,
    bonafideProbability: Math.round(bonafideProb * 10000) / 10000,
    modelName,
    audioUrl,
    rawResponse: data,
  };
}
