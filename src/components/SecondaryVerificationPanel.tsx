import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  PhoneCall,
  KeyRound,
  UserCheck,
  AlertTriangle,
  Lock,
  Unlock,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  Send,
  RefreshCw,
  Ban,
  UserX,
  FileText,
  ChevronRight,
  Activity,
  Check
} from "lucide-react";
import {
  SecondaryVerificationStatus,
  VerificationMethod,
  VerificationSessionState,
  VerificationAuditRecord,
} from "../types";
import { postVerificationAction } from "../api";

interface SecondaryVerificationPanelProps {
  callId: string;
  initialSession?: VerificationSessionState;
  recommendedAction?: string;
  riskScore?: number;
  riskLevel?: string;
  onSessionUpdated?: (session: VerificationSessionState) => void;
}

export const SecondaryVerificationPanel: React.FC<SecondaryVerificationPanelProps> = ({
  callId,
  initialSession,
  recommendedAction = "SECONDARY_VERIFICATION",
  riskScore = 75,
  riskLevel = "HIGH",
  onSessionUpdated,
}) => {
  const [session, setSession] = useState<VerificationSessionState>(() => {
    if (initialSession) return initialSession;
    return {
      call_id: callId,
      status:
        recommendedAction === "CHALLENGE_CALLER"
          ? "CHALLENGE_REQUIRED"
          : riskLevel === "CRITICAL" || riskScore >= 90
          ? "BLOCKED"
          : "PENDING",
      recommended_action: recommendedAction,
      risk_score: riskScore,
      risk_level: riskLevel,
      is_held: recommendedAction !== "ALLOW" && riskScore >= 50,
      hold_reason: "Transaction held pending secondary identity verification.",
      selected_method: null,
      in_progress_step: null,
      audit_trail: [],
      created_at: Date.now(),
      updated_at: Date.now(),
    };
  });

  const [selectedMethod, setSelectedMethod] = useState<VerificationMethod>("VERIFY_CALLER");
  const [operatorNotes, setOperatorNotes] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [challengeStep, setChallengeStep] = useState<number>(1);
  const [simulatedOtp, setSimulatedOtp] = useState<string>("849201");
  const [inputOtp, setInputOtp] = useState<string>("");
  const [challengeResponse, setChallengeResponse] = useState<string>("");

  useEffect(() => {
    if (initialSession) {
      setSession(initialSession);
    }
  }, [initialSession]);

  const handleExecuteAction = async (
    action: "START_VERIFICATION" | "COMPLETE_VERIFICATION" | "ESCALATE" | "BLOCK",
    result?: "SUCCESS" | "FAILURE",
    methodOverride?: string,
    notesOverride?: string
  ) => {
    setIsSubmitting(true);
    try {
      const payloadMethod = methodOverride || selectedMethod;
      const notes = notesOverride || operatorNotes || `Action ${action} triggered by operator.`;

      const updated = await postVerificationAction({
        call_id: session.call_id || callId,
        action,
        method: payloadMethod,
        result,
        notes,
        actor: "FraudSecAnalyst",
      });

      if (updated) {
        setSession(updated);
        if (onSessionUpdated) {
          onSessionUpdated(updated);
        }
      }
    } catch (err: any) {
      console.error("[VerificationActionError]", err);
      // Fallback local update if offline / simulated
      const now = Date.now();
      const prev = session.status;
      let nextStatus: SecondaryVerificationStatus = session.status;
      let nextHeld = session.is_held;
      let nextReason = session.hold_reason;

      if (action === "START_VERIFICATION") {
        nextStatus = "VERIFICATION_IN_PROGRESS";
      } else if (action === "COMPLETE_VERIFICATION") {
        if (result === "SUCCESS") {
          nextStatus = "VERIFIED";
          nextHeld = false;
          nextReason = "Hold released: Identity verified successfully.";
        } else {
          nextStatus = "FAILED";
          nextReason = "Transaction remains ON HOLD: Challenge failed.";
        }
      } else if (action === "ESCALATE") {
        nextStatus = "ESCALATED";
        nextReason = "Transaction ON HOLD: Escalated to supervisor.";
      } else if (action === "BLOCK") {
        nextStatus = "BLOCKED";
        nextHeld = true;
        nextReason = "Call terminated and blacklisted.";
      }

      const localAudit: VerificationAuditRecord = {
        id: `AUD-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
        call_id: session.call_id || callId,
        timestamp: now,
        previous_state: prev,
        new_state: nextStatus,
        action,
        actor: "FraudSecAnalyst",
        method: methodOverride || selectedMethod,
        notes: notesOverride || operatorNotes,
        is_simulated: true,
      };

      const updatedSession: VerificationSessionState = {
        ...session,
        status: nextStatus,
        is_held: nextHeld,
        hold_reason: nextReason,
        selected_method: methodOverride || selectedMethod,
        updated_at: now,
        audit_trail: [localAudit, ...session.audit_trail],
      };

      setSession(updatedSession);
      if (onSessionUpdated) {
        onSessionUpdated(updatedSession);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusBadge = (status: SecondaryVerificationStatus) => {
    switch (status) {
      case "VERIFIED":
        return {
          bg: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
          label: "VERIFIED & AUTHENTICATED",
          glow: "shadow-[0_0_15px_rgba(16,185,129,0.3)]",
        };
      case "VERIFICATION_IN_PROGRESS":
        return {
          bg: "bg-sky-500/20 text-sky-300 border-sky-500/40",
          icon: <RefreshCw className="w-4 h-4 text-sky-400 animate-spin" />,
          label: "VERIFICATION IN PROGRESS",
          glow: "shadow-[0_0_15px_rgba(14,165,233,0.3)]",
        };
      case "CHALLENGE_REQUIRED":
        return {
          bg: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          icon: <ShieldAlert className="w-4 h-4 text-amber-400 animate-pulse" />,
          label: "CHALLENGE REQUIRED",
          glow: "shadow-[0_0_15px_rgba(245,158,11,0.3)]",
        };
      case "FAILED":
        return {
          bg: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          icon: <XCircle className="w-4 h-4 text-rose-400" />,
          label: "VERIFICATION FAILED",
          glow: "shadow-[0_0_15px_rgba(244,63,94,0.3)]",
        };
      case "ESCALATED":
        return {
          bg: "bg-purple-500/20 text-purple-300 border-purple-500/40",
          icon: <AlertTriangle className="w-4 h-4 text-purple-400" />,
          label: "ESCALATED TO SUPERVISOR",
          glow: "shadow-[0_0_15px_rgba(168,85,247,0.3)]",
        };
      case "BLOCKED":
        return {
          bg: "bg-red-950/80 text-red-300 border-red-500/60",
          icon: <Ban className="w-4 h-4 text-red-400" />,
          label: "CALL BLOCKED / TERMINATED",
          glow: "shadow-[0_0_20px_rgba(239,68,68,0.4)]",
        };
      default:
        return {
          bg: "bg-slate-700/40 text-slate-300 border-slate-600/40",
          icon: <Clock className="w-4 h-4 text-slate-400" />,
          label: "PENDING VERIFICATION",
          glow: "",
        };
    }
  };

  const statusMeta = getStatusBadge(session.status);

  return (
    <div
      id="secondary-verification-panel"
      className={`rounded-2xl border border-slate-700/60 bg-slate-900/80 backdrop-blur-xl p-6 shadow-2xl transition-all duration-300 relative overflow-hidden ${statusMeta.glow}`}
    >
      {/* Background ambient gradient */}
      <div className="absolute -right-20 -top-20 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -left-20 -bottom-20 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-5 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 text-indigo-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-slate-100 tracking-tight">
                Secondary Verification Workflow
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                STATE MACHINE ACTIVE
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Authoritative step-up protocol & risk challenge execution
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div
          id="verification-status-badge"
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full border text-xs font-semibold uppercase tracking-wider ${statusMeta.bg}`}
        >
          {statusMeta.icon}
          <span>{statusMeta.label}</span>
        </div>
      </div>

      {/* Transaction & Policy Hold Status Bar */}
      <div className="my-4 p-3.5 rounded-xl bg-slate-800/50 border border-slate-700/50 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              session.is_held
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
            }`}
          >
            {session.is_held ? <Lock className="w-4 h-4" /> : <Unlock className="w-4 h-4" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-300">Transaction Status:</span>
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded ${
                  session.is_held
                    ? "bg-rose-950/60 text-rose-300 border border-rose-800/40"
                    : "bg-emerald-950/60 text-emerald-300 border border-emerald-800/40"
                }`}
              >
                {session.is_held ? "ON HOLD" : "RELEASED / APPROVED"}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {session.hold_reason || (session.is_held ? "Awaiting identity challenge resolution." : "Authorized for processing.")}
            </p>
          </div>
        </div>

        {session.is_held && session.status !== "BLOCKED" && (
          <button
            id="emergency-hold-release-btn"
            disabled={isSubmitting}
            onClick={() => handleExecuteAction("COMPLETE_VERIFICATION", "SUCCESS", undefined, "Manual supervisor hold release override.")}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 transition-colors flex items-center gap-1.5"
          >
            <Unlock className="w-3.5 h-3.5 text-amber-400" />
            <span>Force Release Hold</span>
          </button>
        )}
      </div>

      {/* Main Interactive Workflow Area */}
      {session.status === "VERIFIED" ? (
        <div className="my-5 p-5 rounded-xl bg-emerald-950/30 border border-emerald-500/40 flex flex-col items-center text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 mb-3 shadow-[0_0_20px_rgba(16,185,129,0.3)]">
            <Check className="w-6 h-6 stroke-[3]" />
          </div>
          <h4 className="text-base font-bold text-emerald-300">Identity Successfully Verified</h4>
          <p className="text-xs text-emerald-200/80 max-w-md mt-1">
            The caller has passed the authoritative secondary verification challenge. All security holds have been released and the transaction is authorized.
          </p>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={() => handleExecuteAction("START_VERIFICATION", undefined, "VERIFY_CALLER", "Re-verification requested.")}
              className="text-xs px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
              <span>Re-run Challenge</span>
            </button>
          </div>
        </div>
      ) : session.status === "BLOCKED" ? (
        <div className="my-5 p-5 rounded-xl bg-red-950/40 border border-red-500/50 flex flex-col items-center text-center">
          <div className="w-12 h-12 rounded-full bg-red-500/20 border border-red-500/50 flex items-center justify-center text-red-400 mb-3 shadow-[0_0_20px_rgba(239,68,68,0.3)]">
            <Ban className="w-6 h-6 stroke-[3]" />
          </div>
          <h4 className="text-base font-bold text-red-300">Session Terminated & Blacklisted</h4>
          <p className="text-xs text-red-200/80 max-w-md mt-1">
            High-confidence voice clone threat detected. The audio stream and transaction have been terminated with zero-trust isolation.
          </p>
        </div>
      ) : session.status === "VERIFICATION_IN_PROGRESS" ? (
        <div className="my-5 p-5 rounded-xl bg-slate-800/60 border border-sky-500/30 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-sky-400 animate-spin" />
              <span className="text-sm font-semibold text-sky-300">
                Executing: {selectedMethod.replace(/_/g, " ")}
              </span>
            </div>
            <span className="text-xs text-slate-400 font-mono">Step {challengeStep} of 2</span>
          </div>

          {selectedMethod === "VERIFY_CALLER" && (
            <div className="space-y-3">
              <p className="text-xs text-slate-300 leading-relaxed">
                Ask the caller the predetermined security challenge phrase or dynamic knowledge query:
              </p>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-amber-300">
                "Please confirm your employee badge sequence and the last authorized department code."
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  Caller Response / Security Code
                </label>
                <input
                  id="caller-challenge-input"
                  type="text"
                  value={challengeResponse}
                  onChange={(e) => setChallengeResponse(e.target.value)}
                  placeholder="e.g. BDG-9942 / ACCT-SEC-4"
                  className="w-full bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>
          )}

          {selectedMethod === "REQUIRE_MFA_OTP" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-300">
                  A high-entropy OTP token was dispatched to the registered mobile authenticator:
                </p>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
                  OTP: {simulatedOtp}
                </span>
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  Enter 6-Digit Token Received from Caller
                </label>
                <input
                  id="mfa-otp-input"
                  type="text"
                  maxLength={6}
                  value={inputOtp}
                  onChange={(e) => setInputOtp(e.target.value)}
                  placeholder="Enter OTP (e.g. 849201)"
                  className="w-full bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-center tracking-widest text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>
          )}

          {selectedMethod === "INDEPENDENT_CALLBACK" && (
            <div className="space-y-3">
              <p className="text-xs text-slate-300">
                Initiating independent voice callback via trusted enterprise directory PSTN channel:
              </p>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-700 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-slate-300 font-mono">
                  <PhoneCall className="w-4 h-4 text-emerald-400 animate-pulse" />
                  <span>Outbound: +1 (555) 019-8432 (Registered Executive Desk)</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                  RINGING
                </span>
              </div>
            </div>
          )}

          {selectedMethod === "ESCALATE_TO_SUPERVISOR" && (
            <div className="space-y-3">
              <p className="text-xs text-slate-300">
                Routing live audio capture and biometric feature vector to the Tier-2 Fraud Operations supervisor console:
              </p>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-purple-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-purple-400" />
                <span>Ticket #FRAUD-{session.call_id.substring(0, 8)} created in Supervisor Queue.</span>
              </div>
            </div>
          )}

          {/* Action Resolution Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-700/60">
            <button
              id="verification-pass-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("COMPLETE_VERIFICATION", "SUCCESS", undefined, `Verified via ${selectedMethod}`)}
              className="flex-1 min-w-[130px] px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-medium text-xs shadow-lg shadow-emerald-900/30 flex items-center justify-center gap-1.5 transition-all"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Pass & Authorize</span>
            </button>

            <button
              id="verification-fail-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("COMPLETE_VERIFICATION", "FAILURE", undefined, `Failed challenge via ${selectedMethod}`)}
              className="flex-1 min-w-[130px] px-4 py-2 rounded-xl bg-gradient-to-r from-rose-700 to-red-700 hover:from-rose-600 hover:to-red-600 text-white font-medium text-xs shadow-lg shadow-rose-900/30 flex items-center justify-center gap-1.5 transition-all"
            >
              <XCircle className="w-4 h-4" />
              <span>Fail Challenge</span>
            </button>

            <button
              id="verification-escalate-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("ESCALATE", undefined, "ESCALATE_TO_SUPERVISOR", "Operator escalated to Tier-2 supervisor.")}
              className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-purple-300 border border-purple-500/30 text-xs flex items-center gap-1.5 transition-all"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Escalate</span>
            </button>

            <button
              id="verification-block-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("BLOCK", undefined, undefined, "Operator terminated call due to fraud threat.")}
              className="px-3 py-2 rounded-xl bg-red-950/80 hover:bg-red-900 text-red-300 border border-red-500/50 text-xs flex items-center gap-1.5 transition-all"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Block Call</span>
            </button>
          </div>
        </div>
      ) : (
        /* Methods Selector Area (When PENDING, CHALLENGE_REQUIRED, FAILED, or ESCALATED) */
        <div className="my-5 space-y-4">
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Select Verification Step-Up Method
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {/* Method 1: Verify Caller */}
            <button
              id="method-verify-caller-btn"
              onClick={() => setSelectedMethod("VERIFY_CALLER")}
              className={`p-3 rounded-xl border text-left transition-all flex items-start gap-3 ${
                selectedMethod === "VERIFY_CALLER"
                  ? "bg-indigo-950/60 border-indigo-500 text-slate-100 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                  : "bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <div className={`p-2 rounded-lg ${selectedMethod === "VERIFY_CALLER" ? "bg-indigo-500/20 text-indigo-400" : "bg-slate-800 text-slate-500"}`}>
                <UserCheck className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold block text-slate-200">1. Verify Caller</span>
                <span className="text-[11px] text-slate-400 block mt-0.5">
                  Dynamic challenge-response & employee security phrase
                </span>
              </div>
            </button>

            {/* Method 2: Independent Callback */}
            <button
              id="method-callback-btn"
              onClick={() => setSelectedMethod("INDEPENDENT_CALLBACK")}
              className={`p-3 rounded-xl border text-left transition-all flex items-start gap-3 ${
                selectedMethod === "INDEPENDENT_CALLBACK"
                  ? "bg-indigo-950/60 border-indigo-500 text-slate-100 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                  : "bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <div className={`p-2 rounded-lg ${selectedMethod === "INDEPENDENT_CALLBACK" ? "bg-indigo-500/20 text-indigo-400" : "bg-slate-800 text-slate-500"}`}>
                <PhoneCall className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold block text-slate-200">2. Independent Callback</span>
                <span className="text-[11px] text-slate-400 block mt-0.5">
                  Outbound call to trusted directory phone number on record
                </span>
              </div>
            </button>

            {/* Method 3: Require MFA / OTP */}
            <button
              id="method-mfa-otp-btn"
              onClick={() => setSelectedMethod("REQUIRE_MFA_OTP")}
              className={`p-3 rounded-xl border text-left transition-all flex items-start gap-3 ${
                selectedMethod === "REQUIRE_MFA_OTP"
                  ? "bg-indigo-950/60 border-indigo-500 text-slate-100 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                  : "bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <div className={`p-2 rounded-lg ${selectedMethod === "REQUIRE_MFA_OTP" ? "bg-indigo-500/20 text-indigo-400" : "bg-slate-800 text-slate-500"}`}>
                <KeyRound className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold block text-slate-200">3. Require MFA / OTP</span>
                <span className="text-[11px] text-slate-400 block mt-0.5">
                  Send time-based push token to enterprise authenticator app
                </span>
              </div>
            </button>

            {/* Method 4: Escalate to Supervisor */}
            <button
              id="method-escalate-btn"
              onClick={() => setSelectedMethod("ESCALATE_TO_SUPERVISOR")}
              className={`p-3 rounded-xl border text-left transition-all flex items-start gap-3 ${
                selectedMethod === "ESCALATE_TO_SUPERVISOR"
                  ? "bg-indigo-950/60 border-indigo-500 text-slate-100 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                  : "bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <div className={`p-2 rounded-lg ${selectedMethod === "ESCALATE_TO_SUPERVISOR" ? "bg-indigo-500/20 text-indigo-400" : "bg-slate-800 text-slate-500"}`}>
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold block text-slate-200">4. Escalate to Supervisor</span>
                <span className="text-[11px] text-slate-400 block mt-0.5">
                  Route voice telemetry & high-risk event to Tier-2 analyst
                </span>
              </div>
            </button>
          </div>

          {/* Action Trigger Button */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              id="start-verification-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("START_VERIFICATION")}
              className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-medium text-xs shadow-lg shadow-indigo-950/50 flex items-center justify-center gap-2 transition-all"
            >
              <ArrowRight className="w-4 h-4" />
              <span>Initiate Selected Step-Up Protocol</span>
            </button>

            <button
              id="quick-block-btn"
              disabled={isSubmitting}
              onClick={() => handleExecuteAction("BLOCK", undefined, undefined, "Immediate threat termination.")}
              className="py-2.5 px-4 rounded-xl bg-red-950/80 hover:bg-red-900 text-red-300 border border-red-500/40 text-xs font-medium flex items-center gap-1.5 transition-all"
            >
              <Ban className="w-4 h-4" />
              <span>Block Immediately</span>
            </button>
          </div>
        </div>
      )}

      {/* Audit Trail Section */}
      <div className="mt-6 pt-4 border-t border-slate-800">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-slate-400" />
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Verification Audit Trail & Event Log
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-500">
            {session.audit_trail.length} Event{session.audit_trail.length === 1 ? "" : "s"} Recorded
          </span>
        </div>

        {session.audit_trail.length === 0 ? (
          <p className="text-xs text-slate-500 italic py-2">
            No verification actions recorded yet for call {session.call_id.substring(0, 16)}...
          </p>
        ) : (
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {session.audit_trail.map((audit) => (
              <div
                key={audit.id}
                className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-start justify-between gap-3 text-xs"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className="mt-0.5">
                    {audit.new_state === "VERIFIED" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : audit.new_state === "FAILED" || audit.new_state === "BLOCKED" ? (
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                    ) : audit.new_state === "ESCALATED" ? (
                      <AlertTriangle className="w-3.5 h-3.5 text-purple-400" />
                    ) : (
                      <Activity className="w-3.5 h-3.5 text-indigo-400" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-200">{audit.action}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                        {audit.previous_state} → {audit.new_state}
                      </span>
                    </div>
                    {audit.notes && (
                      <p className="text-[11px] text-slate-400 mt-0.5 truncate">{audit.notes}</p>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[10px] font-mono text-slate-500 block">
                    {new Date(audit.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="text-[10px] text-indigo-400 font-mono block">
                    {audit.actor}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
