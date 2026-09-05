/**
 * VoiceShield AI — Notification & Webhook Dispatcher
 * Dispatches structured security/risk events via Webhook, SMS stub, and Email stub
 * with SSRF protection, bounded retry logic, and non-blocking asynchronous delivery.
 */

import http from "http";
import https from "https";
import { URL } from "url";

export interface VoiceShieldRiskEventPayload {
  event: "voice_risk_alert" | "transaction_hold_alert" | "secondary_verification_alert" | "threat_block_alert";
  call_id: string;
  session_id?: string | null;
  organization_id: string;
  risk_score: number;
  risk_level: string;
  recommended_action: string;
  timestamp: string;
  caller_id?: string | null;
  claimed_role?: string | null;
  transaction_amount?: number | null;
  hold_reason?: string | null;
  flags: string[];
  contributing_signals?: {
    fake_probability?: number;
    speaker_similarity?: number | null;
    speaker_match?: boolean | null;
    acoustic_anomaly?: number;
    role_mismatch?: boolean;
    language?: string;
  };
}

export interface WebhookDeliveryResult {
  success: boolean;
  attempts: number;
  status_code?: number;
  error?: string;
  duration_ms: number;
}

// Notification Adapter Interfaces for future SMS / Email provider plug-in
export interface EmailNotificationAdapter {
  sendSecurityAlert(to: string, subject: string, event: VoiceShieldRiskEventPayload): Promise<boolean>;
}

export interface SmsNotificationAdapter {
  sendSecuritySms(toPhoneNumber: string, alertText: string, event: VoiceShieldRiskEventPayload): Promise<boolean>;
}

// Default stub implementations (structured logging only, no real external provider)
export class StubEmailAdapter implements EmailNotificationAdapter {
  async sendSecurityAlert(to: string, subject: string, event: VoiceShieldRiskEventPayload): Promise<boolean> {
    console.log(`[Notification:EmailStub] Alert to ${to}: ${subject} (Risk: ${event.risk_score})`);
    return true;
  }
}

export class StubSmsAdapter implements SmsNotificationAdapter {
  async sendSecuritySms(toPhoneNumber: string, alertText: string, _event: VoiceShieldRiskEventPayload): Promise<boolean> {
    console.log(`[Notification:SmsStub] SMS to ${toPhoneNumber}: "${alertText}"`);
    return true;
  }
}

export class NotificationDispatcher {
  private allowLocalWebhooks: boolean;
  private defaultWebhookUrl?: string;
  private timeoutMs: number;
  private maxRetries: number;
  public emailAdapter: EmailNotificationAdapter;
  public smsAdapter: SmsNotificationAdapter;

  constructor() {
    this.allowLocalWebhooks = process.env.ALLOW_LOCAL_WEBHOOKS === "true" || process.env.NODE_ENV !== "production";
    this.defaultWebhookUrl = process.env.VOICESHIELD_WEBHOOK_URL || process.env.WEBHOOK_URL;
    this.timeoutMs = parseInt(process.env.WEBHOOK_TIMEOUT_MS || "5000", 10);
    this.maxRetries = parseInt(process.env.WEBHOOK_MAX_RETRIES || "2", 10);
    this.emailAdapter = new StubEmailAdapter();
    this.smsAdapter = new StubSmsAdapter();
  }

