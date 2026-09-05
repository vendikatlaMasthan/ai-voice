import React from "react";
import { AlertOctagon, RotateCcw, HelpCircle } from "lucide-react";

interface ErrorAlertProps {
  error: {
    message: string;
    error_type?: string;
    status?: number;
  };
  onReset: () => void;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({ error, onReset }) => {
  const getHelpTip = (errorType?: string) => {
    switch (errorType) {
      case "AudioTooShortError":
        return "The uploaded recording is shorter than 0.5 seconds. Minimum duration of 0.5s–30.0s is required for reliable feature extraction.";
      case "AudioSilentError":
        return "The audio file was detected as pure silence or very low background noise (< -45 dB energy). Please upload audio with audible speech.";
      case "AudioCorruptError":
      case "UnsupportedFormatError":
        return "The file header is corrupted or in an unsupported format. Please upload standard PCM WAV, FLAC, or MP3 files.";
      case "AudioTooLongError":
        return "The recording exceeds the maximum allowable duration of 30.0 seconds.";
      case "SpeakerNotEnrolledError":
        return "The claimed speaker ID does not exist in the active profile registry. Please enroll reference audio in the Speaker Profiles tab first.";
      default:
        return "Verify that the audio file is valid, has audible speech, and meets preprocessing constraints (0.5s–30.0s, 16kHz mono).";
    }
  };

  return (
    <div id="analysis-error-card" className="glass-card rounded-2xl p-6 sm:p-7 space-y-4 shadow-2xl border border-red-500/30 bg-red-950/20 backdrop-blur-xl">
      <div className="flex items-start gap-4">
        <div className="w-11 h-11 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400 shrink-0 mt-0.5 shadow-sm">
          <AlertOctagon className="w-6 h-6" />
        </div>
        <div className="space-y-1.5 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold font-mono px-2.5 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">
              {error.error_type || "ANALYSIS FAILED"}
            </span>
            {error.status && (
              <span className="text-[11px] font-mono text-slate-400 bg-white/5 px-2 py-0.5 rounded border border-white/10">
                HTTP {error.status}
              </span>
            )}
          </div>
          <h3 className="text-base font-bold text-white">
            Audio Preprocessing / Pipeline Exception
          </h3>
          <p className="text-xs text-red-300 leading-relaxed font-mono bg-black/40 p-3.5 rounded-xl border border-red-500/20 shadow-inner">
            {error.message}
          </p>
        </div>
      </div>

      <div className="p-4 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-300 flex items-start gap-3">
        <HelpCircle className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
        <div>
          <div className="font-bold text-white font-mono">Resolution Tip:</div>
          <div className="text-slate-400 mt-0.5 text-[11px] leading-relaxed font-mono">
            {getHelpTip(error.error_type)}
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <button
          id="btn-error-retry"
          onClick={onReset}
          className="px-5 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-xs flex items-center gap-2 shadow-lg transition-all squish-btn font-mono border border-white/10"
        >
          <RotateCcw className="w-4 h-4" />
          Try Another File / Re-upload
        </button>
      </div>
    </div>
  );
};


