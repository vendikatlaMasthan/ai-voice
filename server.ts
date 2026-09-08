import "dotenv/config";
import express from "express";
import http from "http";
import path from "path";
import fs from "fs";
import { ChildProcess, spawn } from "child_process";
import multer from "multer";
import os from "os";
import { createServer as createViteServer } from "vite";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { WebSocketServer, WebSocket, RawData } from "ws";
import { ContextRetrievalService, EnrichedCallContext, DEFAULT_ORG_ID } from "./src/server/contextService";
import { apiAuthMiddleware, apiRateLimitMiddleware } from "./src/server/authMiddleware";
import { notificationDispatcher } from "./src/server/notificationDispatcher";
import cors from "cors";
import { maskPhoneNumber, sanitizeAuditLogPayload } from "./src/server/piiService";
import { DataRetentionService } from "./src/server/retentionService";

const app = express();
const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 3000;

// Enable CORS for GitHub Pages frontend and local development
const allowedOrigins = [
  "https://vendikatlamasthan.github.io",
  "http://localhost:5173",
  "http://localhost:3000",
  "http://127.0.0.1:5173",
  "http://127.0.0.1:3000",
];

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin) return callback(null, true);
      if (
        allowedOrigins.includes(origin) ||
        origin.endsWith(".github.io") ||
        process.env.NODE_ENV !== "production"
      ) {
        return callback(null, true);
      }
      return callback(null, true);
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization", "x-api-key", "x-organization-id"],
  })
);

// Setup JSON & Form parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Setup multer for temporary audio file storage
const upload = multer({
  dest: path.join(os.tmpdir(), "voiceshield_uploads"),
  limits: { fileSize: 100 * 1024 * 1024 }, // 100 MB limit for audio and video
});

// Helper to resolve the correct Python executable (virtualenv or system python)
function getPythonCommand(): string {
  if (process.env.PYTHON_PATH && fs.existsSync(process.env.PYTHON_PATH)) {
    return process.env.PYTHON_PATH;
  }
  const venvPaths = [
    path.join(process.cwd(), "venv", "Scripts", "python.exe"),
    path.join(process.cwd(), ".venv", "Scripts", "python.exe"),
    path.join(process.cwd(), ".venv", "bin", "python3"),
    path.join(process.cwd(), ".venv", "bin", "python"),
    path.join(process.cwd(), "venv", "bin", "python3"),
    path.join(process.cwd(), "venv", "bin", "python"),
  ];
  for (const p of venvPaths) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  return process.platform === "win32" ? "python" : "python3";
}

// ----------------------------------------------------
// PERSISTENT PYTHON INFERENCE DAEMON MANAGER
// ----------------------------------------------------
class PythonInferenceDaemonManager {
  private proc: ChildProcess | null = null;
  private stdoutBuffer: string = "";
  private isReady: boolean = false;
  private pendingRequests: Map<
    string,
    {
      resolve: (value: { status: number; data: any }) => void;
      reject: (reason: any) => void;
      timer: NodeJS.Timeout;
    }
  > = new Map();
  private initPromise: Promise<void> | null = null;
  private reqSequence: number = 0;

  constructor() {
    this.ensureStarted();
    this.setupProcessExitHandlers();
  }

  private setupProcessExitHandlers(): void {
    const cleanup = () => {
      if (this.proc) {
        try {
          this.proc.kill("SIGTERM");
        } catch (e) {
          // ignore
        }
        this.proc = null;
      }
    };
    process.on("exit", cleanup);
    process.on("SIGINT", cleanup);
    process.on("SIGTERM", cleanup);
  }

  private ensureStarted(): Promise<void> {
    if (this.proc && this.isReady) {
      return Promise.resolve();
    }
    if (this.initPromise) {
      return this.initPromise;
    }

    this.initPromise = new Promise((resolve) => {
      const pythonCmd = getPythonCommand();
      const scriptPath = path.join(process.cwd(), "scripts", "run_pipeline.py");

      let hasResolved = false;
      const startupTimer = setTimeout(() => {
        if (!this.isReady && !hasResolved) {
          console.warn("[PythonDaemonManager] Daemon startup timed out after 10s. Allowing requests to proceed via CLI fallback.");
          hasResolved = true;
          resolve();
        }
      }, 10000);

      console.log(`[PythonDaemonManager] Starting persistent Python daemon with ${pythonCmd}...`);
      const child = spawn(pythonCmd, [scriptPath, "daemon"]);
      this.proc = child;
      this.stdoutBuffer = "";
      this.isReady = false;

      child.stdout.on("data", (chunk: Buffer) => {
        this.stdoutBuffer += chunk.toString("utf-8");
        this.flushStdoutBuffer(() => {
          clearTimeout(startupTimer);
          if (!hasResolved) {
            hasResolved = true;
            resolve();
          }
        });
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8").trim();
        if (text) {
          console.log(`[PythonDaemon:stderr] ${text}`);
        }
      });

      child.on("error", (err) => {
        clearTimeout(startupTimer);
        console.error(`[PythonDaemonManager] Process error:`, err);
        this.handleProcessCrash(err);
      });

      child.on("exit", (code, signal) => {
        clearTimeout(startupTimer);
        console.warn(`[PythonDaemonManager] Process exited with code ${code}, signal ${signal}`);
        this.handleProcessCrash(new Error(`Daemon exited with code ${code}`));
      });
    });

    return this.initPromise;
  }

  private flushStdoutBuffer(readyCallback?: () => void): void {
    let newlineIdx: number;
    while ((newlineIdx = this.stdoutBuffer.indexOf("\n")) !== -1) {
      const line = this.stdoutBuffer.substring(0, newlineIdx).trim();
      this.stdoutBuffer = this.stdoutBuffer.substring(newlineIdx + 1);

      if (!line) continue;

      try {
        const parsed = JSON.parse(line);

        // Check for startup ready sentinel
        if (parsed.status === "READY" && !this.isReady) {
          console.log(`[PythonDaemonManager] Persistent inference models ready.`);
          this.isReady = true;
          this.initPromise = null;
          if (readyCallback) readyCallback();
          continue;
        }

        // Match with pending request ID
        if (parsed.id && this.pendingRequests.has(parsed.id)) {
          const pending = this.pendingRequests.get(parsed.id)!;
          clearTimeout(pending.timer);
          this.pendingRequests.delete(parsed.id);

          pending.resolve({
            status: parsed.status || 200,
            data: parsed.data !== undefined ? parsed.data : parsed,
          });
        }
      } catch (e) {
        console.warn(`[PythonDaemonManager] Non-JSON or unparseable line: ${line}`);
      }
    }
  }

  private handleProcessCrash(err: Error): void {
    this.proc = null;
    this.isReady = false;
    this.initPromise = null;

    // Reject all pending requests
    for (const [id, req] of this.pendingRequests.entries()) {
      clearTimeout(req.timer);
      req.resolve({
        status: 500,
        data: {
          error_type: "DaemonCrashError",
          message: `Persistent inference worker crashed: ${err.message}`,
        },
      });
    }
    this.pendingRequests.clear();
  }

  public get isDaemonReady(): boolean {
    return this.isReady;
  }

  public waitUntilReady(): Promise<void> {
    return this.ensureStarted();
  }

  public async request(command: string, args: Record<string, any> = {}): Promise<{ status: number; data: any }> {
    try {
      await this.ensureStarted();
    } catch (e) {
      console.warn(`[PythonDaemonManager] Failed to start persistent daemon, falling back to CLI runner...`);
      return this.runCliFallback(command, args);
    }

    if (!this.proc || !this.proc.stdin || !this.proc.stdin.writable) {
      return this.runCliFallback(command, args);
    }

    const reqId = `req_${Date.now()}_${++this.reqSequence}`;
    const payload = JSON.stringify({ id: reqId, command, args }) + "\n";

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pendingRequests.has(reqId)) {
          this.pendingRequests.delete(reqId);
          resolve({
            status: 504,
            data: {
              error_type: "InferenceTimeoutError",
              message: "ML inference request timed out.",
            },
          });
        }
      }, 14000); // 14 seconds maximum inference timeout

      this.pendingRequests.set(reqId, { resolve, reject, timer });

      try {
        this.proc!.stdin!.write(payload, "utf-8", (err) => {
          if (err) {
            clearTimeout(timer);
            this.pendingRequests.delete(reqId);
            resolve({
              status: 500,
              data: {
                error_type: "DaemonWriteError",
                message: `Failed to write request to daemon: ${err.message}`,
              },
            });
          }
        });
      } catch (err: any) {
        clearTimeout(timer);
        this.pendingRequests.delete(reqId);
        resolve({
          status: 500,
          data: {
            error_type: "DaemonWriteError",
            message: `Failed to send request: ${err.message}`,
          },
        });
      }
    });
  }

  // Safety fallback to one-shot CLI runner if daemon is not available
  private runCliFallback(command: string, args: Record<string, any>): Promise<{ status: number; data: any }> {
    return new Promise((resolve) => {
      const pythonCmd = getPythonCommand();
      const scriptPath = path.join(process.cwd(), "scripts", "run_pipeline.py");
      const cliArgs = [scriptPath, command];

      for (const [k, v] of Object.entries(args)) {
        if (v !== undefined && v !== null) {
          const flag = `--${k.replace(/_/g, "-")}`;
          cliArgs.push(flag, String(v));
        }
      }

      const proc = spawn(pythonCmd, cliArgs);
      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (c) => (stdout += c.toString()));
      proc.stderr.on("data", (c) => (stderr += c.toString()));

      proc.on("close", (code) => {
        const lines = stdout.trim().split("\n");
        let jsonStr = "";
        for (let i = lines.length - 1; i >= 0; i--) {
          const line = lines[i].trim();
          if (line.startsWith("{") && line.endsWith("}")) {
            jsonStr = line;
            break;
          }
        }
        if (code === 0 && jsonStr) {
          try {
            return resolve({ status: 200, data: JSON.parse(jsonStr) });
          } catch (e) {
            // fallthrough
          }
        }
        return resolve({
          status: code === 0 ? 200 : 500,
          data: { error_type: "CliFallbackError", message: stderr || stdout || "Execution failed." },
        });
      });

      proc.on("error", (err) => {
        resolve({
          status: 500,
          data: { error_type: "SpawnError", message: err.message },
        });
      });
    });
  }
}

