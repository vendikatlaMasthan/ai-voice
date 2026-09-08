import React, { useState, useRef } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Play,
  Pause,
  ArrowLeft,
  Info,
  CheckCircle2,
  XCircle,
  Cpu,
} from "lucide-react";
import { AnalysisRecord } from "../types";

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

  const isSpoof = record.verdict === "SYNTHETIC_AI" || record.verdict === "SYNTHETIC_AI_GENERATED" || record.aiLikelihood >= 50;

  const presentation = isSpoof
    ? {
        title: "Spoof Voice Detected",
        badgeText: "Spoof (Synthetic / Cloned)",
        badgeColor: "bg-rose-500/20 text-rose-300 border-rose-500/40",
        cardBorder: "border-rose-500/40 bg-rose-950/10",
        icon: AlertTriangle,
        iconColor: "text-rose-400",
      }
    : {
        title: "Bonafide Voice Verified",
        badgeText: "Bonafide (Genuine Human)",
        badgeColor: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
        cardBorder: "border-emerald-500/40 bg-emerald-950/10",
        icon: ShieldCheck,
        iconColor: "text-emerald-400",
      };

  const IconComponent = presentation.icon;

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
                Inspected: <span className="text-slate-300 font-medium">{record.fileName}</span>
              </p>
              {/* Official Model Attribution Caption */}
              <p className="text-xs text-indigo-400 font-semibold mt-1.5 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5" />
                Powered by AASIST — trained on ASVspoof2019.
              </p>
            </div>
          </div>

          <span className={`px-4 py-1.5 rounded-full text-xs font-bold border uppercase tracking-wide ${presentation.badgeColor}`}>
            {presentation.badgeText}
          </span>
        </div>

        {/* Neural Network Explanation */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 text-blue-400" /> AASIST Classification Summary
          </div>
          <p className="text-sm text-slate-200 leading-relaxed">{record.explanation}</p>
        </div>

        {/* Recommended Action */}
        <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-700/60 flex items-start gap-3">
          {isSpoof ? (
            <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          )}
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Recommended Action</div>
            <div className="text-sm font-semibold text-white mt-0.5">{record.recommendedAction}</div>
          </div>
        </div>
      </div>

      {/* Real Response Fields Display */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* 1. AI Likelihood (Spoof Probability %) */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">AI Likelihood</span>
            <span
              className={`text-xs font-bold ${
                record.aiLikelihood > 60
                  ? "text-rose-400"
                  : record.aiLikelihood > 30
                  ? "text-yellow-400"
                  : "text-emerald-400"
              }`}
            >
              {record.aiLikelihood}%
            </span>
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                record.aiLikelihood > 60
                  ? "bg-rose-500"
                  : record.aiLikelihood > 30
                  ? "bg-yellow-500"
                  : "bg-emerald-500"
              }`}
              style={{ width: `${record.aiLikelihood}%` }}
            />
          </div>

          <p className="text-[11px] text-slate-400 leading-normal">
            Calculated directly from AASIST raw softmax spoof probability: {record.spoofProbability ?? (record.aiLikelihood / 100)}.
          </p>
        </div>

        {/* 2. Bonafide Probability */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Bonafide Probability</span>
            <span
              className={`text-xs font-bold ${
                (record.bonafideProbability ?? (1 - record.aiLikelihood / 100)) > 0.6
                  ? "text-emerald-400"
                  : "text-slate-400"
              }`}
            >
              {Math.round((record.bonafideProbability ?? (1 - record.aiLikelihood / 100)) * 100)}%
            </span>
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="h-full rounded-full transition-all bg-emerald-500"
              style={{
                width: `${Math.round((record.bonafideProbability ?? (1 - record.aiLikelihood / 100)) * 100)}%`,
              }}
            />
          </div>

          <p className="text-[11px] text-slate-400 leading-normal">
            Confidence score that this speech sample originates from a living human vocal tract.
          </p>
        </div>

        {/* 3. Deep Learning Architecture */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Model Architecture</span>
            <span className="text-xs font-bold text-indigo-400">
              {record.modelName || "AASIST"}
            </span>
          </div>

          <div className="text-xs text-slate-300 font-mono bg-slate-800/60 p-2.5 rounded-lg border border-slate-700/50">
            Spectro-Temporal Graph Attention Network
          </div>

          <p className="text-[11px] text-slate-400 leading-normal">
            Evaluated on raw 16 kHz waveform with heterogeneous graph attention.
          </p>
        </div>
      </div>

      {/* Audio Waveform & Player */}
      {record.audioUrl && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={togglePlay}
              className="w-12 h-12 rounded-xl bg-blue-600 hover:bg-blue-500 text-white flex items-center justify-center shrink-0 transition-colors shadow-sm"
              aria-label={isPlaying ? "Pause playback" : "Play audio"}
            >
              {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
            </button>
            <div>
              <div className="text-sm font-semibold text-white">Audio Playback</div>
              <div className="text-xs text-slate-400">Listen to the inspected voice recording</div>
            </div>
            <audio
              ref={audioRef}
              src={record.audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
          </div>

          {/* Simple waveform visual */}
          <div className="hidden sm:flex items-center gap-1 h-8 opacity-60">
            {[40, 65, 85, 30, 70, 95, 50, 80, 60, 45, 90, 75, 55, 35, 80, 60, 40].map(
              (height, idx) => (
                <div
                  key={idx}
                  className="w-1 bg-blue-400 rounded-full"
                  style={{ height: `${height}%` }}
                />
              )
            )}
          </div>
        </div>
      )}

      {/* Action Footer */}
      <div className="flex justify-end pt-2">
        <button
          onClick={onAnalyzeAnother}
          className="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm shadow-md transition-colors"
        >
          Check Another Audio Sample
        </button>
      </div>
    </div>
  );
};
