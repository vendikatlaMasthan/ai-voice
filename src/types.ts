export type VerdictType =
  | "GENUINE_LIVE"
  | "REPLAYED_RECORDED"
  | "SYNTHETIC_AI"
  | "SYNTHETIC_AI_GENERATED"
  | "UNCERTAIN";

export interface AnalysisRecord {
  id: string;
  timestamp: number;
  fileName: string;
  durationSec?: number;
  verdict: VerdictType;
  verdictLabel: string;
  verdictColor: "green" | "red" | "amber" | "yellow";
  explanation: string;
  recommendedAction: string;
  aiLikelihood: number; // 0 - 100% (from spoof_probability)
  spoofProbability: number;
  bonafideProbability?: number;
  modelName: string; // "AASIST"
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
  model: string;
  device?: string;
  weights_loaded?: boolean;
}

export type NavTab = "dashboard" | "upload" | "record" | "results" | "history";