// Instantiate daemon manager singleton
const daemonManager = new PythonInferenceDaemonManager();

// ----------------------------------------------------
// SUPABASE CLIENT & PERSISTENCE (Server-Side Only)
// ----------------------------------------------------
function sanitizeSupabaseUrl(rawUrl: string): string {
  if (!rawUrl) return "";
  let clean = rawUrl.trim();
  // Strip accidental trailing REST / Auth API path segments and trailing slashes
  clean = clean.replace(/\/rest\/v1\/?$/i, "");
  clean = clean.replace(/\/auth\/v1\/?$/i, "");
  clean = clean.replace(/\/storage\/v1\/?$/i, "");
  clean = clean.replace(/\/+$/, "");
  return clean;
}

const SUPABASE_URL = sanitizeSupabaseUrl(process.env.SUPABASE_URL || "");
const SUPABASE_KEY =
  process.env.SUPABASE_SERVICE_ROLE_KEY ||
  process.env.SUPABASE_KEY ||
  process.env.SUPABASE_ANON_KEY ||
  "";

let supabase: SupabaseClient | null = null;
if (SUPABASE_URL && SUPABASE_KEY) {
  try {
    supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    console.log(`[Supabase] Initialized backend database client successfully with endpoint: ${SUPABASE_URL}`);
  } catch (err: any) {
    console.warn("[Supabase] Failed to initialize client:", err.message);
  }
} else {
  console.log("[Supabase] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured. Telemetry persistence disabled.");
}

// Instantiate ContextRetrievalService singleton
const contextService = new ContextRetrievalService(supabase);

// Instantiate DataRetentionService singleton for automated compliance cleanup
const dataRetentionService = new DataRetentionService(supabase);
dataRetentionService.startAutomatedCleanup();

async function persistAnalysisToSupabase(
  resultData: any,
  params: Record<string, any>,
  reqBody: Record<string, any>,
  enrichedContext?: EnrichedCallContext | null
): Promise<void> {
  if (!supabase || !resultData || !resultData.call_id) {
    return;
  }

  try {
    const orgId = enrichedContext?.organization_id || contextService.resolveAuthoritativeOrganizationId();

    // 1. Resolve textual speaker_id (e.g. SPK-001) to speakers.id (UUID)
    let speakerDbUuid: string | null = null;
    const requestedSpeakerId = params.speaker_id || reqBody.speaker_id;
    if (requestedSpeakerId) {
      const { data: speakerRow, error: spkErr } = await supabase
        .from("speakers")
        .select("id")
        .eq("speaker_id", String(requestedSpeakerId))
        .maybeSingle();

      if (!spkErr && speakerRow?.id) {
        speakerDbUuid = speakerRow.id;
      }
    }

    // 2. Resolve contact if caller_id or contact_id matches
    let contactDbUuid: string | null = enrichedContext?.contact_id || null;
    if (!contactDbUuid && reqBody.contact_id) {
      contactDbUuid = String(reqBody.contact_id);
    }

    const durationSec =
      resultData.audio_metadata?.processed_duration_sec ??
      resultData.audio_metadata?.original_duration_sec ??
      null;
    const nowIso = new Date().toISOString();
    const startedAtIso = durationSec
      ? new Date(Date.now() - Math.round(durationSec * 1000)).toISOString()
      : nowIso;

    // 3. Insert into calls table
    const { data: callRow, error: callErr } = await supabase
      .from("calls")
      .insert({
        call_id: resultData.call_id,
        organization_id: orgId,
        speaker_id: speakerDbUuid,
        contact_id: contactDbUuid,
        caller_id: reqBody.caller_id ? String(reqBody.caller_id) : null,
        claimed_role: reqBody.claimed_role ? String(reqBody.claimed_role) : null,
        started_at: startedAtIso,
        ended_at: nowIso,
        duration_seconds: durationSec,
      })
      .select("id")
      .single();

    if (callErr) {
      console.warn("[Supabase:calls] Failed to insert call record:", callErr.message);
      return;
    }

    if (!callRow?.id) {
      return;
    }

    // 4. Map & sanitize risk_level to conform to CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH'))
    let sanitizedRiskLevel: string | null = null;
    const rawRiskLevel = String(resultData.risk_level || "").toUpperCase();
    if (rawRiskLevel === "LOW" || rawRiskLevel === "MEDIUM" || rawRiskLevel === "HIGH") {
      sanitizedRiskLevel = rawRiskLevel;
    } else if (rawRiskLevel === "CRITICAL") {
      sanitizedRiskLevel = "HIGH";
    }

    // 5. Convert acoustic_anomaly to boolean (Schema is BOOLEAN NOT NULL)
    let acousticAnomalyBool: boolean = false;
    if (params.acoustic_anomaly !== undefined && params.acoustic_anomaly !== null) {
      acousticAnomalyBool =
        typeof params.acoustic_anomaly === "boolean"
          ? params.acoustic_anomaly
          : parseFloat(params.acoustic_anomaly) > 0;
    } else if (reqBody.acoustic_anomaly_override !== undefined && reqBody.acoustic_anomaly_override !== null) {
      acousticAnomalyBool = parseFloat(reqBody.acoustic_anomaly_override) > 0;
    }

    // 6. Insert into risk_events table
    const { error: riskErr } = await supabase.from("risk_events").insert({
      call_id: callRow.id,
      organization_id: orgId,
      risk_score: typeof resultData.risk_score === "number" ? resultData.risk_score : null,
      risk_level: sanitizedRiskLevel,
      recommended_action: resultData.recommended_action ? String(resultData.recommended_action) : null,
      deepfake_prediction: resultData.deepfake_detection?.prediction
        ? String(resultData.deepfake_detection.prediction)
        : null,
      fake_probability:
        typeof resultData.deepfake_detection?.fake_probability === "number"
          ? resultData.deepfake_detection.fake_probability
          : null,
      speaker_similarity:
        typeof resultData.speaker_verification?.similarity_score === "number"
          ? resultData.speaker_verification.similarity_score
          : null,
      speaker_match:
        typeof resultData.speaker_verification?.is_match === "boolean"
          ? resultData.speaker_verification.is_match
          : null,
      speaker_verification_status: resultData.speaker_verification?.status
        ? String(resultData.speaker_verification.status)
        : null,
      speaker_mismatch_flag:
        typeof resultData.speaker_verification?.speaker_mismatch_flag === "number"
          ? resultData.speaker_verification.speaker_mismatch_flag
          : (resultData.risk_signals?.speaker_mismatch ?? 0),
      acoustic_anomaly: acousticAnomalyBool,
      caller_recognized: enrichedContext ? enrichedContext.is_caller_recognized : (typeof params.is_caller_recognized === "boolean" ? params.is_caller_recognized : null),
      previously_flagged: enrichedContext ? enrichedContext.is_previously_flagged : (typeof params.is_previously_flagged === "boolean" ? params.is_previously_flagged : null),
      transaction_amount: typeof params.requested_amount === "number" ? params.requested_amount : null,
      normal_transaction_amount: typeof params.normal_amount === "number" ? params.normal_amount : null,
      is_urgent: typeof params.is_urgent === "boolean" ? params.is_urgent : null,
      urgency_reason: params.urgency_reason ? String(params.urgency_reason) : null,
      model_id: resultData.deepfake_detection?.model_id ? String(resultData.deepfake_detection.model_id) : null,
      inference_time_ms:
        typeof resultData.deepfake_detection?.inference_time_ms === "number"
          ? resultData.deepfake_detection.inference_time_ms
          : null,
    });

    if (riskErr) {
      console.warn("[Supabase:risk_events] Failed to insert risk event record:", riskErr.message);
    }

    // 7. Insert into transactions table if transaction was requested
    if (params.requested_amount || reqBody.requested_transaction_amount) {
      const amount = Number(params.requested_amount || reqBody.requested_transaction_amount);
      const isAutoHold = enrichedContext?.policy?.transaction_auto_hold_amount
        ? amount >= enrichedContext.policy.transaction_auto_hold_amount
        : false;
      const isHighRisk = sanitizedRiskLevel === "HIGH";

      let status = "PENDING";
      let holdReason: string | null = null;
      if (isHighRisk) {
        status = "HELD";
        holdReason = "Deepfake and high fraud risk detected during voice authentication.";
      } else if (isAutoHold) {
        status = "HELD";
        holdReason = `Requested amount (${amount}) exceeds enterprise policy threshold (${enrichedContext?.policy?.transaction_auto_hold_amount}).`;
      }

      await supabase.from("transactions").insert({
        organization_id: orgId,
        call_id: callRow.id,
        contact_id: contactDbUuid,
        amount: amount,
        normal_historical_amount: params.normal_amount ? Number(params.normal_amount) : null,
        is_urgent: typeof params.is_urgent === "boolean" ? params.is_urgent : false,
        urgency_reason: params.urgency_reason ? String(params.urgency_reason) : null,
        risk_score: typeof resultData.risk_score === "number" ? resultData.risk_score : null,
        status: status,
        hold_reason: holdReason,
      });
    }

    // 8. Record threat intelligence alerts and fraud indicators if high risk detected
    if (enrichedContext) {
      await contextService.recordThreatIntelligenceIfHighRisk(callRow.id, resultData, enrichedContext);
    }
  } catch (err: any) {
    console.warn("[Supabase:Catch] Error persisting analysis metadata:", err.message);
  }
}

