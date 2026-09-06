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
  const timeoutId = setTimeout(() => controller.abort(), 20000); // 20-second client timeout

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

  let verdict: VerdictType = "UNCERTAIN";
  let verdictLabel = "Uncertain";
  let verdictColor: "green" | "red" | "amber" | "yellow" = "yellow";
  let explanation = "The audio characteristics are ambiguous or borderline, preventing a conclusive determination.";
  let recommendedAction = "Inconclusive audio — please obtain a clearer voice sample.";

  if (fakeProb >= 0.65) {
    verdict = "SYNTHETIC_AI";
    verdictLabel = "Synthetic AI-Generated";
    verdictColor = "red";
    explanation = "This audio exhibits digital synthesis artifacts typical of AI voice cloning models.";
    recommendedAction = "This voice appears synthetic — verify before trusting it.";
  } else if (fakeProb < 0.35 && anomaly < 0.60 && snr >= 12) {
    verdict = "GENUINE_LIVE";
    verdictLabel = "Genuine Live";
    verdictColor = "green";
    explanation = "Natural vocal variations, pauses, and acoustics characteristic of an authentic live human speaker.";
    recommendedAction = "This voice appears genuine — no action needed.";
  } else if (snr < 10 || (anomaly >= 0.60 && fakeProb < 0.50)) {
    verdict = "REPLAYED_RECORDED";
    verdictLabel = "Replayed-Recorded";
    verdictColor = "amber";
    explanation = "Acoustic signatures suggest audio played back through a loudspeaker or re-recorded with room acoustics.";
    recommendedAction = "This voice appears to be a recording played through a speaker — verify identity.";
  }

  const aiLikelihood = Math.round(fakeProb * 100);
  const voiceNaturalness = Math.max(5, Math.min(100, Math.round((1 - anomaly) * 100)));
  const audioClarity: "Clear" | "Moderate" | "Low" =
    snr >= 18 ? "Clear" : snr >= 10 ? "Moderate" : "Low";

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
    audioUrl,
    rawResponse: data,
  };
}
