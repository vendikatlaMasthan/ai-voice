import React, { useState, useRef } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Radio,
  HelpCircle,
  Play,
  Pause,
  ArrowLeft,
  Info,
  CheckCircle2,
  Cpu,
  Layers,
  Activity,
} from "lucide-react";
import { AnalysisRecord, ClassificationType } from "../types";

interface AnalysisResultProps {
  record: AnalysisRecord;
  onAnalyzeAnother: () => void;
}

export const AnalysisResult: React.FC<AnalysisResultProps> = ({
  record,
  onAnalyzeAnother,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const getPresentation = (classification: ClassificationType) => {
    switch (classification) {
      case "GENUINE_LIVE":
        return {
          title: "Genuine Live Human Voice",
          badgeText: "GENUINE LIVE",
          badgeColor: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          cardBorder: "border-emerald-500/40 bg-emerald-950/10",
          icon: ShieldCheck,
          iconColor: "text-emerald-400",
        };
      case "SYNTHETIC_AI_GENERATED":
        return {
          title: "Synthetic AI Generated Voice",
          badgeText: "SYNTHETIC AI GENERATED",
          badgeColor: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          cardBorder: "border-rose-500/40 bg-rose-950/10",
          icon: AlertTriangle,
          iconColor: "text-rose-400",
        };
      case "REPLAYED_RECORDED":
        return {
          title: "Replayed / Recorded Voice",
          badgeText: "REPLAYED RECORDED",
          badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          cardBorder: "border-amber-500/40 bg-amber-950/10",
          icon: Radio,
          iconColor: "text-amber-400",
        };
      case "UNCERTAIN":
      default:
        return {
          title: "Uncertain / Inconclusive Acoustics",
          badgeText: "UNCERTAIN",
          badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          cardBorder: "border-amber-500/40 bg-amber-950/10",
          icon: HelpCircle,
          iconColor: "text-amber-400",
        };
    }
  };

  const presentation = getPresentation(record.classification);
  const IconComponent = presentation.icon;

  const sub = record.sub_scores || {
    synthetic_voice_score: record.aiLikelihood || 0,
    replay_channel_score: 0,
    naturalness_score: 50,
  };

  const getRiskBadge = (level: string) => {
    switch (level?.toLowerCase()) {
      case "high":
        return "bg-rose-500/20 text-rose-300 border-rose-500/40";
      case "medium":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40";
      default:
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Back button & scan metadata */}
      <div className="flex items-center justify-between">
        <button
          onClick={onAnalyzeAnother}
          className="text-xs font-semibold text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Check Another Audio
        </button>
        <span className="text-xs font-mono text-slate-500">Scan ID: {record.id}</span>
      </div>

      {/* Main Verdict Card */}
      <div className={`rounded-3xl border p-6 sm:p-8 space-y-6 ${presentation.cardBorder}`}>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
              <IconComponent className={`w-8 h-8 ${presentation.iconColor}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold text-white">{presentation.title}</h1>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Inspected File: <span className="text-slate-300 font-medium">{record.fileName}</span>
              </p>
              {/* Detection Source Badge per SPEC.md */}
              <p className="text-xs text-indigo-400 font-semibold mt-1.5 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5" />
                Detection Source: <span className="text-white font-mono uppercase bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-700/50">{record.detection_source}</span>
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:items-end gap-2">
            <span className={`px-4 py-1.5 rounded-full text-xs font-bold border uppercase tracking-wide ${presentation.badgeColor}`}>
              {presentation.badgeText}
            </span>
            <span className={`px-3 py-1 rounded-md text-[11px] font-semibold border uppercase tracking-wide ${getRiskBadge(record.risk_level)}`}>
              Risk Level: {record.risk_level || "Medium"}
            </span>
          </div>
        </div>

        {/* Explanation text */}
        <p className="text-sm text-slate-300 bg-black/20 p-4 rounded-xl border border-white/5 leading-relaxed">
          {record.explanation}
        </p>

        {/* Sub-Scores Panel per SPEC.md */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
          {/* Synthetic Voice Score */}
          <div className="bg-slate-900/60 border border-slate-800 p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-400" /> Synthetic Score
              </span>
              <span className="text-white font-bold font-mono">{sub.synthetic_voice_score}/100</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-rose-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, sub.synthetic_voice_score))}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-500">Cloned / synthesized artifact confidence</p>
          </div>

          {/* Replay Channel Score */}
          <div className="bg-slate-900/60 border border-slate-800 p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
              <span className="flex items-center gap-1.5">
                <Radio className="w-3.5 h-3.5 text-amber-400" /> Replay Score
              </span>
              <span className="text-white font-bold font-mono">{sub.replay_channel_score}/100</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-amber-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, sub.replay_channel_score))}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-500">Loudspeaker & acoustic reflections</p>
          </div>

          {/* Naturalness Score */}
          <div className="bg-slate-900/60 border border-slate-800 p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
              <span className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-emerald-400" /> Naturalness Score
              </span>
              <span className="text-white font-bold font-mono">{sub.naturalness_score}/100</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, sub.naturalness_score))}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-500">Vocal tract dynamics & prosodic variation</p>
          </div>
        </div>

        {/* Audio Player & Recommended Action */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-white/5">
          {record.audioUrl ? (
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <audio ref={audioRef} src={record.audioUrl} onEnded={() => setIsPlaying(false)} className="hidden" />
              <button
                onClick={togglePlay}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold transition-colors"
              >
                {isPlaying ? <Pause className="w-4 h-4 text-indigo-400" /> : <Play className="w-4 h-4 text-indigo-400" />}
                {isPlaying ? "Pause Recording" : "Play Inspected Clip"}
              </button>
            </div>
          ) : <div />}

          <div className="text-xs text-right text-slate-400 w-full sm:w-auto">
            Action: <span className="text-indigo-300 font-semibold">{record.recommendedAction}</span>
          </div>
        </div>

        {/* Model Calibration Note per SPEC.md */}
        {record.detection_source === "aasist" && (
          <div className="p-3 bg-slate-900/40 rounded-xl border border-slate-800 flex items-start gap-2 text-[11px] text-slate-400">
            <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <span>
              <strong>AASIST Architecture Note:</strong> Model was trained on ASVspoof2019 dataset. Outputs are calibrated in conjunction with prosodic and channel metrics.
            </span>
          </div>
        )}
      </div>

      {/* Flags section */}
      {record.flags && record.flags.length > 0 && (
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-5 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Inspection Flags</h3>
          <ul className="space-y-2">
            {record.flags.map((flag, idx) => (
              <li key={idx} className="flex items-center gap-2 text-xs text-slate-300">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
