/**
 * VoiceShield AI — Configurable Data Retention & Automated Compliance Cleanup Service
 * Automatically purges or anonymizes historical incident metadata, audit trails, and logs
 * that exceed the configured organization retention period (default: 90 days).
 *
 * CRITICAL COMPLIANCE RULES:
 * 1. Raw audio is ZERO-RETENTION and never stored anywhere.
 * 2. Active, pending, or held transaction security records ('HELD', 'PENDING', 'IN_PROGRESS')
 *    are NEVER deleted by retention cleanup to prevent tampering with active investigations.
 * 3. All operations are strictly tenant-isolated.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

export interface RetentionPolicy {
  retentionDays: number;
  autoPurgeEnabled: boolean;
  exemptStatuses: string[];
}

export interface PurgeResult {
  organizationId?: string;
  purgedRecordsCount: number;
  cutoffTimestamp: string;
  retentionDays: number;
  status: "SUCCESS" | "NOOP" | "FAILED";
  error?: string;
}

export class DataRetentionService {
  private retentionDays: number;
  private autoPurgeEnabled: boolean;
  private exemptStatuses: Set<string>;
  private supabase: SupabaseClient | null;
  private intervalTimer: NodeJS.Timeout | null = null;

  // In-memory store retention tracker for non-database execution
  private inMemoryEvents: Array<{ id: string; organization_id: string; status?: string; created_at: number }> = [];

  constructor(supabaseClient: SupabaseClient | null = null) {
    this.supabase = supabaseClient;
    const envDays = parseInt(process.env.DATA_RETENTION_DAYS || "90", 10);
    this.retentionDays = isNaN(envDays) || envDays <= 0 ? 90 : envDays;
    this.autoPurgeEnabled = process.env.ENABLE_DATA_RETENTION_AUTO_PURGE !== "false";
    this.exemptStatuses = new Set(["HELD", "PENDING", "IN_PROGRESS", "OPEN", "ACTIVE"]);
  }

  public setSupabaseClient(client: SupabaseClient | null) {
    this.supabase = client;
  }

  public getRetentionPolicy(): RetentionPolicy {
    return {
      retentionDays: this.retentionDays,
      autoPurgeEnabled: this.autoPurgeEnabled,
      exemptStatuses: Array.from(this.exemptStatuses),
    };
  }

  public setRetentionDays(days: number): void {
    if (days > 0) {
      this.retentionDays = days;
    }
  }

  public registerInMemoryEvent(event: { id: string; organization_id: string; status?: string; created_at?: number }) {
    this.inMemoryEvents.push({
      id: event.id,
      organization_id: event.organization_id,
      status: event.status || "COMPLETED",
      created_at: event.created_at || Date.now(),
    });
  }

  public getInMemoryEventCount(): number {
    return this.inMemoryEvents.length;
  }

  /**
   * Executes a tenant-aware, idempotent purge of expired records.
   */
  public async purgeExpiredRecords(targetOrgId?: string): Promise<PurgeResult> {
    const cutoffDate = new Date(Date.now() - this.retentionDays * 86400 * 1000);
    const cutoffIso = cutoffDate.toISOString();
    const cutoffEpoch = cutoffDate.getTime();
    let purgedCount = 0;

    try {
      // 1. Purge from In-Memory registry
      const initialMemCount = this.inMemoryEvents.length;
      this.inMemoryEvents = this.inMemoryEvents.filter((ev) => {
        // If belonging to different org and targetOrgId specified, retain
        if (targetOrgId && ev.organization_id !== targetOrgId) return true;

        // Exempt active / held investigations
        if (ev.status && this.exemptStatuses.has(ev.status.toUpperCase())) return true;

        // Keep if newer than cutoff
        return ev.created_at >= cutoffEpoch;
      });
      purgedCount += initialMemCount - this.inMemoryEvents.length;

      // 2. Purge from Supabase if connected
      if (this.supabase) {
        // Purge audit_logs older than cutoff
        let auditQuery = this.supabase
          .from("audit_logs")
          .delete({ count: "exact" })
          .lt("created_at", cutoffIso);

        if (targetOrgId) {
          auditQuery = auditQuery.eq("organization_id", targetOrgId);
        }

        const { count: auditPurged, error: auditErr } = await auditQuery;
        if (!auditErr && auditPurged) {
          purgedCount += auditPurged;
        }

        // Purge completed/resolved alerts older than cutoff (exempt active statuses)
        let alertsQuery = this.supabase
          .from("alerts")
          .delete({ count: "exact" })
          .lt("created_at", cutoffIso)
          .not("status", "in", '("HELD","PENDING","IN_PROGRESS","ACTIVE")');

        if (targetOrgId) {
          alertsQuery = alertsQuery.eq("organization_id", targetOrgId);
        }

        const { count: alertsPurged, error: alertsErr } = await alertsQuery;
        if (!alertsErr && alertsPurged) {
          purgedCount += alertsPurged;
        }
      }

      return {
        organizationId: targetOrgId,
        purgedRecordsCount: purgedCount,
        cutoffTimestamp: cutoffIso,
        retentionDays: this.retentionDays,
        status: "SUCCESS",
      };
    } catch (err: any) {
      return {
        organizationId: targetOrgId,
        purgedRecordsCount: purgedCount,
        cutoffTimestamp: cutoffIso,
        retentionDays: this.retentionDays,
        status: "FAILED",
        error: err.message,
      };
    }
  }

  /**
   * Starts periodic automated background cleanup job (runs every 24 hours).
   */
  public startAutomatedCleanup(intervalMs: number = 86400000): void {
    if (this.intervalTimer) {
      clearInterval(this.intervalTimer);
    }
    if (!this.autoPurgeEnabled) {
      console.log("[RetentionService] Automated retention purge is disabled via environment.");
      return;
    }

    console.log(
      `[RetentionService] Scheduled automated data retention cleanup (Retention: ${this.retentionDays} days, Interval: ${intervalMs / 1000}s)`
    );

    // Run initial cleanup asynchronously on startup
    this.purgeExpiredRecords().catch((err) => {
      console.warn("[RetentionService] Startup retention cleanup error:", err);
    });

    this.intervalTimer = setInterval(() => {
      this.purgeExpiredRecords().catch((err) => {
        console.warn("[RetentionService] Periodic retention cleanup error:", err);
      });
    }, intervalMs);
  }

  public stopAutomatedCleanup(): void {
    if (this.intervalTimer) {
      clearInterval(this.intervalTimer);
      this.intervalTimer = null;
    }
  }
}
