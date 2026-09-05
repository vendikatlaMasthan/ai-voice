import React, { useState } from "react";
import { Sliders, User, DollarSign, AlertOctagon, ChevronDown, ChevronUp, Zap, Globe, Languages } from "lucide-react";
import { CallContextState, EnrolledSpeaker } from "../types";

interface ContextFormProps {
  context: CallContextState;
  onChange: (updated: Partial<CallContextState>) => void;
  enrolledSpeakers: EnrolledSpeaker[];
  disabled: boolean;
}

export const SUPPORTED_LANGUAGES = [
  { id: "Auto Detect", label: "Auto Detect (Indian / Multilingual)", code: "auto" },
  { id: "English", label: "English (Indian / Global)", code: "en-IN" },
  { id: "Hindi", label: "Hindi (हिन्दी)", code: "hi-IN" },
  { id: "Telugu", label: "Telugu (తెలుగు)", code: "te-IN" },
  { id: "Tamil", label: "Tamil (தமிழ்)", code: "ta-IN" },
  { id: "Kannada", label: "Kannada (ಕನ್ನಡ)", code: "kn-IN" },
  { id: "Malayalam", label: "Malayalam (മലയാളം)", code: "ml-IN" },
  { id: "Bengali", label: "Bengali (বাংলা)", code: "bn-IN" },
  { id: "Marathi", label: "Marathi (मराठी)", code: "mr-IN" },
];

export const ACCENT_REGIONS = [
  { id: "Pan-Indian / General", label: "Pan-Indian / General Standard" },
  { id: "North India (Hindi / Delhi-NCR / UP)", label: "North India (Hindi / Delhi-NCR / UP)" },
  { id: "South India (Karnataka / Bangalore)", label: "South India (Karnataka / Bangalore)" },
  { id: "South India (Telangana / Andhra Pradesh)", label: "South India (Telangana / Andhra Pradesh)" },
  { id: "South India (Tamil Nadu / Chennai)", label: "South India (Tamil Nadu / Chennai)" },
  { id: "South India (Kerala / Malayalam)", label: "South India (Kerala / Malayalam)" },
  { id: "East India (West Bengal / Kolkata)", label: "East India (West Bengal / Kolkata)" },
  { id: "West India (Maharashtra / Mumbai)", label: "West India (Maharashtra / Mumbai)" },
];

