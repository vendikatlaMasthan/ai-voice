import { AnalysisRecord, HealthResponse, SampleAudio } from "./types";
import { analyzeAudioInBrowser } from "./audioAnalysisEngine";

/**
 * Built-in audio samples for static hosting (e.g. GitHub Pages).
 * These reference static assets copied into the /samples folder.
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
 * Checks service health.
 * Since this application is statically hosted without an active API backend,
 * this function reports the active in-browser DSP client engine.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return {
    status: "ok",
    service: "VoiceShield Client-Side WebAudio DSP Engine",
    version: "2.1.0-browser",
  };
}

/**
 * Retrieves demo audio samples.
 * On static hosting, provides the built-in sample collection.
 * Includes defensive content-type verification to prevent HTML parse crashes.
 */
export async function fetchSamples(): Promise<SampleAudio[]> {
  return BUILTIN_SAMPLES;
}

/**
 * Analyzes voice audio sample.
 *
 * Runs 100% client-side in the browser using the Web Audio API:
 * - Decodes audio waveform via AudioContext
 * - Tracks fundamental frequency (F0) & pitch variance
 * - Measures vocal micro-jitter and shimmer perturbations
 * - Computes zero-crossing rate and spectral flatness (Wiener entropy)
 * - Evaluates high-frequency energy ratio and harmonic-to-noise ratio (HNR)
 * - Derives signal-based acoustic authenticity heuristics
 */
export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string
): Promise<AnalysisRecord> {
  return analyzeAudioInBrowser(audioFile, fileName);
}
