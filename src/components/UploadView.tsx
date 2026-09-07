import React, { useState, useRef } from "react";
import { UploadCloud, FileAudio, Play, Pause, Loader2, Sparkles, AlertCircle } from "lucide-react";
import { SampleAudio } from "../types";

interface UploadViewProps {
  samples: SampleAudio[];
  onAnalyze: (file: File | Blob, name: string) => Promise<void>;
  isProcessing: boolean;
  error: string | null;
}

export const UploadView: React.FC<UploadViewProps> = ({
  samples,
  onAnalyze,
  isProcessing,
  error,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedSampleName, setSelectedSampleName] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioPreviewUrl, setAudioPreviewUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setSelectedSampleName(file.name);
      if (audioPreviewUrl) URL.revokeObjectURL(audioPreviewUrl);
      setAudioPreviewUrl(URL.createObjectURL(file));
      setIsPlaying(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      setSelectedSampleName(file.name);
      if (audioPreviewUrl) URL.revokeObjectURL(audioPreviewUrl);
      setAudioPreviewUrl(URL.createObjectURL(file));
      setIsPlaying(false);
    }
  };

  const handleSelectSample = async (sample: SampleAudio) => {
    try {
      const res = await fetch(sample.url);
      if (!res.ok) {
        throw new Error(`Could not load sample audio (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const file = new File([blob], sample.filename, { type: blob.type || "audio/wav" });
      setSelectedFile(file);
      setSelectedSampleName(sample.filename);
      if (audioPreviewUrl) URL.revokeObjectURL(audioPreviewUrl);
      setAudioPreviewUrl(URL.createObjectURL(blob));
      setIsPlaying(false);
    } catch (err) {
      console.error("Failed to load sample:", err);
    }
  };

  const togglePlayback = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleStartAnalysis = async () => {
    if (!selectedFile) return;
    await onAnalyze(selectedFile, selectedSampleName || selectedFile.name);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Upload Audio File</h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload any recorded voice audio clip to verify whether it is genuine human speech or an AI clone.
        </p>
      </div>

      {/* Error Alert if any */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <div className="font-semibold">Unable to analyze audio</div>
            <div className="text-xs text-rose-300/80 mt-0.5">{error}</div>
          </div>
        </div>
      )}

      {/* Drag & Drop Area */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all ${
          selectedFile
            ? "border-blue-500/60 bg-blue-950/20"
            : "border-slate-800 hover:border-blue-500/40 hover:bg-slate-900/40 bg-slate-900/20"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,.wav,.mp3,.flac,.m4a"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="w-16 h-16 rounded-2xl bg-blue-500/15 border border-blue-500/30 text-blue-300 flex items-center justify-center mx-auto mb-4 shadow-sm">
          <UploadCloud className="w-8 h-8" />
        </div>

        <h3 className="text-base sm:text-lg font-semibold text-white">
          {selectedFile ? selectedFile.name : "Drag & drop an audio file here"}
        </h3>
        <p className="text-xs sm:text-sm text-slate-400 mt-1">
          {selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB selected` : "or click to browse your files"}
        </p>
        <p className="text-[11px] text-slate-500 mt-3 font-mono">
          Supported formats: WAV, MP3, FLAC, M4A &bull; Recommended: 3 to 15 seconds
        </p>
      </div>

      {/* Selected Audio Preview & Analyze CTA */}
      {selectedFile && audioPreviewUrl && (
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4 w-full sm:w-auto">
            <button
              onClick={togglePlayback}
              className="w-12 h-12 rounded-xl bg-blue-600 hover:bg-blue-500 text-white flex items-center justify-center shrink-0 transition-colors shadow-sm"
              aria-label={isPlaying ? "Pause audio" : "Play audio"}
            >
              {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
            </button>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white truncate">{selectedSampleName}</div>
              <div className="text-xs text-slate-400">Ready for inspection</div>
            </div>
            <audio
              ref={audioRef}
              src={audioPreviewUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
          </div>

          <button
            onClick={handleStartAnalysis}
            disabled={isProcessing}
            className="w-full sm:w-auto px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-md transition-all flex items-center justify-center gap-2 shrink-0 disabled:opacity-50"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analyzing Voice...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Analyze Voice Authenticity
              </>
            )}
          </button>
        </div>
      )}

      {/* Sample Audio Benchmarks for 1-click test */}
      {samples.length > 0 && (
        <div className="space-y-3 pt-4">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Or test with verified sample audio:
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {samples
              .filter((s) => s.filename.includes("real") || s.filename.includes("fake"))
              .slice(0, 4)
              .map((sample) => {
                const isReal = sample.filename.includes("real");
                const isSelected = selectedSampleName === sample.filename;

                return (
                  <div
                    key={sample.filename}
                    onClick={() => handleSelectSample(sample)}
                    className={`p-4 rounded-xl border text-left cursor-pointer transition-all flex items-center justify-between ${
                      isSelected
                        ? "bg-blue-950/40 border-blue-400/50"
                        : "bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-800/30"
                    }`}
                  >
                    <div className="min-w-0 pr-3">
                      <div className="text-sm font-semibold text-white flex items-center gap-2">
                        <FileAudio className="w-4 h-4 text-slate-400 shrink-0" />
                        <span className="truncate">{sample.filename}</span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1 truncate">
                        {sample.description || (isReal ? "Human speech sample" : "Synthetic voice clone")}
                      </div>
                    </div>

                    <span
                      className={`text-xs px-2.5 py-1 rounded-full font-semibold shrink-0 ${
                        isReal
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {isReal ? "Human" : "Synthetic"}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
};
