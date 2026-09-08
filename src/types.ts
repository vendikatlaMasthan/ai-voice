export type ClassificationType =
  | "GENUINE_LIVE"
  | "REPLAYED_RECORDED"
  | "SYNTHETIC_AI_GENERATED"
  | "UNCERTAIN";

export type VerdictType = ClassificationType;

export interface SubScores {
  synthetic_voice_score: number; // 0 - 100
  replay_channel_score: number; // 0 - 100
  naturalness_score: number; // 0 - 100
}

export type RiskLevel = "Low" | "Medium" | "High";

export interface AudioMetadata {
  sample_rate: number;
  original_duration_sec?: number;
  processed_duration_sec?: number;
  estimated_snr_db?: number;
  rms_db?: number;
}

export interface AnalysisRecord {
  id: string;
  timestamp: number;
  fileName: string;
  durationSec?: number;
  classification: ClassificationType;
  verdict: ClassificationType;
  verdictLabel: string;
  verdictColor: "green" | "red" | "amber" | "yellow";
  sub_scores: SubScores;
  detection_source: string; // "reality_defender" | "aasist" | "wav2vec2" | "local_fallback"
  risk_level: RiskLevel;
  explanation: string;
  recommendedAction: string;
  flags: string[];
  audio_metadata?: AudioMetadata;
  // Legacy / convenience fields
  aiLikelihood: number; // mapped from sub_scores.synthetic_voice_score
  spoofProbability: number;
  bonafideProbability?: number;
  modelName: string;
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
  service?: string;
  architecture?: string;
  model?: string;
  device?: string;
  weights_loaded?: boolean;
}

export type NavTab = "dashboard" | "upload" | "record" | "results" | "history";