export const ContextForm: React.FC<ContextFormProps> = ({
  context,
  onChange,
  enrolledSpeakers,
  disabled,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const applyPreset = (type: "ceo_fraud" | "normal_call" | "hindi_otp" | "tamil_bank") => {
    if (type === "ceo_fraud") {
      onChange({
        speaker_id: enrolledSpeakers.length > 0 ? enrolledSpeakers[0].speaker_id : "EMP-9001",
        verification_threshold: 0.70,
        caller_id: "+1-555-0199",
        is_caller_recognized: false,
        is_previously_flagged: false,
        claimed_role: "CEO",
        requested_transaction_amount: "85000",
        normal_transaction_amount: "5000",
        is_urgent: true,
        urgency_reason: "Immediate overseas vendor acquisition deadline",
        transcript_text: "Please wire the 85,000 USD immediately before banking cutoff.",
        selected_language: "English",
        language: "English",
        accent_region: "Pan-Indian / General",
      });
      setIsExpanded(true);
    } else if (type === "hindi_otp") {
      onChange({
        speaker_id: "EMP-9001",
        verification_threshold: 0.75,
        caller_id: "+91-98765-43210",
        is_caller_recognized: false,
        is_previously_flagged: false,
        claimed_role: "Bank Manager",
        requested_transaction_amount: "50000",
        normal_transaction_amount: "5000",
        is_urgent: true,
        urgency_reason: "Aadhaar KYC suspension threat",
        transcript_text: "तुरंत ओटीपी बताएं वरना आपका खाता ब्लॉक हो जाएगा (Tell OTP immediately or account will be blocked)",
        selected_language: "Hindi",
        language: "Hindi",
        accent_region: "North India (Hindi / Delhi-NCR / UP)",
      });
      setIsExpanded(true);
    } else if (type === "tamil_bank") {
      onChange({
        speaker_id: "EMP-9001",
        verification_threshold: 0.75,
        caller_id: "+91-94440-12345",
        is_caller_recognized: false,
        is_previously_flagged: true,
        claimed_role: "Chief Compliance Officer",
        requested_transaction_amount: "150000",
        normal_transaction_amount: "10000",
        is_urgent: true,
        urgency_reason: "Urgent wire authorization request",
        transcript_text: "உடனடியாக பணத்தை மாற்றுங்கள், சரிபார்க்க வேண்டாம் (Transfer funds immediately, do not verify)",
        selected_language: "Tamil",
        language: "Tamil",
        accent_region: "South India (Tamil Nadu / Chennai)",
      });
      setIsExpanded(true);
    } else if (type === "normal_call") {
      onChange({
        speaker_id: enrolledSpeakers.length > 0 ? enrolledSpeakers[0].speaker_id : "EMP-9001",
        verification_threshold: 0.70,
        caller_id: "+91-80-5550100",
        is_caller_recognized: true,
        is_previously_flagged: false,
        claimed_role: "Account Manager",
        requested_transaction_amount: "1500",
        normal_transaction_amount: "2000",
        is_urgent: false,
        urgency_reason: "",
        transcript_text: "Following up on standard monthly invoice approval.",
        selected_language: "Auto Detect",
        language: "Auto Detect",
        accent_region: "Pan-Indian / General",
      });
      setIsExpanded(true);
    }
  };

  return (
    <div id="context-configuration-panel" className="glass-card rounded-2xl p-5 space-y-4 border border-white/10 shadow-lg">
      {/* Header with toggle and presets */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <button
          type="button"
          id="toggle-context-form-btn"
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-3 text-left hover:opacity-90 transition-opacity"
        >
          <div className="w-9 h-9 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shadow-sm shrink-0">
            <Sliders className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-bold text-white flex items-center gap-2">
              Contextual Anti-Fraud Signals & Speech Readiness
              {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </div>
            <div className="text-xs text-slate-400">
              {context.speaker_id || context.claimed_role || context.selected_language || context.requested_transaction_amount
                ? `Configured: ${context.selected_language && context.selected_language !== "Auto Detect" ? `Lang [${context.selected_language}] • ` : ""}${context.speaker_id ? `Speaker [${context.speaker_id}] • ` : ""}${context.claimed_role ? `Role [${context.claimed_role}]` : ""}`
                : "Multilingual Indian speech profiles (Hindi, Tamil, Telugu, Kannada, etc.), authority roles, and financial thresholds."}
            </div>
          </div>
        </button>

        {/* Quick Simulation Preset Buttons */}
        <div className="flex items-center gap-1.5 self-start sm:self-center flex-wrap">
          <span className="text-[11px] text-slate-400 flex items-center gap-1 font-semibold font-mono">
            <Zap className="w-3 h-3 text-amber-400" />
            Presets:
          </span>
          <button
            type="button"
            onClick={() => applyPreset("hindi_otp")}
            disabled={disabled}
            className="px-2.5 py-1 rounded-lg bg-orange-500/10 hover:bg-orange-500/20 text-[11px] font-semibold font-mono text-orange-300 border border-orange-500/30 transition-colors squish-btn"
          >
            Hindi OTP Scam
          </button>
          <button
            type="button"
            onClick={() => applyPreset("tamil_bank")}
            disabled={disabled}
            className="px-2.5 py-1 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-[11px] font-semibold font-mono text-cyan-300 border border-cyan-500/30 transition-colors squish-btn"
          >
            Tamil Wire Fraud
          </button>
          <button
            type="button"
            onClick={() => applyPreset("ceo_fraud")}
            disabled={disabled}
            className="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-[11px] font-semibold font-mono text-amber-300 border border-amber-500/30 transition-colors squish-btn"
          >
            CEO Impersonation
          </button>
          <button
            type="button"
            onClick={() => applyPreset("normal_call")}
            disabled={disabled}
            className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-[11px] font-semibold font-mono text-emerald-300 border border-emerald-500/30 transition-colors squish-btn"
          >
            Normal Call
          </button>
        </div>
      </div>

      {/* Expandable Form Body */}
      {isExpanded && (
        <div className="pt-4 border-t border-white/10 space-y-4 text-xs">
          
          {/* Row 1: Multilingual / Indian Speech Readiness (Feature 4) */}
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-indigo-500/20 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-indigo-300 font-semibold font-mono">
                <Globe className="w-4 h-4 text-indigo-400" />
                <span>Multilingual & Indian Speech Profile (Feature 4)</span>
              </div>
              <span className="text-[10px] font-mono text-indigo-400/80 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                Non-Authoritative Metadata
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="context-selected-language" className="font-semibold text-slate-300 flex items-center gap-1.5 font-mono">
                  <Languages className="w-3.5 h-3.5 text-indigo-400" />
                  Speech Language Selection:
                </label>
                <select
                  id="context-selected-language"
                  value={context.selected_language || context.language || "Auto Detect"}
                  onChange={(e) => {
                    const val = e.target.value;
                    onChange({ selected_language: val, language: val });
                  }}
                  disabled={disabled}
                  className="w-full bg-slate-950/90 border border-slate-700/80 rounded-xl px-3 py-2 text-slate-200 text-xs focus:outline-none focus:border-indigo-500 shadow-inner font-mono"
                >
                  {SUPPORTED_LANGUAGES.map((lang) => (
                    <option key={lang.id} value={lang.id} className="bg-slate-900">
                      {lang.label}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 font-mono">
                  Inference pipeline acoustic signals remain invariant across languages.
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="context-accent-region" className="font-semibold text-slate-300 flex items-center gap-1.5 font-mono">
                  <Globe className="w-3.5 h-3.5 text-indigo-400" />
                  Regional Accent Profile:
                </label>
                <select
                  id="context-accent-region"
                  value={context.accent_region || "Pan-Indian / General"}
                  onChange={(e) => onChange({ accent_region: e.target.value, accent_profile: e.target.value })}
                  disabled={disabled}
                  className="w-full bg-slate-950/90 border border-slate-700/80 rounded-xl px-3 py-2 text-slate-200 text-xs focus:outline-none focus:border-indigo-500 shadow-inner font-mono"
                >
                  {ACCENT_REGIONS.map((acc) => (
                    <option key={acc.id} value={acc.id} className="bg-slate-900">
                      {acc.label}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 font-mono">
                  Provides contextual regional metadata for fraud risk logging.
                </p>
              </div>
            </div>
          </div>

          {/* Row 2: Speaker Selection & Verification Threshold */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label htmlFor="context-speaker-id" className="font-semibold text-slate-300 flex items-center gap-1.5 font-mono">
                <User className="w-3.5 h-3.5 text-blue-400" />
                Claimed Speaker ID (Phase 5 Biometrics):
              </label>
              <div className="flex gap-2">
                <input
                  id="context-speaker-id"
                  type="text"
                  placeholder="e.g. EMP-9001, CEO-JANE"
                  value={context.speaker_id}
                  onChange={(e) => onChange({ speaker_id: e.target.value })}
                  disabled={disabled}
                  className="flex-1 bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 shadow-inner font-mono"
                />
                {enrolledSpeakers.length > 0 && (
                  <select
                    id="select-enrolled-speaker"
                    onChange={(e) => e.target.value && onChange({ speaker_id: e.target.value })}
                    disabled={disabled}
                    className="bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-slate-200 text-xs focus:outline-none shadow-inner font-mono"
                    value=""
                  >
                    <option value="" disabled className="bg-slate-900">Select Profile</option>
                    {enrolledSpeakers.map((s) => (
                      <option key={s.speaker_id} value={s.speaker_id} className="bg-slate-900">
                        {s.speaker_id} {s.speaker_name ? `(${s.speaker_name})` : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Matches against 192-D ECAPA-TDNN embedding in profile store.
              </p>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="context-threshold-slider" className="font-semibold text-slate-300 font-mono">
                  Verification Threshold (τ):
                </label>
                <span className="font-mono text-blue-400 font-bold bg-blue-500/10 px-2 py-0.5 rounded border border-blue-400/20">
                  {context.verification_threshold.toFixed(2)}
                </span>
              </div>
              <input
                id="context-threshold-slider"
                type="range"
                min="0.50"
                max="0.95"
                step="0.01"
                value={context.verification_threshold}
                onChange={(e) => onChange({ verification_threshold: parseFloat(e.target.value) })}
                disabled={disabled}
                className="w-full accent-blue-500"
              />
              <div className="flex justify-between text-[10px] font-mono text-slate-500">
                <span>0.50 (Relaxed)</span>
                <span>0.70 (Standard Default)</span>
                <span>0.95 (Strict High-Sec)</span>
              </div>
            </div>
          </div>

          {/* Row 3: Authority Role & Financial Amounts */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label htmlFor="context-claimed-role" className="font-semibold text-slate-300 font-mono">
                Claimed Authority Role:
              </label>
              <input
                id="context-claimed-role"
                type="text"
                placeholder="e.g. CEO, CFO, Bank Manager"
                value={context.claimed_role}
                onChange={(e) => onChange({ claimed_role: e.target.value })}
                disabled={disabled}
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 shadow-inner font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="context-requested-amount" className="font-semibold text-slate-300 flex items-center gap-1 font-mono">
                <DollarSign className="w-3.5 h-3.5 text-amber-400" />
                Requested Amount ($ / ₹):
              </label>
              <input
                id="context-requested-amount"
                type="number"
                placeholder="e.g. 75000"
                value={context.requested_transaction_amount}
                onChange={(e) => onChange({ requested_transaction_amount: e.target.value })}
                disabled={disabled}
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 shadow-inner font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="context-normal-amount" className="font-semibold text-slate-300 font-mono">
                Normal Baseline ($ / ₹):
              </label>
              <input
                id="context-normal-amount"
                type="number"
                placeholder="e.g. 5000"
                value={context.normal_transaction_amount}
                onChange={(e) => onChange({ normal_transaction_amount: e.target.value })}
                disabled={disabled}
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 shadow-inner font-mono"
              />
            </div>
          </div>

          {/* Row 4: Caller Status & Urgency */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
            <div className="space-y-1.5">
              <label htmlFor="context-caller-id" className="font-semibold text-slate-300 font-mono">
                Caller Phone / ANI:
              </label>
              <input
                id="context-caller-id"
                type="text"
                placeholder="+91-98765-43210"
                value={context.caller_id}
                onChange={(e) => onChange({ caller_id: e.target.value })}
                disabled={disabled}
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none shadow-inner font-mono"
              />
            </div>

            <div className="flex items-center gap-4 pt-5">
              <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-300">
                <input
                  type="checkbox"
                  checked={context.is_caller_recognized}
                  onChange={(e) => onChange({ is_caller_recognized: e.target.checked })}
                  disabled={disabled}
                  className="rounded border-slate-700 bg-slate-900 text-blue-500 focus:ring-0"
                />
                <span>Recognized Contact</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer font-medium">
                <input
                  type="checkbox"
                  checked={context.is_urgent}
                  onChange={(e) => onChange({ is_urgent: e.target.checked })}
                  disabled={disabled}
                  className="rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-0"
                />
                <span className="text-amber-300 flex items-center gap-1">
                  <AlertOctagon className="w-3.5 h-3.5" />
                  Urgency Pressure
                </span>
              </label>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="context-transcript" className="font-semibold text-slate-300 font-mono">
                Transcript / Multilingual Keyword Snippet:
              </label>
              <input
                id="context-transcript"
                type="text"
                placeholder="e.g. ओटीपी बताएं (Hindi) / உடனடியாக அனுப்புங்கள் (Tamil)"
                value={context.transcript_text}
                onChange={(e) => onChange({ transcript_text: e.target.value })}
                disabled={disabled}
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none shadow-inner font-mono"
              />
            </div>
          </div>

        </div>
      )}
    </div>
  );
};


