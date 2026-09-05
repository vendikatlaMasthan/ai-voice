import React, { useState, useEffect } from "react";
import {
  Sliders,
  ShieldAlert,
  ShieldCheck,
  Zap,
  Save,
  RotateCcw,
  CheckCircle2,
  Lock,
  Cpu,
  Fingerprint,
  Radio,
  AlertOctagon,
  Sparkles,
  History,
  DollarSign,
  Info,
  Clock,
  UserCheck,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { OrganizationPolicy, PolicyAuditLog } from "../types";
import {
  fetchOrganizationPolicy,
  updateOrganizationPolicy,
  resetOrganizationPolicy,
  fetchPolicyAuditLogs,
} from "../api";

export const PolicyConfigView: React.FC = () => {
  // Authoritative Policy State
  const [policy, setPolicy] = useState<OrganizationPolicy>({
    organization_id: "00000000-0000-0000-0000-000000000001",
    fake_prob_critical_threshold: 0.85,
    fake_prob_warn_threshold: 0.50,
    speaker_verification_strictness: 0.65,
    acoustic_anomaly_sensitivity: 0.70,
    transaction_auto_hold_amount: 500000,
    step_up_verification_required: true,
    auto_block_on_critical_deepfake: true,
  });

  const [auditLogs, setAuditLogs] = useState<PolicyAuditLog[]>([]);
  const [orgId, setOrgId] = useState<string>("00000000-0000-0000-0000-000000000001");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<"thresholds" | "audit">("thresholds");

  // Load authoritative policy from backend on mount
  const loadPolicy = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [polData, logData] = await Promise.all([
        fetchOrganizationPolicy().catch((err) => {
          console.warn("Failed fetching policy:", err);
          return null;
        }),
        fetchPolicyAuditLogs().catch((err) => {
          console.warn("Failed fetching audit logs:", err);
          return null;
        }),
      ]);

      if (polData?.policy) {
        setPolicy(polData.policy);
        setOrgId(polData.organization_id || polData.policy.organization_id);
      }
      if (logData?.audit_logs) {
        setAuditLogs(logData.audit_logs);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load organization policy.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPolicy();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setErrorMessage(null);
    setSaveSuccessMsg(null);
    try {
      const result = await updateOrganizationPolicy(policy, "SecurityAdmin (Web Console)");
      if (result.policy) {
        setPolicy(result.policy);
        setOrgId(result.organization_id || result.policy.organization_id);
        const changeCount = result.changes?.length || 0;
        setSaveSuccessMsg(
          changeCount > 0
            ? `Successfully saved and enforced ${changeCount} policy change${changeCount > 1 ? "s" : ""}.`
            : "Policy validated and active."
        );
        // Refresh audit logs
        const updatedLogs = await fetchPolicyAuditLogs().catch(() => null);
        if (updatedLogs?.audit_logs) {
          setAuditLogs(updatedLogs.audit_logs);
        }
      }
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to persist organization policy.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Reset all policy thresholds to authoritative system defaults?")) {
      return;
    }
    setIsResetting(true);
    setErrorMessage(null);
    setSaveSuccessMsg(null);
    try {
      const result = await resetOrganizationPolicy("SecurityAdmin (Reset Defaults)");
      if (result.policy) {
        setPolicy(result.policy);
        setOrgId(result.organization_id || result.policy.organization_id);
        setSaveSuccessMsg("Authoritative default thresholds restored successfully.");
        const updatedLogs = await fetchPolicyAuditLogs().catch(() => null);
        if (updatedLogs?.audit_logs) {
          setAuditLogs(updatedLogs.audit_logs);
        }
      }
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to reset organization policy.");
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div id="policy-config-view" className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card rounded-2xl p-6 border border-white/10 shadow-lg flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0 mt-0.5">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-white">
                Organization Policy &amp; Security Controls Engine
              </h2>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                TENANT ISOLATION ACTIVE
              </span>
              <span className="text-[10px] font-mono text-slate-400 bg-white/5 px-2 py-0.5 rounded border border-white/10">
                Org: {orgId.substring(0, 18)}...
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Authoritatively manages deterministic fusion thresholds, neural deepfake triggers, biometric strictness, and automated transaction hold limits across all voice channels.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start md:self-center">
          <button
            onClick={handleReset}
            disabled={isResetting || isSaving || isLoading}
            className="px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-mono font-semibold transition-all flex items-center gap-1.5 disabled:opacity-50"
            title="Restore system defaults"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${isResetting ? "animate-spin" : ""}`} />
            Reset Defaults
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || isResetting || isLoading}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold font-mono flex items-center gap-2 shadow-lg shadow-blue-500/25 transition-all squish-btn disabled:opacity-50"
          >
            {isSaving ? (
              <RefreshCw className="w-4 h-4 animate-spin text-white" />
            ) : saveSuccessMsg ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-300" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {isSaving ? "Saving..." : saveSuccessMsg ? "Enforced" : "Save Policy"}
          </button>
        </div>
      </div>

      {/* Status Notifications */}
      {saveSuccessMsg && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2 font-mono animate-fade-in">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>{saveSuccessMsg}</span>
        </div>
      )}

      {errorMessage && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-center gap-2 font-mono animate-fade-in">
          <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Sub-tabs: Configuration vs. Audit Logs */}
      <div className="flex items-center justify-between border-b border-white/10 pb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveSubTab("thresholds")}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-2 ${
              activeSubTab === "thresholds"
                ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            Policy Parameters
          </button>
          <button
            onClick={() => setActiveSubTab("audit")}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-2 ${
              activeSubTab === "audit"
                ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            Audit Trail ({auditLogs.length})
          </button>
        </div>

        <span className="text-[11px] font-mono text-slate-500">
          Source: Authoritative DB Context
        </span>
      </div>

      {activeSubTab === "thresholds" ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Card 1: Neural Detection & Acoustic Sensitivity */}
          <div className="glass-card rounded-2xl p-6 space-y-5 border border-white/10 shadow-lg">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Neural &amp; Acoustic Scoring</h3>
                  <div className="text-[10px] text-slate-400">Wav2Vec2 + Prosody Feature Extraction</div>
                </div>
              </div>
              <span className="text-[10px] font-mono text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-400/20">
                Wav2Vec2 300M
              </span>
            </div>

            <div className="space-y-5 text-xs">
              {/* Slider 1: Critical Deepfake Threshold */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-slate-200 flex items-center gap-1.5">
                    <span>Critical Synthetic Deepfake Threshold:</span>
                    <span className="text-[10px] text-red-400 font-mono font-bold">(Triggers BLOCK)</span>
                  </label>
                  <span className="font-mono text-red-400 font-bold bg-red-500/10 px-2 py-0.5 rounded border border-red-400/20">
                    {(policy.fake_prob_critical_threshold * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.50"
                  max="0.99"
                  step="0.01"
                  value={policy.fake_prob_critical_threshold}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    setPolicy((prev) => ({
                      ...prev,
                      fake_prob_critical_threshold: val,
                      // Ensure warn threshold does not exceed critical
                      fake_prob_warn_threshold: Math.min(prev.fake_prob_warn_threshold, val),
                    }));
                  }}
                  className="w-full accent-red-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] font-mono text-slate-500">
                  <span>50% (High Sensitivity)</span>
                  <span>85% (Production Baseline)</span>
                  <span>99% (Conservative)</span>
                </div>
              </div>

              {/* Slider 2: Warning Threshold */}
              <div className="space-y-1.5 pt-2 border-t border-white/5">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-slate-200 flex items-center gap-1.5">
                    <span>Warning / Suspicious Deepfake Threshold:</span>
                    <span className="text-[10px] text-amber-400 font-mono font-bold">(Triggers WARN / STEP-UP)</span>
                  </label>
                  <span className="font-mono text-amber-400 font-bold bg-amber-500/10 px-2 py-0.5 rounded border border-amber-400/20">
                    {(policy.fake_prob_warn_threshold * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.10"
                  max={policy.fake_prob_critical_threshold}
                  step="0.01"
                  value={policy.fake_prob_warn_threshold}
                  onChange={(e) =>
                    setPolicy((prev) => ({
                      ...prev,
                      fake_prob_warn_threshold: parseFloat(e.target.value),
                    }))
                  }
                  className="w-full accent-amber-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] font-mono text-slate-500">
                  <span>10% (Early Warning)</span>
                  <span>50% (Standard Warning)</span>
                  <span>{(policy.fake_prob_critical_threshold * 100).toFixed(0)}% (Critical Cap)</span>
                </div>
              </div>

              {/* Slider 3: Acoustic Anomaly Sensitivity */}
              <div className="space-y-1.5 pt-2 border-t border-white/5">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-slate-200 flex items-center gap-1.5">
                    <span>Acoustic Prosody Anomaly Sensitivity:</span>
                    <span className="text-[10px] text-emerald-400 font-mono font-bold">(Jitter / Shimmer / Formants)</span>
                  </label>
                  <span className="font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-400/20">
                    {(policy.acoustic_anomaly_sensitivity * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.40"
                  max="0.99"
                  step="0.01"
                  value={policy.acoustic_anomaly_sensitivity}
                  onChange={(e) =>
                    setPolicy((prev) => ({
                      ...prev,
                      acoustic_anomaly_sensitivity: parseFloat(e.target.value),
                    }))
                  }
                  className="w-full accent-emerald-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] font-mono text-slate-500">
                  <span>40% (Lenient Pitch)</span>
                  <span>70% (Default Multi-Band)</span>
                  <span>99% (Strict Formants)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: Biometric Verification & Step-Up Routing */}
          <div className="glass-card rounded-2xl p-6 space-y-5 border border-white/10 shadow-lg">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                  <Fingerprint className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Biometrics &amp; Step-Up Enforcement</h3>
                  <div className="text-[10px] text-slate-400">ECAPA-TDNN 192-D Voiceprints</div>
                </div>
              </div>
              <span className="text-[10px] font-mono text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-400/20">
                192-D Cosine
              </span>
            </div>

            <div className="space-y-4 text-xs">
              {/* Speaker Verification Strictness */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-slate-200">
                    Speaker Verification Threshold (τ):
                  </label>
                  <span className="font-mono text-purple-400 font-bold bg-purple-500/10 px-2 py-0.5 rounded border border-purple-400/20">
                    τ = {policy.speaker_verification_strictness.toFixed(2)}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {[
                    { val: 0.60, label: "Lenient", sub: "τ = 0.60" },
                    { val: 0.65, label: "Standard", sub: "τ = 0.65 (Def)" },
                    { val: 0.80, label: "Strict", sub: "τ = 0.80" },
                  ].map((tier) => (
                    <button
                      key={tier.label}
                      type="button"
                      onClick={() =>
                        setPolicy((prev) => ({
                          ...prev,
                          speaker_verification_strictness: tier.val,
                        }))
                      }
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        Math.abs(policy.speaker_verification_strictness - tier.val) < 0.03
                          ? "bg-purple-500/20 border-purple-400 text-white font-bold shadow-sm"
                          : "bg-white/5 border-white/10 text-slate-400 hover:bg-white/10 hover:text-white"
                      }`}
                    >
                      <div className="text-xs">{tier.label}</div>
                      <div className="text-[10px] font-mono text-slate-400">{tier.sub}</div>
                    </button>
                  ))}
                </div>

                <input
                  type="range"
                  min="0.40"
                  max="0.95"
                  step="0.01"
                  value={policy.speaker_verification_strictness}
                  onChange={(e) =>
                    setPolicy((prev) => ({
                      ...prev,
                      speaker_verification_strictness: parseFloat(e.target.value),
                    }))
                  }
                  className="w-full accent-purple-500 cursor-pointer mt-1"
                />
              </div>

              {/* Transaction Auto-Hold Amount */}
              <div className="space-y-1.5 pt-2 border-t border-white/5">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-slate-200 flex items-center gap-1">
                    <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Transaction Auto-Hold Amount:</span>
                  </label>
                  <span className="font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-400/20">
                    ${policy.transaction_auto_hold_amount.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="0"
                    step="5000"
                    value={policy.transaction_auto_hold_amount}
                    onChange={(e) =>
                      setPolicy((prev) => ({
                        ...prev,
                        transaction_auto_hold_amount: Math.max(0, parseFloat(e.target.value) || 0),
                      }))
                    }
                    className="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-white font-mono text-xs focus:border-blue-500 focus:outline-none"
                    placeholder="Enter threshold (e.g. 50000)"
                  />
                  <div className="flex gap-1">
                    {[10000, 50000, 500000].map((amt) => (
                      <button
                        key={amt}
                        type="button"
                        onClick={() =>
                          setPolicy((prev) => ({
                            ...prev,
                            transaction_auto_hold_amount: amt,
                          }))
                        }
                        className="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-[10px] font-mono text-slate-300 border border-white/10"
                      >
                        ${amt / 1000}k
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-[10px] text-slate-400">
                  Transactions exceeding this amount will automatically be placed on HOLD pending secondary verification.
                </p>
              </div>

              {/* Automated Actions & Step-Up Toggles */}
              <div className="space-y-2.5 pt-2 border-t border-white/5">
                <label className="flex items-center justify-between cursor-pointer p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
                  <div className="space-y-0.5">
                    <div className="font-semibold text-red-300 flex items-center gap-1.5">
                      <ShieldAlert className="w-3.5 h-3.5" />
                      Auto-Block on Critical Deepfake
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Instantly terminates call and blocks financial operations when synthesis &gt; {(policy.fake_prob_critical_threshold * 100).toFixed(0)}%.
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={policy.auto_block_on_critical_deepfake}
                    onChange={(e) =>
                      setPolicy((prev) => ({
                        ...prev,
                        auto_block_on_critical_deepfake: e.target.checked,
                      }))
                    }
                    className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-red-500 focus:ring-0 cursor-pointer"
                  />
                </label>

                <label className="flex items-center justify-between cursor-pointer p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
                  <div className="space-y-0.5">
                    <div className="font-semibold text-amber-300 flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5" />
                      Enforce Step-Up Secondary Verification
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Mandate out-of-band verification (OTP / Callback) on elevated risk or role mismatches.
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={policy.step_up_verification_required}
                    onChange={(e) =>
                      setPolicy((prev) => ({
                        ...prev,
                        step_up_verification_required: e.target.checked,
                      }))
                    }
                    className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-0 cursor-pointer"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Audit Logs View */
        <div className="glass-card rounded-2xl p-6 border border-white/10 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-bold text-white">Policy Engine Audit Log Trail</h3>
            </div>
            <button
              onClick={loadPolicy}
              className="text-xs text-slate-400 hover:text-white flex items-center gap-1 font-mono"
            >
              <RefreshCw className="w-3 h-3" />
              Refresh
            </button>
          </div>

          {auditLogs.length === 0 ? (
            <div className="py-12 text-center text-slate-400 font-mono text-xs">
              No policy modifications recorded yet for this organization.
            </div>
          ) : (
            <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
              {auditLogs.map((log, idx) => (
                <div
                  key={log.id || idx}
                  className="p-3.5 rounded-xl bg-white/5 border border-white/10 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-400/20">
                        {log.action || "UPDATE_ORGANIZATION_POLICY"}
                      </span>
                      <span className="text-slate-300 font-semibold flex items-center gap-1">
                        <UserCheck className="w-3.5 h-3.5 text-slate-400" />
                        {log.actor || "SecurityAdmin"}
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(log.timestamp).toLocaleString()}
                    </span>
                  </div>

                  {log.changes && log.changes.length > 0 ? (
                    <div className="space-y-1 pt-1 border-t border-white/5">
                      <div className="text-[10px] font-mono text-slate-400">Modified Fields:</div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {log.changes.map((c, cIdx) => (
                          <div
                            key={cIdx}
                            className="p-1.5 rounded bg-black/40 border border-white/5 font-mono text-[11px] flex items-center justify-between"
                          >
                            <span className="text-slate-300">{c.field}</span>
                            <span className="text-slate-400">
                              <span className="text-red-400 line-through mr-1">{String(c.prev)}</span>
                              &rarr;
                              <span className="text-emerald-400 ml-1 font-bold">{String(c.next)}</span>
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-[11px] text-slate-400 font-mono">
                      Policy synchronized and validated.
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
