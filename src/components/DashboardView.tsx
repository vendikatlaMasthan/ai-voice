import React from "react";
import { ShieldCheck, AlertTriangle, HelpCircle, FileAudio, Mic, ArrowRight, Clock } from "lucide-react";
import { AnalysisRecord, NavTab } from "../types";

interface DashboardViewProps {
  history: AnalysisRecord[];
  onNavigate: (tab: NavTab) => void;
  onSelectRecord: (record: AnalysisRecord) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  history,
  onNavigate,
  onSelectRecord,
}) => {
  const totalScans = history.length;
  const genuineCount = history.filter((h) => h.verdict === "GENUINE_LIVE").length;
  const syntheticCount = history.filter((h) => h.verdict === "SYNTHETIC_AI_GENERATED").length;
  const uncertainCount = history.filter(
    (h) => h.verdict === "UNCERTAIN" || h.verdict === "REPLAYED_RECORDED"
  ).length;

  const recentScans = history.slice(0, 5);

  const getVerdictBadge = (record: AnalysisRecord) => {
    switch (record.verdict) {
      case "GENUINE_LIVE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            🟢 Genuine Live
          </span>
        );
      case "SYNTHETIC_AI_GENERATED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
            🔴 Synthetic AI
          </span>
        );
      case "REPLAYED_RECORDED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
            🟠 Replayed Audio
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-500/15 text-yellow-300 border border-yellow-500/30">
            🟡 Uncertain
          </span>
        );
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header Banner */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Voice Safety Overview</h1>
        <p className="text-sm text-slate-400 mt-1">
          Detect whether an audio clip is an authentic human voice or an AI-generated clone.
        </p>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
          <div className="text-xs font-medium text-slate-400">Total Analyzed</div>
          <div className="text-2xl font-bold text-white mt-2">{totalScans}</div>
          <div className="text-xs text-slate-500 mt-1">Total audio checks</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
          <div className="text-xs font-medium text-emerald-400 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5" /> Genuine Human
          </div>
          <div className="text-2xl font-bold text-emerald-300 mt-2">{genuineCount}</div>
          <div className="text-xs text-slate-500 mt-1">Authentic voice verified</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
          <div className="text-xs font-medium text-rose-400 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> AI Synthetic
          </div>
          <div className="text-2xl font-bold text-rose-300 mt-2">{syntheticCount}</div>
          <div className="text-xs text-slate-500 mt-1">Clone deepfakes flagged</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
          <div className="text-xs font-medium text-yellow-400 flex items-center gap-1.5">
            <HelpCircle className="w-3.5 h-3.5" /> Uncertain / Replayed
          </div>
          <div className="text-2xl font-bold text-yellow-300 mt-2">{uncertainCount}</div>
          <div className="text-xs text-slate-500 mt-1">Requires clearer audio</div>
        </div>
      </div>

      {/* Quick Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          onClick={() => onNavigate("upload")}
          className="group cursor-pointer bg-gradient-to-br from-blue-950/30 to-indigo-950/20 hover:from-blue-900/40 hover:to-indigo-900/30 border border-blue-500/20 hover:border-blue-400/40 rounded-2xl p-6 transition-all shadow-sm"
        >
          <div className="w-12 h-12 rounded-xl bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-300 mb-4 group-hover:scale-105 transition-transform">
            <FileAudio className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-semibold text-white group-hover:text-blue-200 flex items-center justify-between">
            Upload Audio File
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-blue-300 group-hover:translate-x-1 transition-all" />
          </h2>
          <p className="text-sm text-slate-400 mt-2">
            Upload any voice recording in WAV, MP3, or FLAC format to inspect its authenticity.
          </p>
        </div>

        <div
          onClick={() => onNavigate("record")}
          className="group cursor-pointer bg-gradient-to-br from-purple-950/30 to-slate-900/50 hover:from-purple-900/40 hover:to-slate-900/70 border border-purple-500/20 hover:border-purple-400/40 rounded-2xl p-6 transition-all shadow-sm"
        >
          <div className="w-12 h-12 rounded-xl bg-purple-500/20 border border-purple-400/30 flex items-center justify-center text-purple-300 mb-4 group-hover:scale-105 transition-transform">
            <Mic className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-semibold text-white group-hover:text-purple-200 flex items-center justify-between">
            Record Voice Sample
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-purple-300 group-hover:translate-x-1 transition-all" />
          </h2>
          <p className="text-sm text-slate-400 mt-2">
            Record directly from your microphone and test if the speech is detected as live human speech.
          </p>
        </div>
      </div>

      {/* Recent Analyses Section */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" /> Recent Voice Checks
          </h2>
          {history.length > 5 && (
            <button
              onClick={() => onNavigate("history")}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium"
            >
              View all ({history.length})
            </button>
          )}
        </div>

        {recentScans.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl space-y-3">
            <FileAudio className="w-10 h-10 text-slate-600 mx-auto" />
            <p className="text-sm text-slate-400">No analyses performed yet.</p>
            <button
              onClick={() => onNavigate("upload")}
              className="px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors"
            >
              Run First Audio Check
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {recentScans.map((record) => (
              <div
                key={record.id}
                onClick={() => onSelectRecord(record)}
                className="py-3 flex items-center justify-between hover:bg-slate-800/30 px-3 rounded-xl cursor-pointer transition-colors"
              >
                <div className="min-w-0 pr-4">
                  <div className="text-sm font-medium text-white truncate">{record.fileName}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {new Date(record.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &bull;{" "}
                    {record.durationSec}s duration
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {getVerdictBadge(record)}
                  <ArrowRight className="w-4 h-4 text-slate-500" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
