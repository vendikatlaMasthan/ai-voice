/**
 * VoiceShield AI — TypeScript Client SDK
 * Production-ready client library for integrating VoiceShield real-time deepfake defense,
 * multi-sample speaker consistency, and contextual fraud prevention.
 */

import { VoiceShieldLiveStream } from "./liveStream";
import {
  AnalyzeAudioOptions,
  AnalyzeResult,
  EnrolledSpeakerResult,
  EnrollSpeakerOptions,
  EnrollSpeakerResult,
  LiveStreamOptions,
  OrganizationPolicyResult,
  VerifySpeakerOptions,
  VerifySpeakerResult,
  VoiceShieldClientOptions,
} from "./types";

export class VoiceShieldClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeoutMs: number;
  private customFetch: typeof fetch;
  private WebSocketClass?: any;

  constructor(options: VoiceShieldClientOptions = {}) {
    this.baseUrl = (options.baseUrl || "http://localhost:3000").replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeoutMs = options.timeoutMs || 30000;
    this.customFetch = options.fetch || (typeof fetch !== "undefined" ? fetch.bind(globalThis) : (null as any));
    this.WebSocketClass = options.WebSocketClass;

    if (!this.customFetch) {
      throw new Error(
        "Fetch implementation not found. In Node.js environments < 18, provide a custom fetch implementation in client options."
      );
    }
  }

  /**
   * Helper to construct authorized request headers.
   */
  private getHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
    const headers: Record<string, string> = { ...additionalHeaders };
    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }
    return headers;
  }

  /**
   * Executes a fetch with configurable timeout.
   */
  private async executeFetch(url: string, init: RequestInit): Promise<Response> {
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), this.timeoutMs) : null;

    try {
      const response = await this.customFetch(url, {
        ...init,
        signal: controller ? controller.signal : undefined,
      });
      return response;
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  }

  private appendAudioToFormData(formData: FormData, fieldName: string, audio: any, filename?: string) {
    const fn = filename || "audio.wav";
    if (typeof Blob !== "undefined") {
      if (audio instanceof Blob) {
        formData.append(fieldName, audio, fn);
      } else if (audio instanceof ArrayBuffer || audio instanceof Uint8Array) {
        const blob = new Blob([audio], { type: "audio/wav" });
        formData.append(fieldName, blob, fn);
      } else if (typeof Buffer !== "undefined" && Buffer.isBuffer(audio)) {
        const blob = new Blob([audio], { type: "audio/wav" });
        formData.append(fieldName, blob, fn);
      } else {
        try {
          const blob = new Blob([audio], { type: "audio/wav" });
          formData.append(fieldName, blob, fn);
        } catch {
          formData.append(fieldName, audio, fn);
        }
      }
    } else {
      formData.append(fieldName, audio, fn);
    }
  }

  /**
   * Evaluates an audio file for deepfake synthesis, acoustic/prosody anomalies, speaker match, and contextual fraud.
   *
   * @param options Audio upload options and optional contextual fraud metadata
   * @returns Detailed multi-signal risk analysis verdict
   */
  public async analyzeAudio(options: AnalyzeAudioOptions): Promise<AnalyzeResult> {
    if (!options.audio) {
      throw new Error("Audio payload is required for analysis.");
    }

    const formData = new FormData();
    this.appendAudioToFormData(formData, "file", options.audio, options.filename || "analyze.wav");

    if (options.speakerId) formData.append("speaker_id", options.speakerId);
    if (options.verificationThreshold !== undefined) {
      formData.append("verification_threshold", String(options.verificationThreshold));
    }
    if (options.organizationId) formData.append("organization_id", options.organizationId);
    if (options.callerId) formData.append("caller_id", options.callerId);
    if (options.contactId) formData.append("contact_id", options.contactId);
    if (options.claimedRole) formData.append("claimed_role", options.claimedRole);
    if (options.requestedAmount !== undefined) {
      formData.append("requested_transaction_amount", String(options.requestedAmount));
    }
    if (options.normalAmount !== undefined) {
      formData.append("normal_transaction_amount", String(options.normalAmount));
    }
    if (options.transactionReference) formData.append("transaction_reference", options.transactionReference);
    if (options.isUrgent !== undefined) formData.append("is_urgent", String(options.isUrgent));
    if (options.urgencyReason) formData.append("urgency_reason", options.urgencyReason);
    if (options.transcriptText) formData.append("transcript_text", options.transcriptText);
    if (options.language) formData.append("language", options.language);

    const response = await this.executeFetch(`${this.baseUrl}/api/analyze`, {
      method: "POST",
      headers: this.getHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.message || `Analysis failed with HTTP status ${response.status}`);
    }

    return (await response.json()) as AnalyzeResult;
  }

  /**
   * Enrolls a genuine voice sample. Automatically updates the incremental centroid embedding across sessions.
   *
   * @param options Audio data, speakerId, and optional display name
   * @returns Enrollment confirmation with updated sample_count
   */
  public async enrollSpeaker(options: EnrollSpeakerOptions): Promise<EnrollSpeakerResult> {
    if (!options.audio) {
      throw new Error("Audio payload is required for speaker enrollment.");
    }
    if (!options.speakerId) {
      throw new Error("Field 'speakerId' is required for speaker enrollment.");
    }

    const formData = new FormData();
    this.appendAudioToFormData(formData, "file", options.audio, options.filename || "enroll.wav");
    formData.append("speaker_id", options.speakerId);
    if (options.speakerName) formData.append("speaker_name", options.speakerName);

    const response = await this.executeFetch(`${this.baseUrl}/api/enroll`, {
      method: "POST",
      headers: this.getHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.message || `Enrollment failed with HTTP status ${response.status}`);
    }

    return (await response.json()) as EnrollSpeakerResult;
  }

  /**
   * Compares a query audio sample against an enrolled speaker's multi-sample centroid.
   *
   * @param options Query audio, speakerId, and threshold
   * @returns Biometric cosine similarity and match verdict
   */
  public async verifySpeaker(options: VerifySpeakerOptions): Promise<VerifySpeakerResult> {
    if (!options.audio) {
      throw new Error("Audio payload is required for speaker verification.");
    }
    if (!options.speakerId) {
      throw new Error("Field 'speakerId' is required for speaker verification.");
    }

    const formData = new FormData();
    this.appendAudioToFormData(formData, "file", options.audio, options.filename || "verify.wav");
    formData.append("speaker_id", options.speakerId);
    if (options.threshold !== undefined) formData.append("threshold", String(options.threshold));

    const response = await this.executeFetch(`${this.baseUrl}/api/verify-speaker`, {
      method: "POST",
      headers: this.getHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.message || `Verification failed with HTTP status ${response.status}`);
    }

    return (await response.json()) as VerifySpeakerResult;
  }

  /**
   * Retrieves list of all enrolled biometric speaker profiles.
   */
  public async getSpeakers(): Promise<EnrolledSpeakerResult[]> {
    const response = await this.executeFetch(`${this.baseUrl}/api/speakers`, {
      method: "GET",
      headers: this.getHeaders({ Accept: "application/json" }),
    });

    if (!response.ok) {
      throw new Error(`Failed to list speakers with HTTP status ${response.status}`);
    }

    const body = await response.json();
    return (body.speakers || []) as EnrolledSpeakerResult[];
  }

  /**
   * Retrieves the authoritative security & risk policy for an organization.
   */
  public async getPolicy(organizationId?: string): Promise<OrganizationPolicyResult> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    const response = await this.executeFetch(`${this.baseUrl}/api/policy${query}`, {
      method: "GET",
      headers: this.getHeaders({ Accept: "application/json" }),
    });

    if (!response.ok) {
      throw new Error(`Failed to retrieve policy with HTTP status ${response.status}`);
    }

    const body = await response.json();
    return (body.policy || body) as OrganizationPolicyResult;
  }

  /**
   * Checks server health and model warmup status.
   */
  public async getHealth(): Promise<{ status: string; models_ready?: boolean; uptime_sec?: number }> {
    const response = await this.executeFetch(`${this.baseUrl}/api/health`, {
      method: "GET",
      headers: this.getHeaders({ Accept: "application/json" }),
    });

    if (!response.ok) {
      throw new Error(`Health check failed with HTTP status ${response.status}`);
    }

    return await response.json();
  }

  /**
   * Opens a real-time live streaming session over WebSocket (/ws/live-stream).
   *
   * @param options Live stream configuration options
   * @returns A VoiceShieldLiveStream instance for sending audio and listening for results
   */
  public startLiveStream(options: LiveStreamOptions = {}): VoiceShieldLiveStream {
    const wsBaseUrl = this.baseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    const wsUrl = `${wsBaseUrl}/ws/live-stream`;

    return new VoiceShieldLiveStream(wsUrl, options, this.apiKey, this.WebSocketClass);
  }
}