// ----------------------------------------------------
// API ROUTES (FastAPI Parity Contracts)
// ----------------------------------------------------

// 1. Health check: /health and /api/health
const handleHealth = async (_req: express.Request, res: express.Response) => {
  const result = await daemonManager.request("health");
  res.status(result.status).json(result.data);
};
app.get("/health", handleHealth);
app.get("/api/health", handleHealth);



// 3. Samples catalog for quick browser testing
app.get("/api/samples", (_req, res) => {
  const samplesDir = path.join(process.cwd(), "data", "samples");
  if (!fs.existsSync(samplesDir)) {
    return res.json({ samples: [] });
  }

  const files = fs.readdirSync(samplesDir);
  const samples = files
    .filter((f) => f.endsWith(".wav") || f.endsWith(".mp3") || f.endsWith(".flac"))
    .map((f) => ({
      filename: f,
      url: `/data/samples/${f}`,
      description:
        f === "valid_speech.wav"
          ? "Standard 3.0s Clean Speech Sample (Expected: REAL / Low Risk)"
          : f === "real_01.wav"
          ? "Harmonic Human Speech Sample (Expected: REAL / Low Risk)"
          : f === "fake_01.wav"
          ? "High-Frequency Synthetic Voice Clone Sample (Expected: FAKE / High Risk)"
          : f === "too_short.wav"
          ? "Short 0.2s Audio Sample (Expected: AudioTooShortError)"
          : f === "silent_audio.wav"
          ? "Silent Audio Sample (Expected: AudioSilentError)"
          : f === "corrupted_file.wav"
          ? "Corrupted Header Sample (Expected: AudioCorruptError)"
          : f === "low_energy_hiss.wav"
          ? "Low Energy Background Audio"
          : f,
    }));

  res.json({ samples });
});

// Serve sample files statically
app.use("/data/samples", express.static(path.join(process.cwd(), "data", "samples")));

/**
 * Shared audio conversion step: Converts any incoming audio file
 * (WebM, MP3, M4A, FLAC, AAC, WAV, etc.) to standard 16kHz mono 16-bit PCM WAV.
 * Used identically for both Upload and Record flows.
 */
async function probeAudioDuration(filePath: string): Promise<number> {
  return new Promise((resolve) => {
    const proc = spawn("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration",
      "-of", "csv=p=0",
      filePath,
    ]);
    let stdout = "";
    proc.stdout.on("data", (c) => (stdout += c.toString()));
    proc.on("close", (code) => {
      if (code === 0 && stdout.trim()) {
        const d = parseFloat(stdout.trim());
        if (!isNaN(d) && d > 0) return resolve(d);
      }
      resolve(-1);
    });
    proc.on("error", () => resolve(-1));
  });
}

/**
 * Fast ffprobe check to detect if an uploaded media file contains an audio stream.
 */
function probeHasAudioStream(filePath: string): Promise<boolean> {
  return new Promise((resolve) => {
    const proc = spawn("ffprobe", [
      "-v", "error",
      "-select_streams", "a:0",
      "-show_entries", "stream=codec_type",
      "-of", "csv=p=0",
      filePath,
    ]);
    let stdout = "";
    proc.stdout.on("data", (c) => (stdout += c.toString()));
    proc.on("close", (code) => {
      resolve(code === 0 && stdout.trim().toLowerCase().includes("audio"));
    });
    proc.on("error", () => resolve(false));
  });
}

/**
 * Fast speech offset locator using ffmpeg silencedetect.
 * Scans leading audio up to 45s to locate where active voice begins rather than silence.
 */
function findSpeechOffset(filePath: string): Promise<number> {
  return new Promise((resolve) => {
    const proc = spawn("ffmpeg", [
      "-nostdin",
      "-v", "info",
      "-t", "45",
      "-i", filePath,
      "-af", "silencedetect=noise=-30dB:d=0.3",
      "-f", "null",
      "-",
    ]);
    let stderr = "";
    proc.stderr.on("data", (c) => (stderr += c.toString()));
    proc.on("close", () => {
      const match = stderr.match(/silence_end:\s*([0-9.]+)/);
      if (match && match[1]) {
        const offset = parseFloat(match[1]);
        if (!isNaN(offset) && offset > 0 && offset < 40) {
          return resolve(Math.max(0, offset - 0.2)); // 200ms lead-in
        }
      }
      resolve(0.0);
    });
    proc.on("error", () => resolve(0.0));
  });
}

/**
 * Standardize audio or extract audio track from video:
 * Converts/extracts to 16kHz mono 16-bit PCM WAV.
 * Automatically supports seeking to startOffset (for speech segment selection)
 * and discarding video track (-vn).
 */
function convertToStandardWav(
  inputPath: string,
  outputPath: string,
  startOffset: number = 0.0,
  duration: number = 15.0
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(inputPath)) {
      return reject(new Error(`Input file does not exist: ${inputPath}`));
    }
    const stat = fs.statSync(inputPath);
    if (stat.size === 0) {
      return reject(new Error(`Input file is empty (0 bytes): ${inputPath}`));
    }

    const args = ["-y", "-nostdin", "-v", "error"];
    if (startOffset > 0.05) {
      args.push("-ss", startOffset.toFixed(2));
    }
    args.push(
      "-i", inputPath,
      "-t", duration.toFixed(1),
      "-vn", // Discard video track when processing video uploads
      "-ar", "16000",
      "-ac", "1",
      "-c:a", "pcm_s16le",
      "-f", "wav",
      outputPath
    );

    const proc = spawn("ffmpeg", args);
    let stderr = "";

    const ffmpegTimer = setTimeout(() => {
      try {
        proc.kill("SIGKILL");
      } catch {}
      reject(new Error("Audio extraction/conversion timed out after 8 seconds."));
    }, 8000);

    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    proc.on("error", (err) => {
      clearTimeout(ffmpegTimer);
      reject(new Error(`Failed to spawn ffmpeg: ${err.message}`));
    });

    proc.on("close", (code) => {
      clearTimeout(ffmpegTimer);
      if (code === 0 && fs.existsSync(outputPath) && fs.statSync(outputPath).size > 44) {
        resolve();
      } else {
        reject(new Error(`ffmpeg conversion failed (exit code ${code}): ${stderr.trim()}`));
      }
    });
  });
}

