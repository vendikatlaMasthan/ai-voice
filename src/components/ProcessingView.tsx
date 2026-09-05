import React, { useState, useEffect } from "react";
import { Mic, AudioWaveform, Cpu, Fingerprint, ShieldAlert, Loader2, CheckCircle2 } from "lucide-react";

interface ProcessingViewProps {
  currentStage?: number;
}

export const ProcessingView: React.FC<ProcessingViewProps> = () => {
  const statuses = [
    "Decoding acoustic signatures...",
    "Isolating background noise & calculating SNR...",
    "Checking for synthetic patterns (Wav2Vec2)...",
    "Extracting 192-D biometric embedding (ECAPA-TDNN)...",
    "Fusing multi-signal risk assessment..."
  ];

  const [statusIndex, setStatusIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStatusIndex((prev) => (prev + 1) % statuses.length);
    }, 2400);
    return () => clearInterval(interval);
  }, [statuses.length]);

  const stages = [
    {
      title: "Audio Preprocessing & Normalization",
      desc: "Resampling to 16 kHz Mono, silence removal (< -45 dB), and signal-to-noise ratio (SNR) calculation.",
      icon: AudioWaveform,
      color: "text-blue-400",
      bgColor: "bg-blue-500/10",
      borderColor: "border-blue-500/20",
    },
    {
      title: "Deepfake Feature Extraction",
      desc: "Transformer acoustic feature analysis (Wav2Vec2) computing synthetic artifact likelihood (P_fake).",
      icon: Cpu,
      color: "text-amber-400",
      bgColor: "bg-amber-500/10",
      borderColor: "border-amber-500/20",
    },
    {
      title: "Biometric Speaker Verification",
      desc: "192-D ECAPA-TDNN neural embedding extraction and cosine similarity verification against voice profile.",
      icon: Fingerprint,
      color: "text-purple-400",
      bgColor: "bg-purple-500/10",
      borderColor: "border-purple-500/20",
    },
    {
      title: "Multi-Signal Risk Fusion Engine",
      desc: "Mathematical risk scoring fusion (w1*P_fake + w2*M + w3*A + w4*C) and deterministic context rules evaluation.",
      icon: ShieldAlert,
      color: "text-emerald-400",
      bgColor: "bg-emerald-500/10",
      borderColor: "border-emerald-500/20",
    },
  ];

  return (
    <div id="processing-view-card" className="glass-card rounded-2xl overflow-hidden shadow-2xl border border-white/10 space-y-6">
      
      {/* Top Header */}
      <div className="p-6 border-b border-white/10 flex justify-between items-center bg-black/20">
        <div>
          <h2 className="text-xl font-bold text-white">
            Analyzing Audio Stream...
          </h2>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            Pipeline: 4-Stage Multi-Signal Verification
          </p>
        </div>
        <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shadow-sm">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      </div>

      {/* Stitch Radar Sweep Visualizer Container */}
      <div className="px-6 py-2 flex flex-col items-center justify-center">
        <div className="w-full bg-gradient-to-br from-[#051322] to-[#0d1f33] rounded-2xl p-8 border border-white/10 shadow-inner flex flex-col items-center justify-center relative overflow-hidden min-h-[300px]">
          
          {/* Radar Animation Area */}
          <div className="relative w-44 h-44 border border-blue-500/30 rounded-full flex items-center justify-center my-2">
            <div className="absolute w-full h-full border border-cyan-400/20 rounded-full pulse-ring" />
            <div className="absolute w-3/4 h-3/4 border border-cyan-400/25 rounded-full" />
            <div className="absolute w-1/2 h-1/2 border border-cyan-400/35 rounded-full" />
            
            {/* Spinning Radar Conic Sweep */}
            <div className="radar-sweep" />

            {/* Central Mic Icon */}
            <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-full flex items-center justify-center relative z-10 shadow-[0_0_25px_rgba(56,189,248,0.7)] border border-white/20">
              <Mic className="w-7 h-7 text-white" />
            </div>
          </div>

          {/* Typewriter Status Pill */}
          <div className="mt-6 text-center w-full max-w-md bg-black/60 backdrop-blur-md px-4 py-2.5 rounded-xl border border-white/10 shadow-lg">
            <p className="text-xs font-mono text-cyan-300 font-semibold tracking-wide">
              &gt; {statuses[statusIndex]}
            </p>
          </div>
        </div>
      </div>

      {/* 4 Pipeline Stages Breakdown */}
      <div className="px-6 pb-6 grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {stages.map((stage, idx) => {
          const Icon = stage.icon;
          return (
            <div
              key={idx}
              className="p-3.5 rounded-xl bg-white/5 border border-white/10 flex items-start gap-3 shadow-sm hover:bg-white/10 transition-colors"
            >
              <div className={`w-8 h-8 rounded-lg ${stage.bgColor} border ${stage.borderColor} flex items-center justify-center ${stage.color} shrink-0 mt-0.5`}>
                <Icon className="w-4 h-4" />
              </div>
              <div className="space-y-0.5 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-400 font-bold">
                    STAGE 0{idx + 1}
                  </span>
                  <h4 className="text-xs font-bold text-slate-200">
                    {stage.title}
                  </h4>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  {stage.desc}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Privacy Notice Footer */}
      <div className="px-6 py-3 bg-black/20 border-t border-white/10 flex items-center justify-between text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5 font-medium text-slate-300">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          Zero Raw Audio Retention: Audio processed in-memory and purged immediately.
        </span>
        <span className="font-mono text-slate-400">16kHz Mono &bull; FP16 Inference</span>
      </div>

    </div>
  );
};


