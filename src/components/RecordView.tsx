import React, { useState, useRef, useEffect } from "react";
import { Mic, Square, Play, Pause, RotateCcw, Sparkles, Loader2, AlertCircle } from "lucide-react";

interface RecordViewProps {
  onAnalyze: (file: File | Blob, name: string) => Promise<void>;
  isProcessing: boolean;
  error: string | null;
}

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

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioUrl]);

  const startRecording = async () => {
    setPermissionError(null);
    setRecordedBlob(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    audioChunksRef.current = [];
    setRecordingTime(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        setRecordedBlob(audioBlob);
        setAudioUrl(URL.createObjectURL(audioBlob));
        // Stop all tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(250);
      setIsRecording(true);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      console.error("Microphone access error:", err);
      setPermissionError(
        err.message || "Microphone access denied. Please enable microphone permissions in your browser."
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
    const file = new File([recordedBlob], `microphone_recording_${Date.now()}.wav`, {
      type: "audio/wav",
    });
    await onAnalyze(file, file.name);
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remainingSec = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${remainingSec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Record Voice Sample</h1>
        <p className="text-sm text-slate-400 mt-1">
          Speak into your microphone for 3 to 10 seconds to verify whether your voice is identified as live human speech.
        </p>
      </div>

      {/* Permission / General Error */}
      {(permissionError || error) && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <div className="font-semibold">Microphone Notice</div>
            <div className="text-xs text-rose-300/80 mt-0.5">{permissionError || error}</div>
          </div>
        </div>
      )}

      {/* Recorder Center Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-8 sm:p-12 text-center space-y-6">
        {/* Timer Display */}
        <div className="font-mono text-4xl sm:text-5xl font-extrabold text-white tracking-wider">
          {formatSeconds(recordingTime)}
        </div>

        {/* Pulse / Visual Cue */}
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
              className="px-8 py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-blue-500/20 transition-all flex items-center gap-2"
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
                disabled={isProcessing}
                className="px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-sm shadow-lg shadow-emerald-500/20 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Analyzing Voice...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
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
            ? "Recording in progress... speak clearly into your microphone."
            : recordedBlob
            ? "Recording captured! Click Play to listen or Analyze to verify authenticity."
            : "Click 'Start Recording' when you are ready to speak."}
        </p>
      </div>
    </div>
  );
};
