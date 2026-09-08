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
  /** Gemini-generated human-readable explanation (undefined if GEMINI_API_KEY not set) */
  gemini_explanation?: string;
  recommendedAction: string;
  flags: string[];
  audio_metadata?: AudioMetadata;
  // Unified input, language, and simplified presentation
  input_type?: "video" | "audio" | "live";
  detected_language?: string;
  language_code?: string;
  language_confidence?: number;
  is_long_recording?: boolean;
  user_notice?: string;
  simple_verdict?: string;
  simple_verdict_badge?: string;
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
  pipeline?: {
    ffmpeg_available?: boolean;
    aasist_loaded?: boolean;
    wav2vec2_loaded?: boolean;
    whisper_asr_loaded?: boolean;
    reality_defender_configured?: boolean;
    gemini_configured?: boolean;
    assemblyai_configured?: boolean;
  };
}

export type NavTab = "dashboard" | "upload" | "record" | "results" | "history";
