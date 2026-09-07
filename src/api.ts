import { AnalysisRecord, HealthResponse, SampleAudio, VerdictType } from "./types";
import { analyzeAudioInBrowser } from "./audioAnalysisEngine";

/**
 * Base URL for VoiceShield API backend.
 * Configured via VITE_API_URL in .env (local) or .env.production (Render / Cloud).
 * Example: "https://voiceshield-backend.onrender.com"
 */
const RAW_API_URL = import.meta.env.VITE_API_URL || "";
const API_BASE = RAW_API_URL.replace(/\/+$/, "");

/**
 * Helper to determine if a valid external backend URL is configured.
 */
function isBackendConfigured(): boolean {
  return Boolean(
    API_BASE &&
    !API_BASE.includes("your-backend-service") &&
    !API_BASE.includes("placeholder")
  );
}

/**
 * Built-in fallback audio samples for static hosting (e.g. GitHub Pages).
 */
const BUILTIN_SAMPLES: SampleAudio[] = [
  {
    filename: "human_voice_sample.wav",
    url: "./samples/real_02.wav",
    description: "Authentic human speech recording (SIH benchmark ground-truth)",
  },
  {
    filename: "synthetic_clone_sample.wav",
    url: "./samples/fake_01.wav",
    description: "AI-generated voice clone sample (neural vocoder synthesis)",
  },
  {
    filename: "synthetic_vocoder_sample.wav",
    url: "./samples/fake_02.wav",
    description: "Synthetic voice sample exhibiting acoustic prosodic artifacts",
  },
];

/**
 * Safely parses JSON only if the response is OK and has an application/json content-type.
 * Prevents HTML 404 parse crashes.
 */
async function parseJsonSafely(res: Response): Promise<any> {
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const textSample = await res.text().catch(() => "");
    throw new Error(
      `Expected JSON response but server responded with "${contentType || "unknown"}" (HTTP ${res.status}): ${textSample.slice(0, 120)}`
    );
  }
  return res.json();
}

/**
 * Checks backend health endpoint: ${VITE_API_URL}/api/health
 */
