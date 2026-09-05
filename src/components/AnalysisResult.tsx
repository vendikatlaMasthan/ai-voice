import React, { useState, useRef } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  Play,
  Pause,
  ArrowLeft,
  Volume2,
  Info,
  CheckCircle2,
  XCircle,
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

  const getVerdictPresentation = () => {
    switch (record.verdict) {
      case "GENUINE_LIVE":
        return {
          title: "Genuine Live Voice",
          badgeColor: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          cardBorder: "border-emerald-500/40 bg-emerald-950/10",
          icon: ShieldCheck,
          iconColor: "text-emerald-400",
          summary: "This voice shows natural acoustic characteristics consistent with an authentic live human speaker.",
        };
      case "SYNTHETIC_AI":
        return {
          title: "Synthetic AI-Generated Voice",
          badgeColor: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          cardBorder: "border-rose-500/40 bg-rose-950/10",
          icon: AlertTriangle,
          iconColor: "text-rose-400",
          summary: "This voice exhibits digital synthesis patterns characteristic of deepfake voice generators and voice clones.",
        };
      case "REPLAYED_RECORDED":
        return {
          title: "Replayed or Recorded Voice",
          badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          cardBorder: "border-amber-500/40 bg-amber-950/10",
          icon: Volume2,
          iconColor: "text-amber-400",
          summary: "This voice contains reverberation or speaker artifacts indicating it was played from a loudspeaker rather than spoken live.",
        };
      default:
        return {
          title: "Uncertain Voice Sample",
          badgeColor: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
          cardBorder: "border-yellow-500/40 bg-yellow-950/10",
          icon: HelpCircle,
          iconColor: "text-yellow-400",
          summary: "The audio quality or vocal characteristics are inconclusive. A clearer sample is recommended for verification.",
        };
    }
  };

  const presentation = getVerdictPresentation();
  const IconComponent = presentation.icon;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Back button & title */}
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
                Inspected: <span className="text-slate-300 font-medium">{record.fileName}</span> &bull; Duration:{" "}
                <span className="text-slate-300 font-medium">{record.durationSec}s</span>
              </p>
            </div>
          </div>

          <span className={`px-4 py-1.5 rounded-full text-xs font-bold border uppercase tracking-wide ${presentation.badgeColor}`}>
            {record.verdictLabel}
          </span>
        </div>

        {/* Plain English Explanation */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 text-blue-400" /> Explanation
          </div>
          <p className="text-sm text-slate-200 leading-relaxed">{record.explanation}</p>
        </div>

        {/* Recommended Action */}
        <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-700/60 flex items-start gap-3">
          {record.verdict === "GENUINE_LIVE" ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          )}
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Recommended Action</div>
            <div className="text-sm font-semibold text-white mt-0.5">{record.recommendedAction}</div>
          </div>
        </div>
      </div>

      {/* 3 Sub-Scores in Plain English */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* 1. AI Generation Likelihood */}
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
            Probability that this voice was generated or cloned by an artificial intelligence model.
          </p>
        </div>

        {/* 2. Voice Naturalness */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Voice Naturalness</span>
            <span
              className={`text-xs font-bold ${
                record.voiceNaturalness > 60
                  ? "text-emerald-400"
                  : record.voiceNaturalness > 35
                  ? "text-yellow-400"
                  : "text-rose-400"
              }`}
            >
              {record.voiceNaturalness}%
            </span>
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                record.voiceNaturalness > 60
                  ? "bg-emerald-500"
                  : record.voiceNaturalness > 35
                  ? "bg-yellow-500"
                  : "bg-rose-500"
              }`}
              style={{ width: `${record.voiceNaturalness}%` }}
            />
          </div>

          <p className="text-[11px] text-slate-400 leading-normal">
            Evaluates whether the voice has natural rhythm, breathing pauses, and pitch variations typical of human speech.
          </p>
        </div>

        {/* 3. Audio Clarity */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Audio Clarity</span>
            <span
              className={`text-xs font-bold ${
                record.audioClarity === "Clear"
                  ? "text-emerald-400"
                  : record.audioClarity === "Moderate"
                  ? "text-yellow-400"
                  : "text-rose-400"
              }`}
            >
              {record.audioClarity}
            </span>
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                record.audioClarity === "Clear"
                  ? "bg-emerald-500 w-full"
                  : record.audioClarity === "Moderate"
                  ? "bg-yellow-500 w-2/3"
                  : "bg-rose-500 w-1/3"
              }`}
            />
          </div>

          <p className="text-[11px] text-slate-400 leading-normal">
            Quality and background noise level of the audio recording. Clear audio provides the highest accuracy.
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
              <div className="text-xs text-slate-400">Listen to the inspected voice sample</div>
            </div>
            <audio
              ref={audioRef}
              src={record.audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
          </div>

          {/* Simple waveform graphic representation */}
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
