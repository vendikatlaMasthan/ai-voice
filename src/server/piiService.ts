/**
 * VoiceShield AI — TypeScript PII Minimization & Masking Service
 * Provides consistent data anonymization across server logs, audit events, and API payloads.
 */

export function maskPhoneNumber(phone?: string | null): string {
  if (!phone) return "";
  const clean = String(phone).trim();
  if (clean.length <= 5) {
    return clean.length > 2
      ? "*".repeat(Math.max(1, clean.length - 2)) + clean.slice(-2)
      : "*".repeat(Math.max(0, clean.length - 1)) + clean.slice(-1);
  }

  const digitIndices: number[] = [];
  for (let i = 0; i < clean.length; i++) {
    if (/\d/.test(clean[i])) {
      digitIndices.push(i);
    }
  }

  if (digitIndices.length <= 5) {
    return "*".repeat(Math.max(1, clean.length - 2)) + clean.slice(-2);
  }

  const keepPrefix = Math.min(2, digitIndices.length - 4);
  const keepSuffix = 4;
  const maskIndices = new Set(digitIndices.slice(keepPrefix, digitIndices.length - keepSuffix));

  const chars = clean.split("").map((ch, i) => (maskIndices.has(i) ? "*" : ch));
  return chars.join("");
}

export function maskEmail(email?: string | null): string {
  if (!email || !email.includes("@")) return email || "";
  const [user, domain] = email.split("@");
  if (user.length <= 2) {
    return `${user[0]}*@${domain}`;
  }
  const maskedUser = user[0] + "*".repeat(user.length - 2) + user[user.length - 1];
  return `${maskedUser}@${domain}`;
}

export function sanitizeAuditLogPayload<T extends Record<string, any>>(payload: T): T {
  if (!payload || typeof payload !== "object") return payload;
  const copy: Record<string, any> = { ...payload };

  if (copy.caller_id) {
    copy.caller_id_masked = maskPhoneNumber(copy.caller_id);
    copy.caller_id = copy.caller_id_masked;
  }
  if (copy.phone) {
    copy.phone = maskPhoneNumber(copy.phone);
  }
  if (copy.contact_phone) {
    copy.contact_phone = maskPhoneNumber(copy.contact_phone);
  }
  if (copy.email) {
    copy.email = maskEmail(copy.email);
  }
  return copy as T;
}
