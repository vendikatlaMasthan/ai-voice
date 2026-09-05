/**
 * VoiceShield AI — TypeScript SDK Types
 * Reusable type contracts for enterprise, banking, and telecom integrations.
 */

export interface VoiceShieldClientOptions {
  /** Base HTTP URL of the VoiceShield AI server (e.g. "http://localhost:3000" or "https://api.voiceshield.internal") */
  baseUrl?: string;
  /** Optional API Key sent via `X-API-Key` header */
  apiKey?: string;
  /** Request timeout in milliseconds (default: 30000ms) */
  timeoutMs?: number;
  /** Custom fetch implementation (defaults to global fetch) */
  fetch?: typeof fetch;
  /** Custom WebSocket implementation for Node.js environments if global WebSocket is not available */
  WebSocketClass?: any;
}

export interface DeepfakeDetectionResult {
  prediction: "REAL" | "FAKE" | string;
  fake_probability: number;
  real_probability: number;
  model_type: string;
  inference_time_ms: number;
}

export interface SpeakerVerificationResult {
  status: "EVALUATED" | "NOT_EVALUATED" | "NOT_ENROLLED" | string;
  speaker_id?: string | null;
  similarity_score?: number | null;
  threshold?: number | null;
  is_match?: boolean | null;
  speaker_mismatch_flag?: number | null;
  sample_count?: number | null;
  inference_time_ms?: number | null;
}

export interface ProsodyAnalysisResult {
  acoustic_anomaly: number;
  features: Record<string, number>;
  anomaly_reasons: string[];
  status: string;
}

export interface ASRAnalysisResult {
  language: string;
  language_name: string;
  language_confidence: number;
  transcript: string;
  is_speech: boolean;
  inference_time_ms: number;
  keywords_detected?: string[];
  speech_context_flags?: string[];
}

export interface RiskSignalsResult {
  fake_probability: number;
  speaker_mismatch: number;
  acoustic_anomaly: number;
  context_flag: number;
  speaker_verification_status: string;
  acoustic_model_status: string;
  prosody_reasons?: string[];
}

export interface AudioMetadataResult {
  sample_rate: number;
  original_duration_sec: number;
  processed_duration_sec: number;
  estimated_snr_db: number;
  rms_db: number;
}

export interface VerificationSessionResult {
  call_id: string;
  status: "PENDING" | "CHALLENGE_REQUIRED" | "VERIFICATION_IN_PROGRESS" | "VERIFIED" | "FAILED" | "ESCALATED" | "BLOCKED" | string;
  recommended_action: string;
  risk_score: number;
  risk_level: string;
  is_held: boolean;
  hold_reason?: string | null;
  selected_method?: string | null;
  in_progress_step?: string | null;
  created_at: number;
  updated_at: number;
}

export interface AnalyzeResult {
  call_id: string;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  deepfake_detection: DeepfakeDetectionResult;
  speaker_verification: SpeakerVerificationResult;
  prosody_analysis?: ProsodyAnalysisResult;
  risk_signals: RiskSignalsResult;
  flags: string[];
  recommended_action: "ALLOW" | "WARN" | "SECONDARY_VERIFICATION" | "BLOCK" | string;
  audio_metadata: AudioMetadataResult;
  language?: string;
  language_name?: string;
  language_confidence?: number;
  transcript?: string;
  speech_context_flags?: string[];
  asr_analysis?: ASRAnalysisResult;
  verification_session?: VerificationSessionResult;
  pipeline_latency_ms?: number;
}