// 4. Ingest & Analyze: /analyze and /api/analyze
const handleAnalyze = async (req: express.Request, res: express.Response) => {
  const file = req.file;
  if (!file) {
    return res.status(400).json({
      error_type: "MissingFileError",
      message: "Please select or record an audio or video file to analyze.",
    });
  }

  const rawPath = file.path;
  const originalName = file.originalname || "";
  const ext = path.extname(originalName || file.path).toLowerCase().replace(".", "");
  const mimeType = (file.mimetype || "").toLowerCase();

  const isVideo = mimeType.startsWith("video/") || ["mp4", "mov", "mkv", "webm", "avi", "3gp", "ts"].includes(ext);
  const isLive = req.body?.is_live === "true" || req.headers["x-is-live"] === "true" || originalName.startsWith("mic_") || originalName.startsWith("live_");
  const input_type: "video" | "audio" | "live" = isVideo ? "video" : (isLive ? "live" : "audio");

  // Validate video audio stream
  if (isVideo) {
    const hasAudio = await probeHasAudioStream(rawPath);
    if (!hasAudio) {
      try {
        if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);
      } catch {}
      return res.status(400).json({
        error_type: "NoAudioStreamError",
        message: "This video does not contain an audio track.",
      });
    }
  }

  // Fast probe duration (< 50ms)
  const probedDuration = await probeAudioDuration(rawPath);
  let startOffset = 0.0;
  let is_long_recording = false;
  let user_notice: string | null = null;

  if (probedDuration > 15.0) {
    is_long_recording = true;
    user_notice = "Long recording detected. A speech segment was selected for analysis.";
    startOffset = await findSpeechOffset(rawPath);
    console.log(`[handleAnalyze] Long recording detected (${probedDuration.toFixed(2)}s). Selected speech offset: ${startOffset.toFixed(2)}s`);
  }

  const tReqStart = performance.now();
  let ffmpegDurationSec = 0;

  const standardWavPath = path.join(path.dirname(rawPath), `std_${Date.now()}_${path.basename(rawPath)}.wav`);

  try {
    const executionPromise = (async () => {
      const tFfmpegStart = performance.now();
      await convertToStandardWav(rawPath, standardWavPath, startOffset, 15.0);
      ffmpegDurationSec = (performance.now() - tFfmpegStart) / 1000;
      const params: Record<string, any> = {
        file: standardWavPath,
      };
      return await daemonManager.request("analyze", params);
    })();

    const timeoutPromise = new Promise<{ status: number; data: any }>((resolve) => {
      setTimeout(() => {
        resolve({
          status: 504,
          data: {
            error_type: "AnalysisTimeoutError",
            message: "We couldn't complete the analysis in time. Please try a shorter recording or try again.",
          },
        });
      }, 15000); // 15 seconds hard backend ceiling
    });

    let result: { status: number; data: any };
    try {
      result = await Promise.race([executionPromise, timeoutPromise]);
    } catch (convErr: any) {
      console.error(`[AudioProcessingError] Technical error processing '${rawPath}':`, convErr.message);
      return res.status(400).json({
        error_type: "AudioProcessingError",
        message: isVideo
          ? "We couldn't extract the audio from this video. Please ensure it has a valid audio track."
          : "We couldn't process this audio. Please check the file format or try recording again.",
      });
    }

    if (result.status !== 200) {
      console.error(`[DaemonAnalyzeError] Technical error from inference daemon (status ${result.status}):`, result.data);
      const rawMsg = String(result.data?.message || "");
      let userMsg = "We couldn't process this audio. Please try recording again.";
      if (result.data?.error_type === "AnalysisTimeoutError") {
        userMsg = result.data.message;
      } else if (result.data?.error_type === "NoAudioStreamError" || rawMsg.includes("audio track")) {
        userMsg = "This video does not contain an audio track.";
      } else if (result.data?.error_type === "AudioTooShortError" || rawMsg.includes("short")) {
        userMsg = "The voice recording is too short. Please provide at least 1 second of speech.";
      } else if (result.data?.error_type === "AudioSilentError" || rawMsg.includes("silent") || rawMsg.includes("Silence") || rawMsg.includes("speech")) {
        userMsg = "No clear speech was detected.";
      }

      return res.status(result.status === 200 ? 400 : result.status).json({
        error_type: result.data?.error_type || "AudioProcessingError",
        message: userMsg,
        duration_sec: result.data?.duration_sec,
      });
    }

    // Map simplified results safely (Scientifically responsible wording)
    let simple_verdict = "UNABLE TO CONFIRM";
    let simple_verdict_badge = "🟡 UNABLE TO CONFIRM";
    if (result.data.classification === "GENUINE_LIVE") {
      simple_verdict = "LIKELY GENUINE";
      simple_verdict_badge = "🟢 LIKELY GENUINE";
    } else if (result.data.classification === "SYNTHETIC_AI_GENERATED") {
      simple_verdict = "POSSIBLE AI-GENERATED VOICE";
      simple_verdict_badge = "🔴 POSSIBLE AI-GENERATED VOICE";
    } else {
      simple_verdict = "UNABLE TO CONFIRM";
      simple_verdict_badge = "🟡 UNABLE TO CONFIRM";
    }

    // Standardize detected language formatting
    if (
      !result.data.detected_language ||
      ["Unknown", "Unclear", "Silence", "Unavailable", "Error"].includes(result.data.detected_language) ||
      (result.data.language_confidence !== undefined && result.data.language_confidence < 0.40)
    ) {
      result.data.detected_language = "Unable to confidently identify language";
    }

    result.data.input_type = input_type;
    result.data.is_long_recording = is_long_recording;
    result.data.user_notice = user_notice;
    result.data.simple_verdict = simple_verdict;
    result.data.simple_verdict_badge = simple_verdict_badge;

    const totalE2ESec = (performance.now() - tReqStart) / 1000;

    const timingBreakdown = {
      ffmpeg_conversion_sec: Number(ffmpegDurationSec.toFixed(4)),
      python_audio_ingest_sec: Number((result.data?.timing_diagnostics?.audio_ingestion_conversion_sec ?? 0).toFixed(4)),
      total_ingestion_conversion_sec: Number((ffmpegDurationSec + (result.data?.timing_diagnostics?.audio_ingestion_conversion_sec ?? 0)).toFixed(4)),
      model_loading_sec: Number((result.data?.timing_diagnostics?.model_loading_sec ?? 0).toFixed(4)),
      model_resident_in_memory: result.data?.timing_diagnostics?.model_resident_in_memory ?? {},
      reality_defender_api_sec: Number((result.data?.timing_diagnostics?.reality_defender_api_sec ?? 0).toFixed(4)),
      reality_defender_state: result.data?.timing_diagnostics?.reality_defender_state ?? "UNKNOWN",
      aasist_inference_sec: Number((result.data?.timing_diagnostics?.aasist_inference_sec ?? 0).toFixed(4)),
      wav2vec2_inference_sec: Number((result.data?.timing_diagnostics?.wav2vec2_inference_sec ?? 0).toFixed(4)),
      local_heuristic_sec: Number((result.data?.timing_diagnostics?.local_heuristic_sec ?? 0).toFixed(4)),
      asr_transcribe_sec: Number((result.data?.timing_diagnostics?.asr_transcribe_sec ?? 0).toFixed(4)),
      total_end_to_end_sec: Number(totalE2ESec.toFixed(4)),
    };

    result.data.timing_breakdown = timingBreakdown;

    console.log("\n================= /analyze TIMING BREAKDOWN =================");
    console.log(`1. Ingestion / extraction:     ${timingBreakdown.total_ingestion_conversion_sec}s (ffmpeg=${timingBreakdown.ffmpeg_conversion_sec}s, py_ingest=${timingBreakdown.python_audio_ingest_sec}s)`);
    console.log(`2. Model loading:              ${timingBreakdown.model_loading_sec}s (Resident: AASIST=${timingBreakdown.model_resident_in_memory?.aasist}, Wav2Vec2=${timingBreakdown.model_resident_in_memory?.wav2vec2})`);
    console.log(`3. Reality Defender API:       ${timingBreakdown.reality_defender_api_sec}s (State: ${timingBreakdown.reality_defender_state})`);
    console.log(`4. AASIST inference:           ${timingBreakdown.aasist_inference_sec}s`);
    console.log(`5. Wav2Vec2 inference:         ${timingBreakdown.wav2vec2_inference_sec}s`);
    console.log(`6. Language & Speech (Whisper):${timingBreakdown.asr_transcribe_sec}s`);
    console.log(`7. Total end-to-end time:      ${timingBreakdown.total_end_to_end_sec}s`);
    console.log("============================================================\n");

    res.status(200).json(result.data);

  } catch (err: any) {
    console.error("[ServerError:Analyze] Technical error:", err);
    return res.status(500).json({
      error_type: "ServerError",
      message: "Voice analysis could not be completed.",
    });
  } finally {
    try {
      if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);
      if (fs.existsSync(standardWavPath)) fs.unlinkSync(standardWavPath);
    } catch {
      // ignore
    }
  }
};

app.post("/analyze", apiRateLimitMiddleware, apiAuthMiddleware, upload.single("file"), handleAnalyze);
app.post("/api/analyze", apiRateLimitMiddleware, apiAuthMiddleware, upload.single("file"), handleAnalyze);




// In-memory cache for active Secondary Verification Workflow sessions
const activeVerificationSessions = new Map<string, any>();

// In-memory cache for authoritative Security Events & Threat Alerts
interface StoredSecurityEvent {
  id: string;
  call_id: string;
  organization_id: string;
  event_type: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  timestamp: number;
  caller_id?: string | null;
  contact_id?: string | null;
  contact_name?: string | null;
  claimed_role?: string | null;
  speaker_id?: string | null;
  risk_score: number;
  risk_level: string;
  explanation: string;
  recommended_action: string;
  verification_status?: string | null;
  verification_session?: any;
  is_held: boolean;
  transaction_amount?: number | null;
  hold_reason?: string | null;
  flags: string[];
  contributing_signals?: Record<string, any>;
  status: "OPEN" | "RESOLVED" | "ESCALATED" | "INVESTIGATING";
  resolved_at?: number | null;
  resolved_by?: string | null;
  is_simulated: boolean;
}

