import React, { useState } from "react";
import { RotateCcw, Copy, Check, ShieldCheck, ShieldAlert, AlertTriangle } from "lucide-react";
import { AnalyzeResponse } from "../types";

interface AnalysisResultProps {
  result: AnalyzeResponse;
  onReset: () => void;
}

export const AnalysisResult: React.FC<AnalysisResultProps> = ({ result, onReset }) => {
  const [copied, setCopied] = useState(false);

  const isFake = result.deepfake_detection.prediction === "FAKE" || result.deepfake_detection.fake_probability >= 0.5;
  const isHighRisk = result.risk_level === "HIGH" || result.risk_level === "CRITICAL" || result.risk_score >= 60 || isFake;
  const isMediumRisk = !isHighRisk && (result.risk_level === "MEDIUM" || result.risk_score >= 40);
  const isLowRisk = !isHighRisk && !isMediumRisk;

  const fakePct = Math.round(result.deepfake_detection.fake_probability * 100);

  const copyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div id="analysis-result-container" className="space-y-6">
      
      {isHighRisk && (
        <div className="glass-card rounded-2xl border border-red-500 bg-red-950/20 p-8 shadow-2xl relative overflow-hidden flex flex-col items-center text-center">
          <div className="w-20 h-20 rounded-full bg-red-500/20 border border-red-500/40 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(239,68,68,0.3)]">
            <ShieldAlert className="w-10 h-10 text-red-500" />
          </div>
          <h2 className="text-sm font-bold text-red-500 tracking-widest uppercase mb-2">Voice Analysis</h2>
          <h1 className="text-4xl font-black text-white mb-4">🔴 AI VOICE DETECTED</h1>
          <p className="text-slate-300 max-w-md mx-auto mb-8 text-lg">
            This voice may be AI generated or cloned.
          </p>
          <div className="flex gap-8 justify-center font-mono">
            <div>
              <p className="text-slate-400 text-xs mb-1">AI Probability</p>
              <p className="text-2xl font-bold text-red-400">{fakePct}%</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Confidence</p>
              <p className="text-2xl font-bold text-white">HIGH</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Risk</p>
              <p className="text-2xl font-bold text-red-400">HIGH</p>
            </div>
          </div>
        </div>
      )}

      {isMediumRisk && (
        <div className="glass-card rounded-2xl border border-amber-500 bg-amber-950/20 p-8 shadow-2xl relative overflow-hidden flex flex-col items-center text-center">
          <div className="w-20 h-20 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(245,158,11,0.3)]">
            <AlertTriangle className="w-10 h-10 text-amber-500" />
          </div>
          <h2 className="text-sm font-bold text-amber-500 tracking-widest uppercase mb-2">Voice Analysis</h2>
          <h1 className="text-4xl font-black text-white mb-4">🟡 UNCERTAIN</h1>
          <p className="text-slate-300 max-w-md mx-auto mb-8 text-lg">
            Audio quality is insufficient for a reliable determination. Please provide a clearer recording.
          </p>
        </div>
      )}

      {isLowRisk && (
        <div className="glass-card rounded-2xl border border-emerald-500 bg-emerald-950/20 p-8 shadow-2xl relative overflow-hidden flex flex-col items-center text-center">
          <div className="w-20 h-20 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(16,185,129,0.3)]">
            <ShieldCheck className="w-10 h-10 text-emerald-500" />
          </div>
          <h2 className="text-sm font-bold text-emerald-500 tracking-widest uppercase mb-2">Voice Analysis</h2>
          <h1 className="text-4xl font-black text-white mb-4">🟢 HUMAN VOICE</h1>
          <p className="text-slate-300 max-w-md mx-auto mb-8 text-lg">
            This appears to be a real human voice.
          </p>
          <div className="flex gap-8 justify-center font-mono">
            <div>
              <p className="text-slate-400 text-xs mb-1">AI Probability</p>
              <p className="text-2xl font-bold text-emerald-400">{fakePct}%</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Confidence</p>
              <p className="text-2xl font-bold text-white">HIGH</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Risk</p>
              <p className="text-2xl font-bold text-emerald-400">LOW</p>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
        <button
          onClick={onReset}
          className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg transition-all squish-btn font-mono"
        >
          <RotateCcw className="w-4 h-4" />
          Analyze Another Audio Stream
        </button>

        <button
          onClick={copyJson}
          className="px-4 py-2.5 rounded-xl glass-card hover:bg-white/10 text-slate-300 font-mono text-xs flex items-center justify-center gap-2 transition-all shadow-sm border border-white/10 squish-btn"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
          {copied ? "Report Copied" : "Copy Raw JSON"}
        </button>
      </div>

    </div>
  );
};
