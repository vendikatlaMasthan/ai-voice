import React, { useState, useRef, useEffect } from "react";
import {
  Mic,
  Square,
  Play,
  Pause,
  RotateCcw,
  ShieldCheck,
  Loader2,
  AlertCircle,
  Globe,
  Radio,
} from "lucide-react";

interface RecordViewProps {
  onAnalyze: (file: File | Blob, name: string) => Promise<void>;
  isProcessing: boolean;
  error: string | null;
}

type LiveMicState =
  | "idle"
  | "listening"
  | "speech_detected"
  | "detecting_language"
  | "analyzing_voice"
  | "analysis_complete";

export const RecordView: React.FC<RecordViewProps> = ({
  onAnalyze,
  isProcessing,
  error,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<LiveMicState>("idle");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stageTimerRef = useRef<any>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (stageTimerRef.current) clearTimeout(stageTimerRef.current);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioUrl]);

  // Manage stage progression during isProcessing
  useEffect(() => {
    if (isProcessing) {
      setCurrentState("detecting_language");
      stageTimerRef.current = setTimeout(() => {
        setCurrentState("analyzing_voice");
      }, 1500);
    } else {
      if (stageTimerRef.current) clearTimeout(stageTimerRef.current);
      if (currentState === "analyzing_voice") {
        setCurrentState("analysis_complete");
      }
    }
  }, [isProcessing]);

  const startRecording = async () => {
    setPermissionError(null);
    setRecordedBlob(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    audioChunksRef.current = [];
    setRecordingTime(0);
    setCurrentState("listening");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const actualMime = mimeType || mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: actualMime });
        setRecordedBlob(audioBlob);
        setAudioUrl(URL.createObjectURL(audioBlob));
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(250);
      setIsRecording(true);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => {
          const next = prev + 1;
          if (next >= 1) {
            setCurrentState("speech_detected");
          }
          return next;
        });
      }, 1000);
    } catch (err: any) {
      console.error("Microphone access error:", err);
      setCurrentState("idle");
      setPermissionError(
        err.message ||
          "Microphone access was denied. Please enable microphone permissions in your browser."
      );
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  const handleReset = () => {
    setIsRecording(false);
    setRecordedBlob(null);
    setRecordingTime(0);
    setCurrentState("idle");
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setIsPlaying(false);
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

  const handleAnalyzeRecordedVoice = async () => {
    if (!recordedBlob) return;
    if (recordingTime < 1) {
      setPermissionError("Recording is too short. Please speak for at least 1 second.");
      return;
    }
    const ext = recordedBlob.type.includes("mp4") ? "m4a" : "webm";
    const file = new File([recordedBlob], `mic_recording_${Date.now()}.${ext}`, {
      type: recordedBlob.type || "audio/webm",
    });
    await onAnalyze(file, file.name);
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remainingSec = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${remainingSec.toString().padStart(2, "0")}`;
  };

  const getStateBadge = () => {
    switch (currentState) {
      case "listening":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/40">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-ping" />
            Listening...
          </span>
        );
      case "speech_detected":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Speech detected...
          </span>
        );
      case "detecting_language":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/40">
            <Globe className="w-3.5 h-3.5 text-purple-400 animate-spin" />
            Detecting language...
          </span>
        );
      case "analyzing_voice":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
            <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
            Analyzing voice...
          </span>
        );
      case "analysis_complete":
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            Analysis complete.
          </span>
        );
      case "idle":
      default:
        return null;
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Live Microphone Verification
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Capture live voice to detect language and test for synthetic cloning or deepfake voice synthesis.
        </p>
      </div>

      {/* Permission / Notice */}
      {(permissionError || error) && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <div className="font-semibold">Microphone Notice</div>
            <div className="text-xs text-rose-300/80 mt-0.5">{permissionError || error}</div>
          </div>
        </div>
      )}

      {/* Recorder Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-8 sm:p-12 text-center space-y-6">
        {/* State Badge */}
        <div className="h-6 flex items-center justify-center">
          {getStateBadge()}
        </div>

        {/* Timer Display */}
        <div className="font-mono text-4xl sm:text-5xl font-extrabold text-white tracking-wider">
          {formatSeconds(recordingTime)}
        </div>

        {/* Pulse Indicator */}
        <div className="flex items-center justify-center">
          <div
            className={`w-28 h-28 rounded-full flex items-center justify-center transition-all ${
              isRecording
                ? "bg-rose-500/20 border-2 border-rose-500 shadow-xl shadow-rose-500/30 animate-pulse"
                : "bg-slate-800/60 border border-slate-700"
            }`}
          >
            <Mic className={`w-12 h-12 ${isRecording ? "text-rose-400" : "text-slate-400"}`} />
          </div>
        </div>

        {/* Control Buttons */}
        <div className="flex items-center justify-center gap-4 pt-2">
          {!isRecording && !recordedBlob && (
            <button
              onClick={startRecording}
              className="px-8 py-3.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2"
            >
              <Mic className="w-4 h-4" />
              Start Recording
            </button>
          )}

          {isRecording && (
            <button
              onClick={stopRecording}
              className="px-8 py-3.5 rounded-2xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-sm shadow-lg shadow-rose-500/20 transition-all flex items-center gap-2"
            >
              <Square className="w-4 h-4 fill-current" />
              Stop Recording
            </button>
          )}

          {recordedBlob && (
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={togglePlayback}
                className="px-5 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-sm transition-colors flex items-center gap-2"
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                {isPlaying ? "Pause Preview" : "Play Recording"}
              </button>

              <button
                onClick={handleReset}
                className="px-4 py-3 rounded-xl bg-slate-800/60 hover:bg-slate-700/60 text-slate-300 hover:text-white text-sm transition-colors flex items-center gap-1.5"
              >
                <RotateCcw className="w-4 h-4" />
                Re-record
              </button>

              <button
                onClick={handleAnalyzeRecordedVoice}
                disabled={isProcessing || recordingTime < 1}
                className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {currentState === "detecting_language" ? "Detecting language..." : "Analyzing voice..."}
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4" />
                    Analyze Recorded Voice
                  </>
                )}
              </button>

              {audioUrl && (
                <audio
                  ref={audioRef}
                  src={audioUrl}
                  onEnded={() => setIsPlaying(false)}
                  className="hidden"
                />
              )}
            </div>
          )}
        </div>

        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          {isRecording
            ? "Speak clearly. Recommended duration: 3 to 10 seconds of speech."
            : recordedBlob
            ? "Recording captured! Click Play to listen or Analyze to verify authenticity."
            : "Click 'Start Recording' when you are ready to speak."}
        </p>
      </div>
    </div>
  );
};