const activeSecurityEvents: StoredSecurityEvent[] = [
  {
    id: "EVT-9082-CRIT",
    call_id: "CALL-2026-9082-AZ",
    organization_id: DEFAULT_ORG_ID,
    event_type: "DEEPFAKE_VOICE_CLONE",
    severity: "CRITICAL",
    timestamp: Date.now() - 2 * 60 * 1000,
    caller_id: "+1 (415) 890-2100",
    contact_id: "EMP-9001",
    contact_name: "Jane Doe (CEO)",
    claimed_role: "Chief Executive Officer",
    speaker_id: "EMP-9001",
    risk_score: 94,
    risk_level: "CRITICAL",
    explanation: "Wav2Vec2 neural voice clone detected with 96.2% synthetic confidence. Biometric cosine mismatch (0.38 < 0.70). High-value wire transfer blocked.",
    recommended_action: "BLOCK",
    verification_status: "BLOCKED",
    is_held: true,
    transaction_amount: 85000,
    hold_reason: "Call terminated and transaction blocked due to critical voice clone attack.",
    flags: [
      "Wav2Vec2 high neural synthesis probability (96.2%)",
      "ECAPA-TDNN biometric cosine distance mismatch (0.38 < 0.70)",
      "High financial wire anomaly ($85,000 > $5,000 threshold)",
      "Urgency pressure tactics in transcript",
    ],
    contributing_signals: {
      fake_probability: 0.962,
      speaker_similarity: 0.38,
      speaker_match: false,
      acoustic_anomaly: 0.84,
      role_mismatch: true,
    },
    status: "OPEN",
    is_simulated: true,
  },
  {
    id: "EVT-9081-HIGH",
    call_id: "CALL-2026-9081-TX",
    organization_id: DEFAULT_ORG_ID,
    event_type: "TRANSACTION_AUTO_HOLD",
    severity: "HIGH",
    timestamp: Date.now() - 18 * 60 * 1000,
    caller_id: "+1 (212) 555-0199",
    contact_id: "EMP-4102",
    contact_name: "Robert Vance",
    claimed_role: "Treasurer / Accounting",
    speaker_id: "EMP-4102",
    risk_score: 76,
    risk_level: "HIGH",
    explanation: "Transaction of $34,500.00 placed on auto-hold pending secondary identity verification. Acoustic anomalies detected.",
    recommended_action: "SECONDARY_VERIFICATION",
    verification_status: "PENDING",
    is_held: true,
    transaction_amount: 34500,
    hold_reason: "Transaction placed on HOLD pending secondary identity verification.",
    flags: [
      "Synthetic acoustic artifact anomalies detected",
      "Biometric speaker mismatch against enrolled profile",
      "Unrecognized inbound VoIP gateway",
    ],
    contributing_signals: {
      fake_probability: 0.784,
      speaker_similarity: 0.52,
      speaker_match: false,
      acoustic_anomaly: 0.65,
    },
    status: "OPEN",
    is_simulated: true,
  },
  {
    id: "EVT-9080-WARN",
    call_id: "CALL-2026-9080-CA",
    organization_id: DEFAULT_ORG_ID,
    event_type: "ROLE_MISMATCH",
    severity: "MEDIUM",
    timestamp: Date.now() - 45 * 60 * 1000,
    caller_id: "+1 (650) 333-8821",
    contact_id: "EMP-1044",
    contact_name: "Marcus Chen",
    claimed_role: "Senior Director",
    speaker_id: "EMP-1044",
    risk_score: 48,
    risk_level: "MEDIUM",
    explanation: "Claimed role 'Senior Director' conflicts with registered identity profile. Pitch jitter anomaly detected.",
    recommended_action: "CHALLENGE_CALLER",
    verification_status: "CHALLENGE_REQUIRED",
    is_held: false,
    transaction_amount: 4200,
    flags: [
      "Moderate pitch jitter anomaly in early frames",
      "Claimed role mismatch against registry",
    ],
    contributing_signals: {
      fake_probability: 0.442,
      speaker_similarity: 0.74,
      speaker_match: true,
      acoustic_anomaly: 0.45,
      role_mismatch: true,
    },
    status: "OPEN",
    is_simulated: true,
  },
  {
    id: "EVT-9079-SAFE",
    call_id: "CALL-2026-9079-NY",
    organization_id: DEFAULT_ORG_ID,
    event_type: "HIGH_RISK_CALL",
    severity: "LOW",
    timestamp: Date.now() - 60 * 60 * 1000,
    caller_id: "+1 (212) 998-1120",
    contact_id: "EMP-9001",
    contact_name: "Jane Doe",
    claimed_role: "Account Manager",
    speaker_id: "EMP-9001",
    risk_score: 12,
    risk_level: "LOW",
    explanation: "Authentic human prosody spectrum verified. Biometric voiceprint matched with 0.88 cosine similarity.",
    recommended_action: "ALLOW",
    verification_status: "VERIFIED",
    is_held: false,
    transaction_amount: 1500,
    flags: [
      "Authentic human prosody spectrum verified",
      "192-D biometric cosine similarity 0.88 (Clean match)",
    ],
    contributing_signals: {
      fake_probability: 0.041,
      speaker_similarity: 0.88,
      speaker_match: true,
      acoustic_anomaly: 0.08,
    },
    status: "RESOLVED",
    resolved_at: Date.now() - 55 * 60 * 1000,
    resolved_by: "VoiceShieldRiskEngine",
    is_simulated: true,
  },
  {
    id: "EVT-9078-SAFE",
    call_id: "CALL-2026-9078-UK",
    organization_id: DEFAULT_ORG_ID,
    event_type: "HIGH_RISK_CALL",
    severity: "LOW",
    timestamp: Date.now() - 3 * 3600 * 1000,
    caller_id: "+44 20 7946 0991",
    contact_id: "EMP-3091",
    contact_name: "Sarah Jenkins",
    claimed_role: "Client Relations",
    speaker_id: "EMP-3091",
    risk_score: 8,
    risk_level: "LOW",
    explanation: "Zero synthetic artifacts. High signal-to-noise ratio (28.4 dB). Clean authentic speaker.",
    recommended_action: "ALLOW",
    verification_status: "VERIFIED",
    is_held: false,
    transaction_amount: 800,
    flags: [
      "Zero synthetic artifacts",
      "High signal-to-noise ratio (28.4 dB)",
    ],
    contributing_signals: {
      fake_probability: 0.025,
      speaker_similarity: 0.91,
      speaker_match: true,
      acoustic_anomaly: 0.05,
    },
    status: "RESOLVED",
    resolved_at: Date.now() - 2.8 * 3600 * 1000,
    resolved_by: "VoiceShieldRiskEngine",
    is_simulated: true,
  },
];

// Initialize matching verification sessions for seed events
activeVerificationSessions.set("CALL-2026-9082-AZ", {
  call_id: "CALL-2026-9082-AZ",
  organization_id: DEFAULT_ORG_ID,
  status: "BLOCKED",
  recommended_action: "BLOCK",
  risk_score: 94,
  risk_level: "CRITICAL",
  is_held: true,
  hold_reason: "Call terminated and transaction blocked due to critical voice clone attack.",
  selected_method: null,
  in_progress_step: null,
  audit_trail: [
    {
      id: "AUD-SEED-01",
      call_id: "CALL-2026-9082-AZ",
      timestamp: Date.now() - 2 * 60 * 1000,
      previous_state: "NONE",
      new_state: "BLOCKED",
      action: "INITIALIZE_BLOCK",
      actor: "VoiceShieldRiskEngine",
      notes: "Automatic threat block triggered for critical deepfake voice clone.",
      is_simulated: true,
    },
  ],
  context_metadata: {
    caller_id: "+1 (415) 890-2100",
    claimed_role: "Chief Executive Officer",
    requested_transaction_amount: 85000,
    transaction_auto_hold_amount: 5000,
  },
  created_at: (Date.now() - 2 * 60 * 1000) / 1000,
  updated_at: (Date.now() - 2 * 60 * 1000) / 1000,
});

activeVerificationSessions.set("CALL-2026-9081-TX", {
  call_id: "CALL-2026-9081-TX",
  organization_id: DEFAULT_ORG_ID,
  status: "PENDING",
  recommended_action: "SECONDARY_VERIFICATION",
  risk_score: 76,
  risk_level: "HIGH",
  is_held: true,
  hold_reason: "Transaction placed on HOLD pending secondary identity verification.",
  selected_method: null,
  in_progress_step: null,
  audit_trail: [
    {
      id: "AUD-SEED-02",
      call_id: "CALL-2026-9081-TX",
      timestamp: Date.now() - 18 * 60 * 1000,
      previous_state: "NONE",
      new_state: "PENDING",
      action: "INITIALIZE_SECONDARY_VERIFICATION",
      actor: "VoiceShieldRiskEngine",
      notes: "Transaction placed on HOLD pending secondary identity verification.",
      is_simulated: true,
    },
  ],
  context_metadata: {
    caller_id: "+1 (212) 555-0199",
    claimed_role: "Treasurer / Accounting",
    requested_transaction_amount: 34500,
    transaction_auto_hold_amount: 10000,
  },
  created_at: (Date.now() - 18 * 60 * 1000) / 1000,
  updated_at: (Date.now() - 18 * 60 * 1000) / 1000,
});

activeVerificationSessions.set("CALL-2026-9080-CA", {
  call_id: "CALL-2026-9080-CA",
  organization_id: DEFAULT_ORG_ID,
  status: "CHALLENGE_REQUIRED",
  recommended_action: "CHALLENGE_CALLER",
  risk_score: 48,
  risk_level: "MEDIUM",
  is_held: false,
  hold_reason: null,
  selected_method: null,
  in_progress_step: null,
  audit_trail: [
    {
      id: "AUD-SEED-03",
      call_id: "CALL-2026-9080-CA",
      timestamp: Date.now() - 45 * 60 * 1000,
      previous_state: "NONE",
      new_state: "CHALLENGE_REQUIRED",
      action: "INITIALIZE_CHALLENGE_CALLER",
      actor: "VoiceShieldRiskEngine",
      notes: "Challenge caller required due to role mismatch and pitch anomaly.",
      is_simulated: true,
    },
  ],
  context_metadata: {
    caller_id: "+1 (650) 333-8821",
    claimed_role: "Senior Director",
    requested_transaction_amount: 4200,
  },
  created_at: (Date.now() - 45 * 60 * 1000) / 1000,
  updated_at: (Date.now() - 45 * 60 * 1000) / 1000,
});

