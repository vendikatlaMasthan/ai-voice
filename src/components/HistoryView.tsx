import React from "react";
import { Clock, Trash2, ArrowRight, FileAudio } from "lucide-react";
import { AnalysisRecord, NavTab } from "../types";

interface HistoryViewProps {
  history: AnalysisRecord[];
  onSelectRecord: (record: AnalysisRecord) => void;
  onClearHistory: () => void;
  onNavigate: (tab: NavTab) => void;
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  history,
  onSelectRecord,
  onClearHistory,
  onNavigate,
}) => {
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
            🟠 Replayed
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
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Title & Clear Action */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Analysis History</h1>
          <p className="text-sm text-slate-400 mt-1">Review past voice checks and authenticity reports.</p>
        </div>

        {history.length > 0 && (
          <button
            onClick={onClearHistory}
            className="text-xs font-semibold text-slate-400 hover:text-rose-300 flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800/60 hover:bg-slate-800 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" /> Clear History
          </button>
        )}
      </div>

      {history.length === 0 ? (
        <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-12 text-center space-y-4">
          <Clock className="w-12 h-12 text-slate-600 mx-auto" />
          <h3 className="text-lg font-semibold text-white">No Analysis History Yet</h3>
          <p className="text-sm text-slate-400 max-w-sm mx-auto">
            Audio samples you analyze will appear here so you can review their findings at any time.
          </p>
          <div className="flex justify-center gap-3 pt-2">
            <button
              onClick={() => onNavigate("upload")}
              className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors"
            >
              Upload an Audio File
            </button>
            <button
              onClick={() => onNavigate("record")}
              className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition-colors"
            >
              Record Voice
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl divide-y divide-slate-800/80 overflow-hidden">
          {history.map((record) => (
            <div
              key={record.id}
              onClick={() => onSelectRecord(record)}
              className="p-4 sm:p-5 flex items-center justify-between hover:bg-slate-800/40 cursor-pointer transition-colors"
            >
              <div className="flex items-center gap-4 min-w-0 pr-4">
                <div className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center text-slate-400 shrink-0">
                  <FileAudio className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white truncate">{record.fileName}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {new Date(record.timestamp).toLocaleDateString()} &bull;{" "}
                    {new Date(record.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &bull;{" "}
                    {record.durationSec}s
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-4 shrink-0">
                <div className="text-right hidden sm:block">
                  <div className="text-xs font-semibold text-slate-300">
                    AI Likelihood: {record.aiLikelihood}%
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Naturalness: {record.voiceNaturalness}%
                  </div>
                </div>

                {getVerdictBadge(record)}

                <ArrowRight className="w-4 h-4 text-slate-500" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
