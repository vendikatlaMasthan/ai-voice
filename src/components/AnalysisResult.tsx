import React, { useState, useRef } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  Play,
  Pause,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Globe,
  Radio,
  Music,
  Video,
  Mic,
  ShieldAlert,
  Info,
  CheckCircle2,
  Lock,
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
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
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

  // Safe mapping of classification to scientifically responsible verdict
  const getVerdict = (classification: ClassificationType) => {
    switch (classification) {
      case "GENUINE_LIVE":
        return {
          title: "LIKELY GENUINE",
          badgeColor: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
          cardBorder: "border-emerald-500/30 bg-emerald-950/10",
          icon: ShieldCheck,
          iconColor: "text-emerald-400",
          dotColor: "bg-emerald-400",
          explanation:
            "Acoustic characteristics and speech patterns align with authentic human voice. No significant synthetic cloning artifacts were identified in this sample.",
        };
      case "SYNTHETIC_AI_GENERATED":
        return {
          title: "POSSIBLE AI-GENERATED VOICE",
          badgeColor: "bg-rose-500/15 text-rose-400 border-rose-500/30",
          cardBorder: "border-rose-500/30 bg-rose-950/10",
          icon: AlertTriangle,
          iconColor: "text-rose-400",
          dotColor: "bg-rose-400",
          explanation:
            record.input_type === "video"
              ? "Strong acoustic indicators of synthetic speech synthesis were detected in the audio extracted from this video."
              : "Strong acoustic indicators of synthetic speech or voice cloning were detected in this audio sample.",
        };
      case "UNCERTAIN":
      case "REPLAYED_RECORDED":
      default:
        return {
          title: "UNABLE TO CONFIRM",
          badgeColor: "bg-amber-500/15 text-amber-400 border-amber-500/30",
          cardBorder: "border-amber-500/30 bg-amber-950/10",
          icon: HelpCircle,
          iconColor: "text-amber-400",
          dotColor: "bg-amber-400",
          explanation:
            "Acoustic features are borderline or ambiguous. The audio may be compressed, affected by background noise, or insufficient to reach a conclusive determination.",
        };
    }
  };

  const verdict = getVerdict(record.classification);
  const VerdictIcon = verdict.icon;

  const rawRisk = (record.risk_level || "Medium").toUpperCase();
  const riskLevel = rawRisk === "HIGH" ? "HIGH" : rawRisk === "LOW" ? "LOW" : "MEDIUM";

  const getRiskStyle = (level: string) => {
    switch (level) {
      case "HIGH":
        return {
          badge: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          text: "text-rose-400",
        };
      case "MEDIUM":
        return {
          badge: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          text: "text-amber-400",
        };
      case "LOW":
      default:
        return {
          badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          text: "text-emerald-400",
        };
    }
  };

  const riskStyle = getRiskStyle(riskLevel);

  // Input Type display
  const inputType = record.input_type || (record.fileName.toLowerCase().match(/\.(mp4|mov|mkv|webm|avi)$/) ? "video" : (record.fileName.startsWith("mic_") || record.fileName.startsWith("live_") ? "live" : "audio"));

  const getInputTypeLabel = () => {
    switch (inputType) {
      case "video":
        return (
          <span className="flex items-center gap-1.5 text-slate-300 font-medium">
            <Video className="w-4 h-4 text-purple-400" /> Video Audio Track
          </span>
        );
      case "live":
        return (
          <span className="flex items-center gap-1.5 text-slate-300 font-medium">
            <Mic className="w-4 h-4 text-blue-400" /> Live Microphone
          </span>
        );
      case "audio":
      default:
        return (
          <span className="flex items-center gap-1.5 text-slate-300 font-medium">
            <Music className="w-4 h-4 text-emerald-400" /> Audio Recording
          </span>
        );
    }
  };

  // Detected language formatting
  const rawLang = record.detected_language || "";
  const isUnclearLang = !rawLang || rawLang === "Unable to confidently identify language" || rawLang === "Unclear" || rawLang === "Unknown" || rawLang === "Silence";
  const displayLanguage = isUnclearLang
    ? "Unable to confidently identify language"
    : rawLang;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Top Bar: Back Action & ID */}
      <div className="flex items-center justify-between">
        <button
          onClick={onAnalyzeAnother}
          className="text-xs font-semibold text-slate-400 hover:text-white flex items-center gap-2 transition-colors px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700"
        >
          <ArrowLeft className="w-3.5 h-3.5 text-indigo-400" /> Analyze Another File
        </button>
        <span className="text-xs font-mono text-slate-500">
          Scan: {record.id}
        </span>
      </div>

      {/* Long Recording Notice if applicable */}
      {(record.is_long_recording || record.user_notice) && (
        <div className="p-3.5 rounded-2xl bg-indigo-950/40 border border-indigo-500/30 flex items-start gap-3 text-xs text-indigo-200">
          <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-white">Notice: </span>
            {record.user_notice || "Long recording detected. A speech segment was selected for analysis."}
          </div>
        </div>
      )}

      {/* Main Analysis Card */}
      <div className={`rounded-3xl border p-6 sm:p-8 space-y-6 ${verdict.cardBorder} transition-all`}>
        {/* Header: Title & Meta */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-white/5">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              {inputType === "video" ? "Voice Analysis From Video" : "Voice Analysis Result"}
            </div>
            <div className="text-sm text-slate-400 mt-1 truncate max-w-md">
              Target: <span className="text-slate-200 font-medium">{record.fileName}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="px-3 py-1 rounded-full bg-white/5 border border-white/10">
              {getInputTypeLabel()}
            </div>
          </div>
        </div>

        {/* Spoken Language Banner */}
        <div className="flex items-center gap-2.5 p-3 rounded-xl bg-slate-900/70 border border-slate-800 text-xs">
          <Globe className="w-4 h-4 text-sky-400 shrink-0" />
          <span className="text-slate-400">Detected Language:</span>
          <span className={`font-semibold ${isUnclearLang ? "text-slate-400 italic" : "text-white"}`}>
            {displayLanguage}
          </span>
          {record.language_confidence !== undefined && record.language_confidence >= 0.4 && (
            <span className="text-[10px] font-mono text-slate-500 ml-auto">
              ({Math.round(record.language_confidence * 100)}% match)
            </span>
          )}
        </div>

        {/* Primary Verdict Banner */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-2xl bg-black/40 border border-white/10">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
              <VerdictIcon className={`w-7 h-7 ${verdict.iconColor}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${verdict.dotColor} animate-pulse`} />
                <h1 className="text-lg sm:text-xl font-bold tracking-tight text-white">
                  {verdict.title}
                </h1>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Acoustic analysis completed with deterministic models.
              </p>
            </div>
          </div>

          {/* Risk Level Badge */}
          <div className="sm:text-right">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
              Assessed Risk
            </span>
            <span className={`inline-block px-3.5 py-1 rounded-full text-xs font-bold border uppercase tracking-wider ${riskStyle.badge}`}>
              Risk: {riskLevel}
            </span>
          </div>
        </div>

        {/* Responsible Verdict Explanation */}
        <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800/80 text-xs text-slate-300 leading-relaxed">
          {verdict.explanation}
        </div>

        {/* Action Guidance Checklist: WHAT SHOULD YOU DO? */}
        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-200">
            <ShieldAlert className={`w-4 h-4 ${riskStyle.text}`} />
            WHAT SHOULD YOU DO?
          </div>

          {riskLevel === "HIGH" ? (
            <ul className="space-y-2 text-xs text-rose-200/90">
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">✕</span>
                <span><strong>Do not share OTPs</strong> or security verification codes with anyone.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">✕</span>
                <span><strong>Do not share passwords</strong>, PINs, or banking login credentials.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">✕</span>
                <span><strong>Do not transfer money immediately</strong>, even if the caller claims an urgent emergency.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">✓</span>
                <span><strong>Verify the caller independently</strong> through known phone numbers or in-person confirmation.</span>
              </li>
            </ul>
          ) : riskLevel === "MEDIUM" ? (
            <ul className="space-y-2 text-xs text-amber-200/90">
              <li className="flex items-start gap-2">
                <span className="text-amber-400 font-bold">!</span>
                <span><strong>Exercise caution</strong> with unexpected financial, legal, or personal requests.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-amber-400 font-bold">!</span>
                <span><strong>Verify caller identity</strong> using established official phone numbers before taking action.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-amber-400 font-bold">!</span>
                <span><strong>Do not reveal sensitive information</strong> if audio quality is compressed or unusual.</span>
              </li>
            </ul>
          ) : (
            <ul className="space-y-2 text-xs text-emerald-200/90">
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">✓</span>
                <span>Speech characteristics align with natural human voice patterns.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">✓</span>
                <span>Standard caution remains recommended for sensitive financial requests.</span>
              </li>
            </ul>
          )}
        </div>

        {/* Audio Player if available */}
        {record.audioUrl && (
          <div className="flex items-center justify-between pt-2 border-t border-white/5">
            <audio
              ref={audioRef}
              src={record.audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
            <button
              onClick={togglePlay}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold transition-colors"
            >
              {isPlaying ? (
                <Pause className="w-3.5 h-3.5 text-indigo-400" />
              ) : (
                <Play className="w-3.5 h-3.5 text-indigo-400" />
              )}
              {isPlaying ? "Pause Inspected Clip" : "Play Inspected Voice Clip"}
            </button>
            <span className="text-[11px] text-slate-500 font-mono">
              Duration: {record.durationSec ? `${record.durationSec.toFixed(1)}s` : "Standard window"}
            </span>
          </div>
        )}

        {/* Technical Details Collapsible Accordion */}
        <div className="pt-2 border-t border-white/5">
          <button
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="w-full flex items-center justify-between py-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
          >
            <span className="flex items-center gap-1.5">
              {showTechnicalDetails ? (
                <ChevronDown className="w-4 h-4 text-indigo-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-indigo-400" />
              )}
              Technical Details
            </span>
            <span className="text-[11px] font-mono text-slate-500">
              {showTechnicalDetails ? "Click to collapse" : "Click to inspect raw metrics"}
            </span>
          </button>

          {showTechnicalDetails && (
            <div className="mt-3 p-4 rounded-2xl bg-black/40 border border-slate-800 space-y-3 text-xs animate-in fade-in duration-200">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-slate-300">
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Detection Engine</span>
                  <span className="font-mono text-white font-semibold">
                    {record.detection_source || "Acoustic (AASIST / Wav2Vec2)"}
                  </span>
                </div>
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Synthetic Probability</span>
                  <span className="font-mono text-white font-semibold">
                    {record.spoofProbability !== undefined ? `${(record.spoofProbability * 100).toFixed(1)}%` : "N/A"}
                  </span>
                </div>
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Processed Audio Duration</span>
                  <span className="font-mono text-white font-semibold">
                    {record.durationSec !== undefined ? `${record.durationSec.toFixed(2)}s` : "Standard window"}
                  </span>
                </div>
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Replay Score</span>
                  <span className="font-mono text-white font-semibold">
                    {record.sub_scores?.replay_channel_score !== undefined
                      ? `${record.sub_scores.replay_channel_score}/100`
                      : "0/100"}
                  </span>
                </div>
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Language Code</span>
                  <span className="font-mono text-white font-semibold uppercase">
                    {record.language_code || "N/A"}
                  </span>
                </div>
                <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/60">
                  <span className="text-[11px] text-slate-500 block">Estimated SNR / Sample Rate</span>
                  <span className="font-mono text-white font-semibold">
                    {record.audio_metadata?.estimated_snr_db !== undefined
                      ? `${record.audio_metadata.estimated_snr_db} dB`
                      : "Standard"} @ 16kHz Mono
                  </span>
                </div>
              </div>

              {record.flags && record.flags.length > 0 && (
                <div className="pt-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">
                    Inspection Flags
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {record.flags.map((flag, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/80 text-slate-300 border border-slate-700/50"
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Action button */}
      <div className="text-center pt-2">
        <button
          onClick={onAnalyzeAnother}
          className="px-6 py-3 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/20"
        >
          Analyze Another Audio or Video
        </button>
      </div>
    </div>
  );
};
