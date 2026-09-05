/**
 * TypeScript Test Suite for Data Retention & Automated Compliance Cleanup Service.
 * Validates:
 * 1. Default retention period is 90 days (configurable via DATA_RETENTION_DAYS).
 * 2. Expired resolved/completed records exceeding retention window are purged.
 * 3. Non-expired records remain intact.
 * 4. Active/in-progress/held security records ('HELD', 'PENDING', 'IN_PROGRESS')
 *    are strictly EXEMPT from deletion to preserve ongoing investigation state.
 * 5. Tenant isolation during purge (scoped by organization_id).
 * 6. Repeated purges are safe and idempotent.
 */

import { DataRetentionService } from "../src/server/retentionService";

async function runDataRetentionTests() {
  console.log("[DataRetentionTest] Starting validation suite...");

  // Test 1: Configuration & Defaults
  const retentionService = new DataRetentionService(null);
  const policy = retentionService.getRetentionPolicy();
  if (policy.retentionDays !== 90) {
    throw new Error(`Expected default retention of 90 days, got ${policy.retentionDays}`);
  }
  if (!policy.exemptStatuses.includes("HELD") || !policy.exemptStatuses.includes("PENDING")) {
    throw new Error("Active/Held investigation statuses must be exempt from purge.");
  }
  console.log("  ✓ test_1_default_retention_policy passed");

  // Test 2: In-Memory Expired Records Purge
  retentionService.setRetentionDays(30); // 30 days retention
  const now = Date.now();
  const dayMs = 86400 * 1000;

  // Add 1 expired completed event (45 days old)
  retentionService.registerInMemoryEvent({
    id: "EVT-EXPIRED-01",
    organization_id: "ORG-A",
    status: "RESOLVED",
    created_at: now - 45 * dayMs,
  });

  // Add 1 non-expired event (10 days old)
  retentionService.registerInMemoryEvent({
    id: "EVT-RECENT-01",
    organization_id: "ORG-A",
    status: "RESOLVED",
    created_at: now - 10 * dayMs,
  });

  // Add 1 expired but HELD investigation (50 days old)
  retentionService.registerInMemoryEvent({
    id: "EVT-HELD-01",
    organization_id: "ORG-A",
    status: "HELD",
    created_at: now - 50 * dayMs,
  });

  if (retentionService.getInMemoryEventCount() !== 3) {
    throw new Error("Failed to register in-memory test events");
  }

  const purgeResult = await retentionService.purgeExpiredRecords();
  if (purgeResult.status !== "SUCCESS") {
    throw new Error(`Purge returned status ${purgeResult.status}`);
  }
  if (purgeResult.purgedRecordsCount !== 1) {
    throw new Error(`Expected 1 expired record purged, got ${purgeResult.purgedRecordsCount}`);
  }
  if (retentionService.getInMemoryEventCount() !== 2) {
    throw new Error(`Expected 2 records remaining (1 recent + 1 HELD exempt), got ${retentionService.getInMemoryEventCount()}`);
  }
  console.log("  ✓ test_2_purge_expired_completed_records passed");

  // Test 3: Tenant-Scoped Purge
  retentionService.registerInMemoryEvent({
    id: "EVT-ORG-B-EXPIRED",
    organization_id: "ORG-B",
    status: "COMPLETED",
    created_at: now - 60 * dayMs,
  });

  // Purge targeting only ORG-A should NOT affect ORG-B
  const tenantPurge = await retentionService.purgeExpiredRecords("ORG-A");
  if (tenantPurge.purgedRecordsCount !== 0) {
    throw new Error("Expected 0 records purged for ORG-A since no more expired records exist");
  }
  if (retentionService.getInMemoryEventCount() !== 3) {
    throw new Error("ORG-B record should remain untouched during ORG-A targeted purge");
  }
  console.log("  ✓ test_3_tenant_isolation_in_retention passed");

  // Test 4: Idempotency
  const repeatedPurge = await retentionService.purgeExpiredRecords();
  if (repeatedPurge.purgedRecordsCount !== 1) { // Purges the ORG-B expired event
    throw new Error("Expected 1 record purged for global cleanup");
  }
  const secondRepeat = await retentionService.purgeExpiredRecords();
  if (secondRepeat.purgedRecordsCount !== 0) {
    throw new Error("Repeated purge should be cleanly idempotent with 0 purged");
  }
  console.log("  ✓ test_4_idempotent_cleanup passed");

  console.log("All Data Retention & Compliance tests passed successfully!\n");
}

runDataRetentionTests().catch((err) => {
  console.error("Data Retention Test Suite failed:", err);
  process.exit(1);
});
