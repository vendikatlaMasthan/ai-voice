import { AnalysisRecord, HealthResponse, SampleAudio, VerdictType } from "./types";

const API_BASE = "";

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchSamples(): Promise<SampleAudio[]> {
  try {
    const res = await fetch(`${API_BASE}/api/samples`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.samples || [];
  } catch {
    return [];
  }
}

export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string
): Promise<AnalysisRecord> {
  const formData = new FormData();
  formData.append("file", audioFile, fileName);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 16000); // 16-second client timeout matching backend

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err.name === "AbortError") {
      throw new Error("This is taking longer than expected. Please try again.");
    }
    throw new Error(err.message || "Failed to connect to VoiceShield service.");
  } finally {
    clearTimeout(timeoutId);
  }

  const data = await res.json();
  if (!res.ok) {
    const msg = data.message || data.detail?.message || data.detail || "Analysis request failed";
    throw new Error(msg);
  }

  const fakeProb = data.deepfake_detection?.fake_probability ?? 0;
  const anomaly = data.prosody_analysis?.acoustic_anomaly ?? 0;
  const duration = data.audio_metadata?.processed_duration_sec ?? 0;
  const snr = data.audio_metadata?.estimated_snr_db ?? 15;
  const hfRatio = data.prosody_analysis?.features?.hf_energy_ratio ?? 0;

  const aiLikelihood = Math.round(fakeProb * 100);
  const voiceNaturalness = Math.max(5, Math.min(100, Math.round((1 - anomaly) * 100)));
  const audioClarity: "Clear" | "Moderate" | "Low" =
    snr >= 18 ? "Clear" : snr >= 10 ? "Moderate" : "Low";

  // Phase 2: Spoken Language Identification (25 supported languages)
  const detectedLangRaw = data.detected_language || data.speech_profile?.detected_language || data.language_name || "";
  const langConfRaw = data.language_confidence ?? data.speech_profile?.language_confidence ?? 0;
  let detectedLanguage = "Unclear";
  const languageConfidence = Math.round(langConfRaw * 100);

  if (langConfRaw >= 0.50 && detectedLangRaw && detectedLangRaw !== "Unclear" && detectedLangRaw !== "Unknown") {
    detectedLanguage = detectedLangRaw;
  } else {
    detectedLanguage = "Unclear";
  }

  // Unified Classification Contract: GENUINE_LIVE | REPLAYED_RECORDED | SYNTHETIC_AI_GENERATED | UNCERTAIN
  const backendVerdict = data.classification || data.verdict;
  let verdict: VerdictType = "UNCERTAIN";
  let verdictLabel = "Uncertain";
  let verdictColor: "green" | "red" | "amber" | "yellow" = "yellow";
  let explanation = "The audio characteristics are ambiguous or borderline, preventing a conclusive determination.";
  let recommendedAction = "Inconclusive audio — please obtain a clearer voice sample.";
  let uncertainReason: "mixed_signals" | "low_quality" | "short_audio" | undefined = undefined;

  // Derive verdict based on authoritative backend classification or calibrated multi-signal fallback
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
    : (
        (aiLikelihood >= 35 && aiLikelihood <= 65) ||
        (voiceNaturalness >= 40 && voiceNaturalness <= 60 && hfRatio >= 0.60) ||
        (voiceNaturalness >= 40 && voiceNaturalness <= 60 && aiLikelihood >= 40 && aiLikelihood <= 60)
      )
    ? "UNCERTAIN"
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
}
