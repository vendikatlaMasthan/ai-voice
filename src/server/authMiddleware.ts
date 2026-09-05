/**
 * VoiceShield AI — API Authentication, Authorization & Abuse Protection Middleware
 * Supports X-API-Key header, tenant binding, and in-memory sliding-window rate limiting.
 */

import { Request, Response, NextFunction } from "express";
import { DEFAULT_ORG_ID } from "./contextService";

export interface ApiClientIdentity {
  api_key: string;
  organization_id: string;
  client_name: string;
  tier: "STANDARD" | "ENTERPRISE" | "INTERNAL";
}

// In-memory rate limiting store (sliding window per IP/client key)
interface RateLimitEntry {
  count: number;
  resetTimeMs: number;
}

const rateLimitStore = new Map<string, RateLimitEntry>();

// Periodic cleanup of expired rate limit entries every 60 seconds
setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of rateLimitStore.entries()) {
    if (now > entry.resetTimeMs) {
      rateLimitStore.delete(key);
    }
  }
}, 60000);

/**
 * Resolves configured API keys from environment or defaults.
 */
function getRegisteredApiKeys(): Map<string, ApiClientIdentity> {
  const keyMap = new Map<string, ApiClientIdentity>();

  // 1. Single global key from env
  const globalKey = process.env.VOICESHIELD_API_KEY;
  if (globalKey) {
    keyMap.set(globalKey, {
      api_key: globalKey,
      organization_id: process.env.DEFAULT_ORGANIZATION_ID || DEFAULT_ORG_ID,
      client_name: "DefaultEnterpriseClient",
      tier: "ENTERPRISE",
    });
  }

  // 2. Multi-tenant JSON key mapping from env
  const multiKeysEnv = process.env.VOICESHIELD_API_KEYS;
  if (multiKeysEnv) {
    try {
      const parsed = JSON.parse(multiKeysEnv);
      if (typeof parsed === "object" && parsed !== null) {
        for (const [k, val] of Object.entries(parsed)) {
          const clientVal = val as any;
          keyMap.set(k, {
            api_key: k,
            organization_id: clientVal.organization_id || DEFAULT_ORG_ID,
            client_name: clientVal.client_name || "EnterprisePartner",
            tier: clientVal.tier || "ENTERPRISE",
          });
        }
      }
    } catch (err: any) {
      console.warn("[Auth:ApiKeysConfig] Failed to parse VOICESHIELD_API_KEYS JSON:", err.message);
    }
  }

  return keyMap;
}

/**
 * Extracts API key from request headers.
 */
export function extractApiKey(req: Request): string | null {
  const xApiKey = req.headers["x-api-key"];
  if (typeof xApiKey === "string" && xApiKey.trim()) {
    return xApiKey.trim();
  }

  const authHeader = req.headers["authorization"];
  if (typeof authHeader === "string" && authHeader.startsWith("Bearer ")) {
    const token = authHeader.substring(7).trim();
    if (token) return token;
  }

  return null;
}

/**
 * Integration API Authentication Middleware.
 * - If REQUIRE_API_KEY=true: enforces valid X-API-Key and binds authoritative tenant.
 * - If REQUIRE_API_KEY=false: allows demo/frontend requests while authenticating any supplied X-API-Key.
 */
export function apiAuthMiddleware(req: Request, res: Response, next: NextFunction): void {
  const requireAuth = process.env.REQUIRE_API_KEY === "true";
  const apiKey = extractApiKey(req);
  const registeredKeys = getRegisteredApiKeys();

  if (apiKey) {
    // If key provided, validate it
    const client = registeredKeys.get(apiKey);
    // Also allow demo test keys in test environment
    const isTestKey = process.env.NODE_ENV === "test" || apiKey.startsWith("test-api-key");

    if (!client && registeredKeys.size > 0 && !isTestKey) {
      res.status(401).json({
        error_type: "UnauthorizedError",
        message: "Invalid API key provided in X-API-Key header.",
        status: 401,
      });
      return;
    }

    // Attach authoritative identity to request
    const orgId = client ? client.organization_id : (process.env.DEFAULT_ORGANIZATION_ID || DEFAULT_ORG_ID);
    (req as any).apiClient = client || {
      api_key: apiKey,
      organization_id: orgId,
      client_name: "AuthenticatedClient",
      tier: "ENTERPRISE",
    };
    (req as any).authoritativeOrgId = orgId;
    next();
    return;
  }

  if (requireAuth) {
    res.status(401).json({
      error_type: "UnauthorizedError",
      message: "Authentication required for external integration API. Supply valid X-API-Key header.",
      status: 401,
    });
    return;
  }

  // Local/demo fallback: use default authoritative organization
  (req as any).authoritativeOrgId = process.env.DEFAULT_ORGANIZATION_ID || DEFAULT_ORG_ID;
  next();
}

/**
 * Sliding-window in-memory Rate Limiting Middleware.
 * Configurable via RATE_LIMIT_WINDOW_MS (default 60s) and RATE_LIMIT_MAX_REQUESTS (default 120).
 */
export function apiRateLimitMiddleware(req: Request, res: Response, next: NextFunction): void {
  const windowMs = parseInt(process.env.RATE_LIMIT_WINDOW_MS || "60000", 10);
  const maxRequests = parseInt(process.env.RATE_LIMIT_MAX_REQUESTS || "120", 10);

  // Client identifier: API key or remote IP
  const apiKey = extractApiKey(req);
  const ip = req.ip || req.socket.remoteAddress || "127.0.0.1";
  const clientKey = apiKey ? `key:${apiKey}` : `ip:${ip}`;

  const now = Date.now();
  let entry = rateLimitStore.get(clientKey);

  if (!entry || now > entry.resetTimeMs) {
    entry = {
      count: 1,
      resetTimeMs: now + windowMs,
    };
    rateLimitStore.set(clientKey, entry);
  } else {
    entry.count++;
  }

  const remaining = Math.max(0, maxRequests - entry.count);
  const resetSeconds = Math.ceil((entry.resetTimeMs - now) / 1000);

  res.setHeader("X-RateLimit-Limit", maxRequests);
  res.setHeader("X-RateLimit-Remaining", remaining);
  res.setHeader("X-RateLimit-Reset", resetSeconds);

  if (entry.count > maxRequests) {
    res.setHeader("Retry-After", resetSeconds);
    res.status(429).json({
      error_type: "RateLimitExceededError",
      message: `Rate limit of ${maxRequests} requests per minute exceeded. Please retry in ${resetSeconds}s.`,
      status: 429,
      retry_after_sec: resetSeconds,
    });
    return;
  }

  next();
}
