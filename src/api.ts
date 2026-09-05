import {
  AnalyzeResponse,
  EnrollmentResponse,
  HealthResponse,
  VerifySpeakerResponse,
  EnrolledSpeaker,
  SampleAudio,
  CallContextState,
  OrganizationPolicy,
  PolicyAuditLog,
} from "./types";

// Base API URL. In AI Studio, port 3000 routes both Vite frontend and Express proxy backend.
const API_BASE = "";

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchSpeakers(): Promise<EnrolledSpeaker[]> {
  try {
    const res = await fetch(`${API_BASE}/api/speakers`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.speakers || [];
  } catch (e) {
    return [];
  }
}

export async function fetchSamples(): Promise<SampleAudio[]> {
  try {
    const res = await fetch(`${API_BASE}/api/samples`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.samples || [];
  } catch (e) {
    return [];
  }
}

export async function analyzeAudio(
  audioFile: File | Blob,
  fileName: string,
  context: Partial<CallContextState>
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", audioFile, fileName);

  if (context.speaker_id && context.speaker_id.trim()) {
    formData.append("speaker_id", context.speaker_id.trim());
  }
  if (context.verification_threshold !== undefined) {
    formData.append("verification_threshold", String(context.verification_threshold));
  }
  if (context.caller_id && context.caller_id.trim()) {
    formData.append("caller_id", context.caller_id.trim());
  }
  if (context.is_caller_recognized !== undefined) {
    formData.append("is_caller_recognized", String(context.is_caller_recognized));
  }
  if (context.is_previously_flagged !== undefined) {
    formData.append("is_previously_flagged", String(context.is_previously_flagged));
  }
  if (context.claimed_role && context.claimed_role.trim()) {
    formData.append("claimed_role", context.claimed_role.trim());
  }
  if (context.requested_transaction_amount && Number(context.requested_transaction_amount) > 0) {
    formData.append("requested_transaction_amount", context.requested_transaction_amount);
  }
  if (context.normal_transaction_amount && Number(context.normal_transaction_amount) > 0) {
    formData.append("normal_transaction_amount", context.normal_transaction_amount);
  }
  if (context.is_urgent !== undefined) {
    formData.append("is_urgent", String(context.is_urgent));
  }
  if (context.urgency_reason && context.urgency_reason.trim()) {
    formData.append("urgency_reason", context.urgency_reason.trim());
  }
  if (context.transcript_text && context.transcript_text.trim()) {
    formData.append("transcript_text", context.transcript_text.trim());
  }
  if (context.selected_language && context.selected_language.trim()) {
    formData.append("selected_language", context.selected_language.trim());
    formData.append("language", context.selected_language.trim());
  } else if (context.language && context.language.trim()) {
    formData.append("language", context.language.trim());
  }
  if (context.accent_region && context.accent_region.trim()) {
    formData.append("accent_region", context.accent_region.trim());
  }
  if (context.transcript_language && context.transcript_language.trim()) {
    formData.append("transcript_language", context.transcript_language.trim());
  }

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    const errorMsg = data.message || data.detail?.message || data.detail || `Analysis request failed with status ${res.status}`;
    const err = new Error(errorMsg);
    (err as any).error_type = data.error_type || data.detail?.error_type || "AnalysisError";
    (err as any).status = res.status;
    throw err;
  }

  return data as AnalyzeResponse;
}

export async function enrollSpeaker(
  audioFile: File | Blob,
  fileName: string,
  speakerId: string,
  speakerName?: string
): Promise<EnrollmentResponse> {
  const formData = new FormData();
  formData.append("file", audioFile, fileName);
  formData.append("speaker_id", speakerId.trim());
  if (speakerName && speakerName.trim()) {
    formData.append("speaker_name", speakerName.trim());
  }

  const res = await fetch(`${API_BASE}/api/enroll`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    const errorMsg = data.message || data.detail?.message || data.detail || `Enrollment failed with status ${res.status}`;
    const err = new Error(errorMsg);
    (err as any).error_type = data.error_type || "EnrollmentError";
    throw err;
  }

  return data as EnrollmentResponse;
}

export async function verifySpeakerApi(
  audioFile: File | Blob,
  fileName: string,
  speakerId: string,
  threshold?: number
): Promise<VerifySpeakerResponse> {
  const formData = new FormData();
  formData.append("file", audioFile, fileName);
  formData.append("speaker_id", speakerId.trim());
  if (threshold !== undefined) {
    formData.append("threshold", String(threshold));
  }

  const res = await fetch(`${API_BASE}/api/verify-speaker`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    const errorMsg = data.message || data.detail?.message || data.detail || `Verification failed with status ${res.status}`;
    const err = new Error(errorMsg);
    (err as any).error_type = data.error_type || "VerificationError";
    throw err;
  }

  return data as VerifySpeakerResponse;
}

export async function fetchVerificationSession(callId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/verification/${encodeURIComponent(callId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch verification session for ${callId}`);
  }
  const data = await res.json();
  return data.verification_session;
}

export async function postVerificationAction(payload: {
  call_id: string;
  action: "START_VERIFICATION" | "COMPLETE_VERIFICATION" | "ESCALATE" | "BLOCK" | string;
  method?: string;
  result?: "SUCCESS" | "FAILURE" | string;
  notes?: string;
  actor?: string;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/api/verification/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Verification action failed with HTTP ${res.status}`);
  }
  return data.verification_session;
}

export async function fetchSecurityEvents(
  filter?: string,
  search?: string
): Promise<{ events: any[]; summary: any }> {
  const params = new URLSearchParams();
  if (filter && filter !== "ALL") params.append("filter", filter);
  if (search && search.trim()) params.append("search", search.trim());

  const url = `${API_BASE}/api/security-events${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch security events with HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchSecuritySummary(): Promise<any> {
  const res = await fetch(`${API_BASE}/api/security-events/summary`);
  if (!res.ok) {
    throw new Error(`Failed to fetch security summary with HTTP ${res.status}`);
  }
  return res.json();
}

export async function resolveSecurityEvent(eventId: string, notes?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/security-events/${encodeURIComponent(eventId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Failed to resolve event with HTTP ${res.status}`);
  }
  return res.json();
}

export async function escalateSecurityEvent(eventId: string, notes?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/security-events/${encodeURIComponent(eventId)}/escalate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Failed to escalate event with HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchOrganizationPolicy(): Promise<{ organization_id: string; policy: OrganizationPolicy }> {
  const res = await fetch(`${API_BASE}/api/policy`);
  if (!res.ok) {
    throw new Error(`Failed to fetch policy with HTTP ${res.status}`);
  }
  return res.json();
}

export async function updateOrganizationPolicy(
  policy: Partial<OrganizationPolicy>,
  actor: string = "SecurityAdmin"
): Promise<{ organization_id: string; policy: OrganizationPolicy; changes: any[]; audit_entry: any }> {
  const res = await fetch(`${API_BASE}/api/policy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, actor }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Failed to update policy with HTTP ${res.status}`);
  }
  return res.json();
}

export async function resetOrganizationPolicy(
  actor: string = "SecurityAdmin"
): Promise<{ organization_id: string; policy: OrganizationPolicy; changes: any[]; audit_entry: any }> {
  const res = await fetch(`${API_BASE}/api/policy/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Failed to reset policy with HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchPolicyAuditLogs(): Promise<{ organization_id: string; audit_logs: PolicyAuditLog[] }> {
  const res = await fetch(`${API_BASE}/api/policy/audit-logs`);
  if (!res.ok) {
    throw new Error(`Failed to fetch policy audit logs with HTTP ${res.status}`);
  }
  return res.json();
}

