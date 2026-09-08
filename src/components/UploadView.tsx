import React, { useState, useRef } from "react";
import {
  UploadCloud,
  FileAudio,
  FileVideo,
  Play,
  Pause,
  Loader2,
  ShieldCheck,
  AlertCircle,
  Video,
  Music,
} from "lucide-react";
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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isVideoFile, setIsVideoFile] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const checkIsVideo = (file: File): boolean => {
    if (file.type && file.type.startsWith("video/")) return true;
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    return ["mp4", "mov", "mkv", "webm", "avi"].includes(ext);
  };

  const handleFile = (file: File) => {
    setSelectedFile(file);
    setSelectedSampleName(file.name);
    const isVid = checkIsVideo(file);
    setIsVideoFile(isVid);

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));
    setIsPlaying(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
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
      handleFile(file);
    } catch (err) {
      console.error("Failed to load sample:", err);
    }
  };

  const togglePlayback = () => {
    if (isVideoFile && videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
      } else {
        videoRef.current.play();
        setIsPlaying(true);
      }
      return;
    }

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
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Upload Audio or Video
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload any audio clip or video recording to detect voice cloning, synthetic speech, and spoken language.
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <div className="font-semibold">Unable to analyze media</div>
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
            ? "border-indigo-500/60 bg-indigo-950/20"
            : "border-slate-800 hover:border-indigo-500/40 hover:bg-slate-900/40 bg-slate-900/20"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,video/*,.wav,.mp3,.m4a,.flac,.aac,.ogg,.mp4,.mov,.mkv,.webm"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="w-16 h-16 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 flex items-center justify-center mx-auto mb-4 shadow-sm">
          {isVideoFile ? <Video className="w-8 h-8" /> : <UploadCloud className="w-8 h-8" />}
        </div>

        <h3 className="text-base sm:text-lg font-semibold text-white">
          {selectedFile ? selectedFile.name : "Drag & drop an audio or video file here"}
        </h3>
        <p className="text-xs sm:text-sm text-slate-400 mt-1">
          {selectedFile
            ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • ${isVideoFile ? "Video file" : "Audio file"}`
            : "or click to browse your computer"}
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 text-[11px] text-slate-400 mt-4">
          <span className="flex items-center gap-1 bg-slate-900/80 px-2.5 py-1 rounded-full border border-slate-800">
            <Music className="w-3 h-3 text-indigo-400" /> Audio: WAV, MP3, M4A, FLAC, AAC, OGG
          </span>
          <span className="flex items-center gap-1 bg-slate-900/80 px-2.5 py-1 rounded-full border border-slate-800">
            <Video className="w-3 h-3 text-purple-400" /> Video: MP4, MOV, MKV, WEBM
          </span>
        </div>
      </div>

      {/* Media Preview & Notice */}
      {selectedFile && previewUrl && (
        <div className="space-y-3">
          {isVideoFile && (
            <div className="p-3.5 rounded-xl bg-purple-950/30 border border-purple-500/30 text-xs text-purple-200 flex items-start gap-2.5">
              <Video className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
              <div>
                <strong>Video Audio Analysis:</strong> The audio track will be extracted and analyzed for synthetic speech and spoken language. Visual video deepfake detection is not performed.
              </div>
            </div>
          )}

          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4 w-full sm:w-auto">
              <button
                onClick={togglePlayback}
                className="w-12 h-12 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center shrink-0 transition-colors shadow-sm"
                aria-label={isPlaying ? "Pause media" : "Play media"}
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>

              <div className="min-w-0">
                <div className="text-sm font-semibold text-white truncate flex items-center gap-2">
                  {isVideoFile ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950 border border-purple-500/40 text-purple-300 font-mono uppercase">
                      VIDEO
                    </span>
                  ) : (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 border border-indigo-500/40 text-indigo-300 font-mono uppercase">
                      AUDIO
                    </span>
                  )}
                  <span className="truncate">{selectedSampleName}</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  Ready for AI voice analysis & language detection
                </div>
              </div>

              {isVideoFile ? (
                <video
                  ref={videoRef}
                  src={previewUrl}
                  onEnded={() => setIsPlaying(false)}
                  className="hidden"
                />
              ) : (
                <audio
                  ref={audioRef}
                  src={previewUrl}
                  onEnded={() => setIsPlaying(false)}
                  className="hidden"
                />
              )}
            </div>

            <button
              onClick={handleStartAnalysis}
              disabled={isProcessing}
              className="w-full sm:w-auto px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm shadow-md transition-all flex items-center justify-center gap-2 shrink-0 disabled:opacity-50"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Analyzing Voice...
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  Analyze Voice Authenticity
                </>
              )}
            </button>
          </div>
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
                        ? "bg-indigo-950/40 border-indigo-400/50"
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