export async function fetchHealth(): Promise<HealthResponse> {
  if (isBackendConfigured()) {
    try {
      const res = await fetch(`${API_BASE}/api/health`, {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        return await parseJsonSafely(res);
      }
    } catch (err) {
      console.warn("[VoiceShield] Remote backend health check failed, using client status:", err);
    }
  }

  return {
    status: "ok",
    service: isBackendConfigured()
      ? `VoiceShield Gateway (${API_BASE})`
      : "VoiceShield Client-Side WebAudio DSP Engine",
    version: "2.1.0-browser",
  };
}

/**
 * Retrieves audio samples: ${VITE_API_URL}/api/samples
 * Falls back to built-in static samples if backend is unreachable or not configured.
 */
export async function fetchSamples(): Promise<SampleAudio[]> {
  if (isBackendConfigured()) {
    try {
      const res = await fetch(`${API_BASE}/api/samples`, {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const data = await parseJsonSafely(res);
        if (data && Array.isArray(data.samples) && data.samples.length > 0) {
          // If samples have relative paths, prefix them with API_BASE
          return data.samples.map((s: SampleAudio) => ({
            ...s,
            url: s.url.startsWith("http") ? s.url : `${API_BASE}${s.url.startsWith("/") ? "" : "/"}${s.url}`,
          }));
        }
      }
    } catch (err) {
      console.warn("[VoiceShield] Remote samples fetch failed, falling back to bundled samples:", err);
    }
  }

  return BUILTIN_SAMPLES;
}

/**
 * Analyzes audio file: ${VITE_API_URL}/api/analyze
 *
 * If a deployed backend URL is configured (VITE_API_URL):
 * - Submits audio via POST to ${VITE_API_URL}/api/analyze
 * - Validates response content-type to avoid HTML parse crashes
 * - Maps the backend ML model prediction and multi-signal risk metrics
 *
 * If no backend is configured or if the backend request fails:
 * - Automatically falls back to the in-browser Web Audio DSP engine
 * - Ensures 100% operational uptime on static hosting
 */
export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string
): Promise<AnalysisRecord> {
  if (isBackendConfigured()) {
    try {
      const formData = new FormData();
      formData.append("file", audioFile, fileName);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 20000); // 20-second timeout

      let res: Response;
      try {
        res = await fetch(`${API_BASE}/api/analyze`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
          headers: {
            Accept: "application/json",
          },
        });
      } finally {
        clearTimeout(timeoutId);
      }

      if (!res.ok) {
        let errorMsg = `Server error (HTTP ${res.status})`;
        try {
          const errData = await parseJsonSafely(res);
          errorMsg = errData.message || errData.detail?.message || errData.detail || errorMsg;
        } catch {
          // Fall back to HTTP status message
        }
        throw new Error(errorMsg);
      }

      const data = await parseJsonSafely(res);

      // Extract backend fields
      const fakeProb = data.deepfake_detection?.fake_probability ?? (data.risk_score ? data.risk_score / 100 : 0);
      const anomaly = data.prosody_analysis?.acoustic_anomaly ?? 0;
      const duration = data.audio_metadata?.processed_duration_sec ?? 0;
      const snr = data.audio_metadata?.estimated_snr_db ?? 15;
      const hfRatio = data.prosody_analysis?.features?.hf_energy_ratio ?? 0;

      const aiLikelihood = Math.round(fakeProb * 100);
      const voiceNaturalness = Math.max(5, Math.min(100, Math.round((1 - anomaly) * 100)));
      const audioClarity: "Clear" | "Moderate" | "Low" =
        snr >= 18 ? "Clear" : snr >= 10 ? "Moderate" : "Low";

      const detectedLangRaw = data.detected_language || data.speech_profile?.detected_language || data.language_name || "";
      const langConfRaw = data.language_confidence ?? data.speech_profile?.language_confidence ?? 0;
      let detectedLanguage = "Unclear";
      const languageConfidence = Math.round(langConfRaw * 100);

      if (langConfRaw >= 0.50 && detectedLangRaw && detectedLangRaw !== "Unclear" && detectedLangRaw !== "Unknown") {
        detectedLanguage = detectedLangRaw;
      }

      const backendVerdict = data.classification || data.verdict;
      let verdict: VerdictType = "UNCERTAIN";
      let verdictLabel = "Uncertain";
      let verdictColor: "green" | "red" | "amber" | "yellow" = "yellow";
      let explanation = "The audio characteristics are ambiguous or borderline, preventing a conclusive determination.";
      let recommendedAction = "Inconclusive audio — please obtain a clearer voice sample.";
      let uncertainReason: "mixed_signals" | "low_quality" | "short_audio" | undefined = undefined;

      const targetVerdict = (
        backendVerdict === "GENUINE_LIVE" ||
        backendVerdict === "REPLAYED_RECORDED" ||
        backendVerdict === "SYNTHETIC_AI_GENERATED" ||
        backendVerdict === "UNCERTAIN"
      )
        ? backendVerdict
        : fakeProb >= 0.65
        ? "SYNTHETIC_AI_GENERATED"
        : snr < 10
        ? "UNCERTAIN"
        : (anomaly >= 0.65 && fakeProb < 0.35 && hfRatio < 0.60)
        ? "REPLAYED_RECORDED"
        : (fakeProb < 0.35 && voiceNaturalness > 50 && snr >= 12 && hfRatio < 0.60)
        ? "GENUINE_LIVE"
        : "UNCERTAIN";

      if (targetVerdict === "SYNTHETIC_AI_GENERATED") {
        verdict = "SYNTHETIC_AI_GENERATED";
        verdictLabel = "Synthetic AI-Generated";
        verdictColor = "red";
        explanation = "This audio exhibits digital synthesis artifacts typical of AI voice cloning models.";
        recommendedAction = "This voice appears synthetic — verify before trusting it.";
      } else if (targetVerdict === "REPLAYED_RECORDED") {
        verdict = "REPLAYED_RECORDED";
        verdictLabel = "Replayed-Recorded";
        verdictColor = "amber";
        explanation = "Acoustic signatures suggest audio played back through a loudspeaker or re-recorded with room acoustics.";
        recommendedAction = "This voice appears to be a recording played through a speaker — verify identity.";
      } else if (targetVerdict === "GENUINE_LIVE") {
        verdict = "GENUINE_LIVE";
        verdictLabel = "Genuine Live";
        verdictColor = "green";
        explanation = "Natural vocal variations, pauses, and acoustics characteristic of an authentic live human speaker.";
        recommendedAction = "This voice appears genuine — no action needed.";
      } else {
        verdict = "UNCERTAIN";
        verdictLabel = "Uncertain";
        verdictColor = "yellow";
        uncertainReason = snr < 10 ? "low_quality" : "mixed_signals";
        explanation = "This voice has mixed signals and could not be confidently classified. Treat with caution and verify through another channel.";
        recommendedAction = "Inconclusive audio — please obtain a clearer voice sample.";
      }

      let audioUrl: string | undefined = undefined;
      if (audioFile instanceof Blob) {
        audioUrl = URL.createObjectURL(audioFile);
      }

      return {
        id: data.call_id || `SCAN-${Date.now()}`,
        timestamp: Date.now(),
        fileName,
        durationSec: Number(duration.toFixed(1)),
        verdict,
        verdictLabel,
        verdictColor,
        explanation,
        recommendedAction,
        aiLikelihood,
        voiceNaturalness,
        audioClarity,
        detectedLanguage,
        languageConfidence,
        uncertainReason,
        audioUrl,
        rawResponse: data,
      };
    } catch (err: any) {
      console.warn("[VoiceShield] Remote backend analysis failed, using in-browser DSP analysis:", err);
      // If user aborted intentionally or if server error, fall back to in-browser engine
      return analyzeAudioInBrowser(audioFile, fileName);
    }
  }

  // Pure client-side DSP execution when no backend URL is set
  return analyzeAudioInBrowser(audioFile, fileName);
}