function recordSecurityEventFromAnalysis(
  resultData: any,
  params: Record<string, any>,
  reqBody: Record<string, any>,
  enrichedContext?: EnrichedCallContext | null
): StoredSecurityEvent | null {
  if (!resultData || !resultData.call_id) return null;

  const callId = resultData.call_id;
  const riskScore = Number(resultData.risk_score ?? 0);
  const riskLevel = String(resultData.risk_level ?? "LOW");
  const recAction = String(resultData.recommended_action ?? "ALLOW");
  const fakeProb = Number(resultData.deepfake_detection?.fake_probability ?? resultData.fake_probability ?? 0);
  const flags = Array.isArray(resultData.flags) ? resultData.flags : [];
  const orgId = enrichedContext?.organization_id || DEFAULT_ORG_ID;

  let eventType = "HIGH_RISK_CALL";
  let severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" = "LOW";

  if (recAction === "BLOCK" || riskScore >= 85 || fakeProb >= 0.85) {
    severity = "CRITICAL";
    eventType = fakeProb >= 0.85 ? "DEEPFAKE_VOICE_CLONE" : recAction === "BLOCK" ? "CALL_BLOCKED" : "HIGH_RISK_CALL";
  } else if (riskScore >= 70 || fakeProb >= 0.65 || resultData.verification_session?.is_held) {
    severity = "HIGH";
    if (enrichedContext?.role_mismatch) {
      const isExec = /ceo|cfo|director|executive|treasurer|president/i.test(enrichedContext.claimed_role || "");
      eventType = isExec ? "EXECUTIVE_IMPERSONATION" : "ROLE_MISMATCH";
    } else if (resultData.verification_session?.is_held) {
      eventType = "TRANSACTION_AUTO_HOLD";
    } else {
      eventType = "HIGH_RISK_CALL";
    }
  } else if (riskScore >= 35) {
    severity = "MEDIUM";
    if (enrichedContext?.role_mismatch) {
      eventType = "ROLE_MISMATCH";
    } else if (resultData.speaker_verification?.is_match === false) {
      eventType = "SPEAKER_MISMATCH";
    } else if (Number(resultData.acoustic_anomaly ?? 0) > 0.5) {
      eventType = "ACOUSTIC_ANOMALY";
    }
  }

  const isHeld = Boolean(resultData.verification_session?.is_held);
  const holdReason = resultData.verification_session?.hold_reason || null;
  const vStatus = resultData.verification_session?.status || (recAction === "ALLOW" ? "VERIFIED" : "PENDING");

  const amount = Number(
    enrichedContext?.requested_amount ??
    reqBody.requested_transaction_amount ??
    reqBody.requested_amount ??
    params.requested_amount ??
    0
  );

  const newEvent: StoredSecurityEvent = {
    id: `EVT-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
    call_id: callId,
    organization_id: orgId,
    event_type: eventType,
    severity,
    timestamp: Date.now(),
    caller_id: enrichedContext?.caller_id || params.caller_id || reqBody.caller_id || null,
    contact_id: enrichedContext?.contact_id || params.contact_id || reqBody.contact_id || null,
    contact_name: enrichedContext?.contact_name || null,
    claimed_role: enrichedContext?.claimed_role || params.claimed_role || reqBody.claimed_role || null,
    speaker_id: resultData.speaker_verification?.speaker_id || params.speaker_id || null,
    risk_score: riskScore,
    risk_level: riskLevel,
    explanation: (
      `Call evaluated with risk score ${riskScore}/100 (${riskLevel}). Action: ${recAction}. ` +
      (flags.length > 0 ? flags.slice(0, 2).join("; ") : "Acoustic / context telemetry analyzed.")
    ),
    recommended_action: recAction,
    verification_status: vStatus,
    verification_session: resultData.verification_session || null,
    is_held: isHeld,
    transaction_amount: amount > 0 ? amount : null,
    hold_reason: holdReason,
    flags,
    contributing_signals: {
      fake_probability: fakeProb,
      speaker_similarity: resultData.speaker_verification?.similarity_score,
      speaker_match: resultData.speaker_verification?.is_match,
      acoustic_anomaly: resultData.acoustic_anomaly,
      role_mismatch: enrichedContext?.role_mismatch,
    },
    status: "OPEN",
    is_simulated: true,
  };

  // Prepend to activeSecurityEvents (bounded to 100)
  activeSecurityEvents.unshift(newEvent);
  if (activeSecurityEvents.length > 100) {
    activeSecurityEvents.pop();
  }

  // Dispatch webhook notification for actionable security events
  if (["WARN", "SECONDARY_VERIFICATION", "CHALLENGE_CALLER", "HOLD_AND_STEP_UP", "BLOCK"].includes(recAction) || riskScore >= 60 || isHeld) {
    const eventTypeStr = isHeld
      ? "transaction_hold_alert"
      : recAction === "BLOCK"
      ? "threat_block_alert"
      : recAction === "SECONDARY_VERIFICATION"
      ? "secondary_verification_alert"
      : "voice_risk_alert";

    notificationDispatcher.dispatchRiskEvent({
      event: eventTypeStr,
      call_id: callId,
      session_id: params.session_id || callId,
      organization_id: orgId,
      risk_score: riskScore,
      risk_level: riskLevel,
      recommended_action: recAction,
      timestamp: new Date().toISOString(),
      caller_id: newEvent.caller_id,
      claimed_role: newEvent.claimed_role,
      transaction_amount: newEvent.transaction_amount,
      hold_reason: newEvent.hold_reason,
      flags,
      contributing_signals: {
        fake_probability: fakeProb,
        speaker_similarity: resultData.speaker_verification?.similarity_score,
        speaker_match: resultData.speaker_verification?.is_match,
        acoustic_anomaly: resultData.acoustic_anomaly,
        role_mismatch: enrichedContext?.role_mismatch,
        language: resultData.language,
      },
    });
  }

  return newEvent;
}


// 7. Live Stream Chunk (REST Fallback): /stream-chunk and /api/stream-chunk
const handleStreamChunk = async (req: express.Request, res: express.Response) => {
  const { pcm_bytes_b64, samples, file, speaker_id, threshold, context, window_index, call_id } = req.body;
  if (!pcm_bytes_b64 && !samples && !file) {
    return res.status(400).json({
      error_type: "MissingPayloadError",
      message: "Supply 'pcm_bytes_b64', 'samples', or 'file' for stream chunk analysis.",
    });
  }

  let enrichedContext: EnrichedCallContext | null = null;
  if (context && typeof context === "object") {
    try {
      enrichedContext = await contextService.retrieveCallContext({
        organization_id: context.organization_id,
        caller_id: context.caller_id,
        contact_id: context.contact_id,
        speaker_id: speaker_id || context.speaker_id,
        claimed_role: context.claimed_role,
        requested_amount: context.requested_transaction_amount ?? context.requested_amount,
        normal_amount: context.normal_transaction_amount ?? context.normal_amount,
        transaction_reference: context.transaction_reference,
        is_urgent: context.is_urgent,
        urgency_reason: context.urgency_reason,
        transcript_text: context.transcript_text,
        is_caller_recognized: context.is_caller_recognized,
        is_previously_flagged: context.is_previously_flagged,
      });
    } catch (ctxErr: any) {
      console.warn("[StreamChunk:ContextError]", ctxErr.message);
    }
  }

  try {
    const result = await daemonManager.request("stream-chunk", {
      pcm_bytes_b64,
      samples,
      file,
      speaker_id,
      threshold,
      context: enrichedContext || context,
      window_index: window_index || 0,
      call_id,
    });
    if (result.status === 200 && result.data?.verification_session && result.data.call_id) {
      activeVerificationSessions.set(result.data.call_id, result.data.verification_session);
    }
    res.status(result.status).json(result.data);
  } catch (err: any) {
    res.status(500).json({
      error_type: "InferenceError",
      message: err.message || "Failed to process stream chunk.",
    });
  }
};

app.post("/stream-chunk", apiRateLimitMiddleware, apiAuthMiddleware, handleStreamChunk);
app.post("/api/stream-chunk", apiRateLimitMiddleware, apiAuthMiddleware, handleStreamChunk);

// ----------------------------------------------------
// FEATURE 1: SECONDARY VERIFICATION WORKFLOW ENDPOINTS
// ----------------------------------------------------

// Get current verification session for a call
app.get("/api/verification/:callId", (req: express.Request, res: express.Response) => {
  const callId = req.params.callId;
  const session = activeVerificationSessions.get(callId);
  if (!session) {
    return res.status(404).json({ error: "Verification session not found for call_id: " + callId });
  }
  res.json({ status: "ok", verification_session: session });
});

// Authoritative verification workflow action processor
app.post("/api/verification/action", async (req: express.Request, res: express.Response) => {
  try {
    const { call_id, action, method, result, notes, actor } = req.body;
    if (!call_id) {
      return res.status(400).json({ error: "Missing required parameter: call_id" });
    }

    let session = activeVerificationSessions.get(call_id);
    if (!session) {
      // Create session if not in cache
      session = {
        call_id,
        organization_id: "00000000-0000-0000-0000-000000000001",
        status: "PENDING",
        recommended_action: "SECONDARY_VERIFICATION",
        risk_score: 75,
        risk_level: "HIGH",
        is_held: true,
        hold_reason: "Transaction placed on HOLD pending secondary identity verification.",
        selected_method: null,
        in_progress_step: null,
        audit_trail: [],
        context_metadata: {},
        created_at: Date.now(),
        updated_at: Date.now(),
      };
      activeVerificationSessions.set(call_id, session);
    }

    const actionUpper = String(action || "").toUpperCase();
    const resultUpper = String(result || "").toUpperCase();
    const actorName = actor || "SecurityOperator";
    const now = Date.now();
    const prevStatus = session.status;

    if (actionUpper === "START" || actionUpper === "START_VERIFICATION") {
      session.status = "VERIFICATION_IN_PROGRESS";
      session.selected_method = method || "VERIFY_CALLER";
      session.in_progress_step = `Executing ${method || "VERIFY_CALLER"}`;
      session.updated_at = now;

      session.audit_trail.push({
        id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
        call_id,
        timestamp: now,
        previous_state: prevStatus,
        new_state: session.status,
        action: "START_VERIFICATION",
        actor: actorName,
        method: session.selected_method,
        notes: notes || `Verification initiated via ${session.selected_method}.`,
        is_simulated: true,
      });
    } else if (actionUpper === "SUBMIT" || actionUpper === "COMPLETE" || actionUpper === "COMPLETE_VERIFICATION") {
      const isSuccess = resultUpper === "SUCCESS" || resultUpper === "PASS" || resultUpper === "VERIFIED";
      if (isSuccess) {
        session.status = "VERIFIED";
        if (session.is_held) {
          session.is_held = false;
          session.hold_reason = "Hold released: Secondary verification completed successfully.";
        }
        session.in_progress_step = null;

        if (supabase) {
          try {
            await supabase
              .from("transactions")
              .update({ status: "APPROVED", hold_reason: "Released upon verified identity." })
              .eq("call_id", call_id);
          } catch (e: any) {
            console.warn("[Supabase:TransactionsUpdate]", e.message);
          }
        }
      } else {
        session.status = "FAILED";
        if (session.is_held) {
          session.hold_reason = "Transaction remains ON HOLD: Secondary verification challenge failed.";
        }
        session.in_progress_step = null;

        if (supabase) {
          try {
            await supabase
              .from("transactions")
              .update({ status: "REJECTED", hold_reason: "Verification challenge failed." })
              .eq("call_id", call_id);
          } catch (e: any) {
            console.warn("[Supabase:TransactionsUpdate]", e.message);
          }
        }
      }
      session.updated_at = now;

      session.audit_trail.push({
        id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
        call_id,
        timestamp: now,
        previous_state: prevStatus,
        new_state: session.status,
        action: isSuccess ? "VERIFICATION_SUCCESS" : "VERIFICATION_FAILURE",
        actor: actorName,
        method: method || session.selected_method,
        notes: notes || (isSuccess ? "Identity verification succeeded." : "Identity verification challenge failed."),
        is_simulated: true,
      });
    } else if (actionUpper === "ESCALATE" || actionUpper === "ESCALATE_TO_SUPERVISOR") {
      session.status = "ESCALATED";
      session.selected_method = "ESCALATE_TO_SUPERVISOR";
      session.in_progress_step = "Pending supervisor manual investigation";
      if (session.is_held) {
        session.hold_reason = "Transaction ON HOLD: Escalated to supervisor for manual review.";
      }
      session.updated_at = now;

      session.audit_trail.push({
        id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
        call_id,
        timestamp: now,
        previous_state: prevStatus,
        new_state: session.status,
        action: "ESCALATE_TO_SUPERVISOR",
        actor: actorName,
        method: "ESCALATE_TO_SUPERVISOR",
        notes: notes || "Escalated to Fraud Operations supervisor.",
        is_simulated: true,
      });
    } else if (actionUpper === "BLOCK" || actionUpper === "BLOCK_CALL") {
      session.status = "BLOCKED";
      session.is_held = true;
      session.hold_reason = notes || "Call terminated and transaction blocked due to high fraud threat.";
      session.in_progress_step = null;
      session.updated_at = now;

      if (supabase) {
        try {
          await supabase
            .from("transactions")
            .update({ status: "REJECTED", hold_reason: "Blocked threat." })
            .eq("call_id", call_id);
        } catch (e: any) {
          console.warn("[Supabase:TransactionsUpdate]", e.message);
        }
      }

      session.audit_trail.push({
        id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
        call_id,
        timestamp: now,
        previous_state: prevStatus,
        new_state: session.status,
        action: "BLOCK_CALL",
        actor: actorName,
        notes: notes || "Call terminated and blacklisted as voice clone attack.",
        is_simulated: true,
      });
    }

    // Persist to audit_logs if Supabase available
    if (supabase) {
      try {
        await supabase.from("audit_logs").insert({
          organization_id: session.organization_id,
          action: `VERIFICATION_${session.status}`,
          details: {
            call_id,
            action,
            method,
            result,
            notes,
            actor: actorName,
            is_simulated: true,
          },
        });
      } catch (e: any) {
        // non-blocking
      }
    }

    // Sync verification state to in-memory security events
    for (const evt of activeSecurityEvents) {
      if (evt.call_id === call_id) {
        evt.verification_status = session.status;
        evt.is_held = session.is_held;
        evt.hold_reason = session.hold_reason;
        evt.verification_session = session;
        if (session.status === "VERIFIED") {
          evt.status = "RESOLVED";
          evt.resolved_at = Date.now();
          evt.resolved_by = actorName;
        } else if (session.status === "ESCALATED") {
          evt.status = "ESCALATED";
        }
      }
    }

    return res.json({
      status: "ok",
      verification_session: session,
    });
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to process verification action" });
  }
});

// ----------------------------------------------------
// FEATURE 2: SECURITY EVENTS & ALERT CENTER ENDPOINTS
// ----------------------------------------------------

function computeSecurityMetrics(events: StoredSecurityEvent[]) {
  const active_threats = events.filter(
    (e) => e.status === "OPEN" && (e.severity === "HIGH" || e.severity === "CRITICAL")
  ).length;

  const critical_events = events.filter((e) => e.severity === "CRITICAL").length;

  const calls_requiring_verification = events.filter(
    (e) =>
      ["SECONDARY_VERIFICATION", "CHALLENGE_CALLER", "HOLD_AND_STEP_UP"].includes(e.recommended_action) ||
      ["PENDING", "CHALLENGE_REQUIRED", "VERIFICATION_IN_PROGRESS"].includes(e.verification_status || "")
  ).length;

  const transactions_on_hold = events.filter((e) => e.is_held).length;

  const blocked_calls = events.filter(
    (e) =>
      e.recommended_action === "BLOCK" ||
      e.verification_status === "BLOCKED" ||
      e.event_type === "CALL_BLOCKED"
  ).length;

  return {
    total_events: events.length,
    active_threats,
    critical_events,
    calls_requiring_verification,
    transactions_on_hold,
    blocked_calls,
  };
}

const handleGetSecurityEvents = async (req: express.Request, res: express.Response) => {
  try {
    // SECURITY HARDENING: Authoritative organization resolution. Never trust client organization_id.
    const orgId = contextService.resolveAuthoritativeOrganizationId(req.query.organization_id as string);
    const filter = (req.query.filter as string || "ALL").toUpperCase().trim();
    const search = (req.query.search as string || "").toLowerCase().trim();

    // Start with authoritative in-memory events for the organization
    let events = activeSecurityEvents.filter((e) => e.organization_id === orgId);

    // If Supabase is connected, query and enrich from alerts & calls tables
    if (supabase) {
      try {
        const { data: dbAlerts, error } = await supabase
          .from("alerts")
          .select("*, calls(*), risk_events(*), transactions(*)")
          .eq("organization_id", orgId)
          .order("created_at", { ascending: false })
          .limit(50);

        if (!error && dbAlerts && dbAlerts.length > 0) {
          const dbEvents: StoredSecurityEvent[] = dbAlerts.map((row: any) => {
            const call = row.calls || {};
            const risk = row.risk_events || {};
            const tx = row.transactions || {};
            return {
              id: row.id || `EVT-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
              call_id: row.call_id || call.id || "CALL-UNKNOWN",
              organization_id: row.organization_id || orgId,
              event_type: row.alert_type || (row.severity === "CRITICAL" ? "DEEPFAKE_VOICE_CLONE" : "HIGH_RISK_CALL"),
              severity: (row.severity || "HIGH").toUpperCase() as any,
              timestamp: row.created_at ? new Date(row.created_at).getTime() : Date.now(),
              caller_id: call.caller_id || null,
              contact_id: call.contact_id || null,
              contact_name: call.contact_name || null,
              claimed_role: call.claimed_role || null,
              speaker_id: call.speaker_id || null,
              risk_score: Number(risk.risk_score ?? 75),
              risk_level: risk.risk_level || (row.severity === "CRITICAL" ? "CRITICAL" : "HIGH"),
              explanation: row.explanation || "Threat intelligence alert recorded in database.",
              recommended_action: risk.recommended_action || "SECONDARY_VERIFICATION",
              verification_status: row.is_resolved ? "VERIFIED" : "PENDING",
              is_held: tx.is_held ?? false,
              transaction_amount: tx.amount ? Number(tx.amount) : null,
              hold_reason: tx.hold_reason || null,
              flags: Array.isArray(row.flags) ? row.flags : [],
              contributing_signals: row.contributing_signals || {},
              status: row.is_resolved ? "RESOLVED" : "OPEN",
              resolved_at: row.resolved_at ? new Date(row.resolved_at).getTime() : null,
              resolved_by: row.resolved_by || null,
              is_simulated: Boolean(row.is_simulated),
            };
          });

          // Merge DB events with in-memory events without duplicates
          const seenIds = new Set(events.map((e) => e.call_id));
          for (const dbe of dbEvents) {
            if (!seenIds.has(dbe.call_id)) {
              events.push(dbe);
              seenIds.add(dbe.call_id);
            }
          }
        }
      } catch (dbErr: any) {
        console.warn("[SecurityEvents:SupabaseFetch]", dbErr.message);
      }
    }

    // Attach current active verification sessions if available
    for (const evt of events) {
      if (evt.call_id && activeVerificationSessions.has(evt.call_id)) {
        const sess = activeVerificationSessions.get(evt.call_id);
        evt.verification_session = sess;
        evt.verification_status = sess.status;
        evt.is_held = sess.is_held;
        evt.hold_reason = sess.hold_reason;
      }
    }

    // Calculate full metrics before filtering
    const summary = computeSecurityMetrics(events);

    // Apply fast filter
    let filtered = events;
    if (filter === "CRITICAL") {
      filtered = filtered.filter((e) => e.severity === "CRITICAL");
    } else if (filter === "HIGH") {
      filtered = filtered.filter((e) => e.severity === "HIGH");
    } else if (filter === "MEDIUM") {
      filtered = filtered.filter((e) => e.severity === "MEDIUM");
    } else if (filter === "LOW") {
      filtered = filtered.filter((e) => e.severity === "LOW");
    } else if (filter === "UNRESOLVED") {
      filtered = filtered.filter((e) => e.status === "OPEN");
    } else if (filter === "VERIFICATION_REQUIRED") {
      filtered = filtered.filter(
        (e) =>
          ["SECONDARY_VERIFICATION", "CHALLENGE_CALLER", "HOLD_AND_STEP_UP"].includes(e.recommended_action) ||
          ["PENDING", "CHALLENGE_REQUIRED", "VERIFICATION_IN_PROGRESS", "FAILED"].includes(e.verification_status || "")
      );
    } else if (filter === "BLOCKED") {
      filtered = filtered.filter(
        (e) =>
          e.recommended_action === "BLOCK" ||
          e.verification_status === "BLOCKED" ||
          e.event_type === "CALL_BLOCKED"
      );
    }

    // Apply search query
    if (search) {
      filtered = filtered.filter((e) => {
        const matchCall = (e.call_id || "").toLowerCase().includes(search);
        const matchCaller = (e.caller_id || "").toLowerCase().includes(search);
        const matchContact =
          (e.contact_name || "").toLowerCase().includes(search) ||
          (e.contact_id || "").toLowerCase().includes(search);
        const matchRole = (e.claimed_role || "").toLowerCase().includes(search);
        const matchType = (e.event_type || "").toLowerCase().includes(search);
        const matchFlags = Array.isArray(e.flags) ? e.flags.some((f) => (f || "").toLowerCase().includes(search)) : false;
        const matchExpl = (e.explanation || "").toLowerCase().includes(search);
        return matchCall || matchCaller || matchContact || matchRole || matchType || matchFlags || matchExpl;
      });
    }

    return res.json({
      status: "ok",
      organization_id: orgId,
      events: filtered,
      summary,
    });
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to fetch security events" });
  }
};