  /**
   * SSRF Protection: Validates URL hostname to prevent internal loopback/private network scanning.
   */
  public isSafeWebhookUrl(urlStr: string): { safe: boolean; reason?: string } {
    try {
      const parsed = new URL(urlStr);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return { safe: false, reason: "Unsupported protocol. Must be http: or https:." };
      }

      const hostname = parsed.hostname.toLowerCase();

      // If local testing/dev is explicitly enabled, allow localhost and loopback
      if (this.allowLocalWebhooks) {
        return { safe: true };
      }

      // Production SSRF checks: reject private / local IP ranges
      if (
        hostname === "localhost" ||
        hostname === "127.0.0.1" ||
        hostname === "::1" ||
        hostname.startsWith("10.") ||
        hostname.startsWith("192.168.") ||
        /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(hostname) ||
        hostname.startsWith("169.254.")
      ) {
        return { safe: false, reason: "Webhook target resolves to a private or loopback IP range (SSRF protection)." };
      }

      return { safe: true };
    } catch (e: any) {
      return { safe: false, reason: `Malformed webhook URL: ${e.message}` };
    }
  }

  /**
   * Dispatches a structured risk event to the configured webhook URL.
   * Runs asynchronously without blocking request handling.
   */
  public dispatchRiskEvent(event: VoiceShieldRiskEventPayload, targetWebhookUrl?: string): void {
    const url = targetWebhookUrl || this.defaultWebhookUrl;
    if (!url) {
      return; // No webhook configured
    }

    // Fire-and-forget in background with bounded retries
    this.sendWebhookWithRetry(url, event).catch((err) => {
      console.warn(`[WebhookDispatcher] Unhandled delivery failure to ${url}:`, err?.message || err);
    });
  }

  /**
   * Internal HTTP POST sender with exponential backoff retry.
   */
  public async sendWebhookWithRetry(
    targetUrl: string,
    payload: VoiceShieldRiskEventPayload
  ): Promise<WebhookDeliveryResult> {
    const urlCheck = this.isSafeWebhookUrl(targetUrl);
    if (!urlCheck.safe) {
      console.warn(`[WebhookDispatcher:Blocked] Webhook destination rejected: ${urlCheck.reason}`);
      return {
        success: false,
        attempts: 0,
        error: urlCheck.reason,
        duration_ms: 0,
      };
    }

    const payloadJson = JSON.stringify(payload);
    const startTime = Date.now();
    let attempts = 0;
    let lastError = "";
    let statusCode: number | undefined;

    while (attempts <= this.maxRetries) {
      attempts++;
      try {
        const res = await this.executeSinglePost(targetUrl, payloadJson);
        statusCode = res.statusCode;
        if (res.statusCode >= 200 && res.statusCode < 300) {
          console.log(`[WebhookDispatcher:Success] Delivered ${payload.event} (${payload.call_id}) to ${targetUrl} [HTTP ${res.statusCode}] in ${Date.now() - startTime}ms`);
          return {
            success: true,
            attempts,
            status_code: res.statusCode,
            duration_ms: Date.now() - startTime,
          };
        } else {
          lastError = `HTTP ${res.statusCode}`;
        }
      } catch (err: any) {
        lastError = err.message || "Connection failed";
      }

      // If more attempts remain, sleep briefly with backoff
      if (attempts <= this.maxRetries) {
        await new Promise((r) => setTimeout(r, 200 * Math.pow(2, attempts - 1)));
      }
    }

    console.warn(`[WebhookDispatcher:Failed] Failed delivering ${payload.event} (${payload.call_id}) after ${attempts} attempts: ${lastError}`);
    return {
      success: false,
      attempts,
      status_code: statusCode,
      error: lastError,
      duration_ms: Date.now() - startTime,
    };
  }

  private executeSinglePost(urlStr: string, bodyJson: string): Promise<{ statusCode: number; body: string }> {
    return new Promise((resolve, reject) => {
      const parsed = new URL(urlStr);
      const isHttps = parsed.protocol === "https:";
      const client = isHttps ? https : http;

      const req = client.request(
        {
          hostname: parsed.hostname,
          port: parsed.port || (isHttps ? 443 : 80),
          path: parsed.pathname + parsed.search,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(bodyJson),
            "User-Agent": "VoiceShield-AI-Webhook-Dispatcher/1.0",
            "X-VoiceShield-Event": "risk_alert",
          },
          timeout: this.timeoutMs,
        },
        (res) => {
          let resBody = "";
          res.setEncoding("utf-8");
          res.on("data", (chunk) => (resBody += chunk));
          res.on("end", () => {
            resolve({ statusCode: res.statusCode || 0, body: resBody });
          });
        }
      );

      req.on("error", (err) => reject(err));
      req.on("timeout", () => {
        req.destroy();
        reject(new Error(`Webhook request timed out after ${this.timeoutMs}ms`));
      });

      req.write(bodyJson);
      req.end();
    });
  }
}

// Export singleton instance
export const notificationDispatcher = new NotificationDispatcher();
