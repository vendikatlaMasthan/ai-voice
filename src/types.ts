export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  supported_models: string[];
  hardware_profile?: string;
  phases_active?: number[];
}

export interface DeepfakeResult {
  prediction: "REAL" | "FAKE" | string;
  fake_probability: number;
  real_probability: number;
  model_type: string;
  model_id: string;
  inference_time_ms: number;
  disclaimer?: string | null;
}

export interface SpeakerVerificationDetail {
  status: "EVALUATED" | "NOT_EVALUATED" | "NOT_ENROLLED" | string;
  speaker_id?: string | null;
  similarity_score?: number | null;
  threshold?: number | null;
  is_match?: boolean | null;
  speaker_mismatch_flag?: number | null;
  sample_count?: number | null;
  inference_time_ms?: number | null;
}

export interface ProsodyAnalysis {
  acoustic_anomaly: number;
  features: Record<string, number>;
  anomaly_reasons: string[];
  status: string;
  metadata?: Record<string, unknown>;
}

export interface RiskSignals {
  fake_probability: number;
  speaker_mismatch: number;
  acoustic_anomaly: number;
  context_flag: number;
  speaker_verification_status: string;
  acoustic_model_status: string;
  prosody_reasons?: string[];
  prosody_features?: Record<string, number>;
}

export interface AudioMetadata {
  sample_rate: number;
  original_duration_sec: number;
  processed_duration_sec: number;
  estimated_snr_db: number;
  rms_db: number;
}

export interface SpeechProfile {
  language: string;
  language_code: string;
  selected_language: string;
  detected_language: string;
  is_auto_detected: boolean;
  language_confidence?: number | null;
  accent_region?: string | null;
  accent_profile?: string | null;
  transcript_language?: string | null;
  is_authoritative?: boolean;
  disclaimer?: string | null;
}

export type SecondaryVerificationStatus =
  | "PENDING"
  | "CHALLENGE_REQUIRED"
  | "VERIFICATION_IN_PROGRESS"
  | "VERIFIED"
  | "FAILED"
  | "ESCALATED"
  | "BLOCKED";

export type VerificationMethod =
  | "VERIFY_CALLER"
  | "INDEPENDENT_CALLBACK"
  | "REQUIRE_MFA_OTP"
  | "ESCALATE_TO_SUPERVISOR";

export interface VerificationAuditRecord {
  id: string;
  call_id: string;
  timestamp: number;
  previous_state: string;
  new_state: string;
  action: string;
  actor: string;
  method?: string | null;
  notes?: string | null;
  is_simulated: boolean;
}

export interface VerificationSessionState {
  call_id: string;
  status: SecondaryVerificationStatus;
  recommended_action: string;
  risk_score: number;
  risk_level: string;
  is_held: boolean;
  hold_reason?: string | null;
  selected_method?: string | null;
  in_progress_step?: string | null;
  audit_trail: VerificationAuditRecord[];
  context_metadata?: Record<string, any>;
  created_at: number;
  updated_at: number;
}

export interface AnalyzeResponse {
  call_id: string;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  deepfake_detection: DeepfakeResult;
  speaker_verification: SpeakerVerificationDetail;
  prosody_analysis?: ProsodyAnalysis;
  risk_signals: RiskSignals;
  flags: string[];
  recommended_action: "ALLOW" | "WARN" | "SECONDARY_VERIFICATION" | "BLOCK" | string;
  audio_metadata: AudioMetadata;
  speech_profile?: SpeechProfile;
  language_profile?: SpeechProfile;
  language?: string;
  language_name?: string;
  language_confidence?: number;
  transcript?: string;
  speech_context_flags?: string[];
  asr_analysis?: {
    language: string;
    language_name: string;
    language_confidence: number;
    transcript: string;
    is_speech: boolean;
    inference_time_ms: number;
    keywords_detected?: string[];
    speech_context_flags?: string[];
  };
  verification_session?: VerificationSessionState;
}


export interface EnrollmentResponse {
  status: "ENROLLED" | string;
  speaker_id: string;
  speaker_name?: string | null;
  sample_count: number;
  embedding_dimension: number;
  message: string;
  sample_rate_verified: number;
  created_at?: number;
  updated_at?: number;
  inference_time_ms: number;
}

export interface VerifySpeakerResponse {
  status: string;
  speaker_id: string;
  similarity_score: number;
  threshold: number;
  match: boolean;
  speaker_mismatch_flag: number;
  sample_count?: number;
  inference_time_ms: number;
  message: string;
}

export interface EnrolledSpeaker {
  speaker_id: string;
  speaker_name?: string | null;
  dimension: number;
  sample_count: number;
  created_at: number;
  updated_at?: number;
}

export interface SampleAudio {
  filename: string;
  url: string;
  description: string;
}