app.get("/api/security-events", handleGetSecurityEvents);
app.get("/api/alerts", handleGetSecurityEvents);

// Get summary metrics only
app.get("/api/security-events/summary", async (req: express.Request, res: express.Response) => {
  try {
    const orgId = contextService.resolveAuthoritativeOrganizationId(req.query.organization_id as string);
    const events = activeSecurityEvents.filter((e) => e.organization_id === orgId);
    const summary = computeSecurityMetrics(events);
    return res.json({ status: "ok", organization_id: orgId, summary });
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to compute security metrics" });
  }
});

// Mark security event / alert as resolved
app.post("/api/security-events/:id/resolve", async (req: express.Request, res: express.Response) => {
  try {
    const eventId = req.params.id;
    const { notes } = req.body;
    const now = Date.now();

    const event = activeSecurityEvents.find((e) => e.id === eventId || e.call_id === eventId);
    if (event) {
      event.status = "RESOLVED";
      event.resolved_at = now;
      event.resolved_by = "SecurityOperator";

      // If associated with a verification session, mark verified/released
      if (event.call_id && activeVerificationSessions.has(event.call_id)) {
        const session = activeVerificationSessions.get(event.call_id);
        session.status = "VERIFIED";
        session.is_held = false;
        session.hold_reason = null;
        session.updated_at = now;
        session.audit_trail.push({
          id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
          call_id: event.call_id,
          timestamp: now,
          previous_state: session.status,
          new_state: "VERIFIED",
          action: "RESOLVE_INCIDENT",
          actor: "SecurityOperator",
          notes: notes || "Incident resolved by security operator.",
          is_simulated: true,
        });
      }
    }

    if (supabase) {
      try {
        await supabase
          .from("alerts")
          .update({ is_resolved: true, resolved_at: new Date(now).toISOString() })
          .eq("id", eventId);

        await supabase.from("audit_logs").insert({
          organization_id: event?.organization_id || DEFAULT_ORG_ID,
          action: "RESOLVE_SECURITY_ALERT",
          details: { event_id: eventId, notes, resolved_at: now, actor: "SecurityOperator" },
        });
      } catch (dbErr: any) {
        console.warn("[SecurityEvents:SupabaseResolve]", dbErr.message);
      }
    }

    return res.json({ status: "ok", event: event || { id: eventId, status: "RESOLVED" } });
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to resolve security event" });
  }
});