export interface AnalyzeAudioOptions {
  /** Audio data: File, Blob, Buffer, Uint8Array, or ArrayBuffer */
  audio: File | Blob | Uint8Array | ArrayBuffer | any;
  /** Name of the audio file if using raw bytes (default: "audio.wav") */
  filename?: string;
  /** Enrolled speaker ID for biometric cross-session verification */
  speakerId?: string;
  /** Biometric verification strictness threshold (0.0 – 1.0, default: 0.70) */
  verificationThreshold?: number;
  /** Organization or Tenant ID */
  organizationId?: string;
  /** Inbound caller identifier / phone number */
  callerId?: string;
  /** Registered contact ID */
  contactId?: string;
  /** Role claimed by caller (e.g., "CEO", "Treasurer", "Account Manager") */
  claimedRole?: string;
  /** Financial transaction wire amount requested */
  requestedAmount?: number;
  /** Baseline normal transaction amount for this contact */
  normalAmount?: number;
  /** Transaction reference string */
  transactionReference?: string;
  /** Urgency indicator flag */
  isUrgent?: boolean;
  /** Justification given for transaction urgency */
  urgencyReason?: string;
  /** Known transcript text override (if pre-transcribed) */
  transcriptText?: string;
  /** Language hint (e.g., "hi", "en", "ta", "te") */
  language?: string;
}

export interface EnrollSpeakerOptions {
  /** Genuine reference audio sample (1.0s – 30.0s clean speech) */
  audio: File | Blob | Uint8Array | ArrayBuffer | any;
  /** Target speaker identifier (e.g., "EMP-9001", "CEO-JANE") */
  speakerId: string;
  /** Human-readable display name or title */
  speakerName?: string;
  /** Optional file name */
  filename?: string;
}

export interface EnrollSpeakerResult {
  status: "ENROLLED" | string;
  speaker_id: string;
  speaker_name?: string | null;
  sample_count: number;
  embedding_dimension: number;
  created_at: number;
  updated_at: number;
  message: string;
  sample_rate_verified: number;
  inference_time_ms: number;
}

export interface VerifySpeakerOptions {
  /** Query audio sample to compare against enrolled speaker centroid */
  audio: File | Blob | Uint8Array | ArrayBuffer | any;
  /** Target speaker identifier */
  speakerId: string;
  /** Decision threshold (default: 0.70) */
  threshold?: number;
  /** Optional file name */
  filename?: string;
}

export interface VerifySpeakerResult {
  status: "SUCCESS" | string;
  speaker_id: string;
  similarity_score: number;
  threshold: number;
  match: boolean;
  speaker_mismatch_flag: number;
  sample_count: number;
  inference_time_ms: number;
  message: string;
}

export interface EnrolledSpeakerResult {
  speaker_id: string;
  speaker_name?: string | null;
  dimension: number;
  sample_count: number;
  created_at: number;
  updated_at?: number;
}

export interface OrganizationPolicyResult {
  organization_id: string;
  name: string;
  fake_prob_critical_threshold: number;
  fake_prob_warn_threshold: number;
  transaction_auto_hold_amount: number;
  high_risk_wire_threshold: number;
  role_enforcement_strictness: string;
  speaker_verification_strictness: number;
  independent_callback_required: boolean;
  supervisor_escalation_required: boolean;
  otp_verification_required: boolean;
  version: number;
}

export interface LiveStreamOptions {
  /** Session identifier */
  sessionId?: string;
  /** Enrolled speaker ID for real-time biometric matching */
  speakerId?: string;
  /** Biometric verification threshold */
  threshold?: number;
  /** Sliding window duration in seconds (0.8 – 3.0s, default: 1.5s) */
  windowDurationSec?: number;
  /** Contextual fraud metadata */
  context?: {
    organization_id?: string;
    caller_id?: string;
    contact_id?: string;
    claimed_role?: string;
    requested_amount?: number;
    normal_amount?: number;
    is_urgent?: boolean;
    urgency_reason?: string;
    language?: string;
  };
}

export interface LiveStreamResultEvent {
  type: "analysis_result";
  session_id: string;
  window_index: number;
  data: AnalyzeResult;
}

export interface LiveStreamErrorEvent {
  type: "analysis_error";
  session_id: string;
  window_index?: number;
  error: string;
}

export interface LiveStreamSessionReadyEvent {
  type: "session_ready";
  session_id: string;
  window_duration_sec: number;
  window_size_bytes: number;
  sample_rate: number;
  speaker_id?: string | null;
}