export interface CallContextState {
  speaker_id: string;
  verification_threshold: number;
  caller_id: string;
  is_caller_recognized: boolean;
  is_previously_flagged: boolean;
  claimed_role: string;
  requested_transaction_amount: string;
  normal_transaction_amount: string;
  is_urgent: boolean;
  urgency_reason: string;
  transcript_text: string;
  selected_language?: string;
  language?: string;
  detected_language?: string;
  language_confidence?: number;
  accent_region?: string;
  accent_profile?: string;
  transcript_language?: string;
}

export type LiveSessionStatus = "idle" | "chunking" | "streaming" | "listening" | "paused" | "completed" | "error";
export type LiveAnalysisMode = "microphone" | "simulation";

export interface AudioChunkWindow {
  index: number;
  startTimeSec: number;
  endTimeSec: number;
  blob: Blob;
  filename: string;
}

export interface LiveStreamAnalysisResult {
  session_id: string;
  call_id: string;
  window_index: number;
  server_latency_ms: number;
  window_duration_sec: number;
  sample_rate: number;
  fake_probability: number;
  real_probability: number;
  acoustic_anomaly: number;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  recommended_action: "ALLOW" | "WARN" | "SECONDARY_VERIFICATION" | "BLOCK" | string;
  flags: string[];
  prosody_reasons: string[];
  prosody_metrics: Record<string, any>;
  deepfake_detection: DeepfakeResult;
  speaker_verification: SpeakerVerificationDetail;
  audio_metrics: AudioMetadata;
  speech_profile?: SpeechProfile;
  language_profile?: SpeechProfile;
  language?: string;
  language_name?: string;
  language_confidence?: number;
  transcript?: string;
  speech_context_flags?: string[];
  asr_analysis?: {
    language: string;
    language_name: string;
    language_confidence: number;
    transcript: string;
    is_speech: boolean;
    inference_time_ms: number;
    keywords_detected?: string[];
    speech_context_flags?: string[];
  };
  timestamp: number;
  verification_session?: VerificationSessionState;
}

export interface LiveChunkResult {
  chunkIndex: number;
  totalChunks: number;
  startTimeSec: number;
  endTimeSec: number;
  durationSec: number;
  processingLatencyMs: number;
  response: AnalyzeResponse;
  timestamp: number;
}

export type SecurityEventSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type SecurityEventType =
  | "HIGH_RISK_CALL"
  | "DEEPFAKE_VOICE_CLONE"
  | "EXECUTIVE_IMPERSONATION"
  | "ROLE_MISMATCH"
  | "PREVIOUS_FRAUD_HISTORY"
  | "TRANSACTION_AUTO_HOLD"
  | "SPEAKER_MISMATCH"
  | "ACOUSTIC_ANOMALY"
  | "VERIFICATION_FAILED"
  | "VERIFICATION_ESCALATED"
  | "CALL_BLOCKED";

export type EventFilterType =
  | "ALL"
  | "CRITICAL"
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "UNRESOLVED"
  | "VERIFICATION_REQUIRED"
  | "BLOCKED";

export type SecurityEventFilterType = EventFilterType;

export interface SecurityEvent {
  id: string;
  call_id: string;
  organization_id: string;
  event_type: SecurityEventType;
  severity: SecurityEventSeverity;
  timestamp: number | string;
  caller_id?: string | null;
  contact_id?: string | null;
  contact_name?: string | null;
  claimed_role?: string | null;
  speaker_id?: string | null;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  explanation: string;
  recommended_action: "ALLOW" | "WARN" | "SECONDARY_VERIFICATION" | "BLOCK" | string;
  verification_status?: SecondaryVerificationStatus | string | null;
  verification_session?: VerificationSessionState | null;
  is_held: boolean;
  transaction_amount?: number | null;
  hold_reason?: string | null;
  flags: string[];
  contributing_signals?: Record<string, any>;
  status: "OPEN" | "RESOLVED" | "ESCALATED" | "INVESTIGATING" | string;
  resolved_at?: number | null;
  resolved_by?: string | null;
  is_simulated?: boolean;
}

export interface SecurityEventsSummary {
  total_events: number;
  active_threats: number;
  critical_events: number;
  calls_requiring_verification: number;
  transactions_on_hold: number;
  blocked_calls: number;
}

export interface OrganizationPolicy {
  id?: string;
  organization_id: string;
  fake_prob_critical_threshold: number;
  fake_prob_warn_threshold: number;
  speaker_verification_strictness: number;
  acoustic_anomaly_sensitivity: number;
  transaction_auto_hold_amount: number;
  step_up_verification_required: boolean;
  auto_block_on_critical_deepfake: boolean;
  updated_at?: string;
}

export interface PolicyAuditLog {
  id: string;
  organization_id: string;
  actor: string;
  action: string;
  resource_type?: string;
  timestamp: number;
  changes: Array<{ field: string; prev: any; next: any }>;
  policy?: Partial<OrganizationPolicy>;
  details?: Record<string, any>;
}

