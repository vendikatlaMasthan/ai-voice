export type VerdictType =
  | "GENUINE_LIVE"
  | "REPLAYED_RECORDED"
  | "SYNTHETIC_AI"
  | "UNCERTAIN";

export interface AnalysisRecord {
  id: string;
  timestamp: number;
  fileName: string;
  durationSec: number;
  verdict: VerdictType;
  verdictLabel: string;
  verdictColor: "green" | "red" | "amber" | "yellow";
  explanation: string;
  recommendedAction: string;
  aiLikelihood: number; // 0 - 100%
  voiceNaturalness: number; // 0 - 100%
  audioClarity: "Clear" | "Moderate" | "Low";
  audioUrl?: string;
  rawResponse?: any;
}

export interface SampleAudio {
  filename: string;
  url: string;
  description: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export type NavTab = "dashboard" | "upload" | "record" | "results" | "history";