// Escalate security event to SOC Supervisor
app.post("/api/security-events/:id/escalate", async (req: express.Request, res: express.Response) => {
  try {
    const eventId = req.params.id;
    const { notes } = req.body;
    const now = Date.now();

    const event = activeSecurityEvents.find((e) => e.id === eventId || e.call_id === eventId);
    if (event) {
      event.status = "ESCALATED";
      event.verification_status = "ESCALATED";

      if (event.call_id && activeVerificationSessions.has(event.call_id)) {
        const session = activeVerificationSessions.get(event.call_id);
        session.status = "ESCALATED";
        session.in_progress_step = "Escalated to Fraud Operations Supervisor";
        session.updated_at = now;
        session.audit_trail.push({
          id: `AUD-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
          call_id: event.call_id,
          timestamp: now,
          previous_state: session.status,
          new_state: "ESCALATED",
          action: "ESCALATE_TO_SUPERVISOR",
          actor: "SecurityOperator",
          notes: notes || "Escalated to supervisor from Alert Center.",
          is_simulated: true,
        });
      }
    }

    if (supabase) {
      try {
        await supabase.from("audit_logs").insert({
          organization_id: event?.organization_id || DEFAULT_ORG_ID,
          action: "ESCALATE_SECURITY_ALERT",
          details: { event_id: eventId, notes, escalated_at: now, actor: "SecurityOperator" },
        });
      } catch (dbErr: any) {
        console.warn("[SecurityEvents:SupabaseEscalate]", dbErr.message);
      }
    }

    return res.json({ status: "ok", event: event || { id: eventId, status: "ESCALATED" } });
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to escalate security event" });
  }
});

// ----------------------------------------------------
// FEATURE 3: AUTHORITATIVE POLICY ENGINE ENDPOINTS
// ----------------------------------------------------





// ----------------------------------------------------
// DATA RETENTION & COMPLIANCE ENDPOINTS
// ----------------------------------------------------
app.get("/api/admin/retention/policy", (req: express.Request, res: express.Response) => {
  res.json({ status: "ok", policy: dataRetentionService.getRetentionPolicy() });
});

app.post("/api/admin/retention/purge", apiAuthMiddleware, async (req: express.Request, res: express.Response) => {
  try {
    const targetOrgId = (req as any).authoritativeOrgId || req.body?.organization_id;
    const result = await dataRetentionService.purgeExpiredRecords(targetOrgId);
    return res.json(result);
  } catch (err: any) {
    return res.status(500).json({ error: err.message || "Failed to execute retention purge." });
  }
});

// ----------------------------------------------------
// WEBSOCKET LIVE STREAMING ENDPOINT (/ws/live-stream)
// ----------------------------------------------------
function appendToRollingTranscript(existing: string, newSnippet: string): string {
  const cleanSnippet = newSnippet.trim();
  if (!cleanSnippet) return existing;
  if (!existing) return cleanSnippet;

  const existingLower = existing.toLowerCase().trim();
  const snippetLower = cleanSnippet.toLowerCase();

  if (existingLower.endsWith(snippetLower) || existingLower.includes(snippetLower)) {
    return existing;
  }

  const existingWords = existing.split(/\s+/);
  const snippetWords = cleanSnippet.split(/\s+/);

  const maxOverlap = Math.min(existingWords.length, snippetWords.length);
  for (let overlap = maxOverlap; overlap > 0; overlap--) {
    const endSlice = existingWords.slice(existingWords.length - overlap).join(" ").toLowerCase();
    const startSlice = snippetWords.slice(0, overlap).join(" ").toLowerCase();
    if (endSlice === startSlice) {
      const remainder = snippetWords.slice(overlap).join(" ");
      return remainder ? `${existing} ${remainder}` : existing;
    }
  }

  return `${existing} ${cleanSnippet}`;
}

// ----------------------------------------------------
// VITE INTEGRATION / STATIC SERVING
// ----------------------------------------------------
async function startServer() {
  const server = http.createServer(app);

  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        watch: {
          ignored: [
            "**/data/**",
            "**/*.db*",
            "**/*.sqlite*",
            "**/.venv/**",
            "**/venv/**",
            "**/*.wav",
            "**/*.mp3",
            "**/*.log",
          ],
        },
      },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  server.listen(PORT, "0.0.0.0", () => {
    console.log(`[VoiceShield Server] Listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
