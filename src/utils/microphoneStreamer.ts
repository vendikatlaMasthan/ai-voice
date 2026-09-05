/**
 * VoiceShield Live Microphone Streaming Engine.
 * 
 * Captures browser microphone audio via getUserMedia(), resamples to 16 kHz mono PCM16,
 * and streams raw audio packets over WebSocket to the backend /ws/live-stream pipeline.
 */

import { CallContextState, LiveStreamAnalysisResult } from "../types";

export interface MicrophoneStreamConfig {
  speakerId?: string;
  threshold?: number;
  context?: CallContextState;
  windowDurationSec?: number;
  onResult: (result: LiveStreamAnalysisResult) => void;
  onVolume: (rmsDb: number, peak: number) => void;
  onStatusChange: (status: "connecting" | "listening" | "error" | "closed", message?: string) => void;
}

export class MicrophoneStreamer {
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private socket: WebSocket | null = null;
  private isStreaming: boolean = false;
  private config: MicrophoneStreamConfig;
  private heartbeatTimer: any = null;
  private fileStreamTimer: any = null;

  constructor(config: MicrophoneStreamConfig) {
    this.config = config;
  }

  public updateContext(newContext: Partial<CallContextState>, speakerId?: string, threshold?: number) {
    if (speakerId !== undefined) this.config.speakerId = speakerId;
    if (threshold !== undefined) this.config.threshold = threshold;
    if (newContext && this.config.context) {
      this.config.context = { ...this.config.context, ...newContext };
    }

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(
          JSON.stringify({
            type: "config",
            speaker_id: this.config.speakerId || null,
            threshold: this.config.threshold,
            context: this.config.context,
            window_duration_sec: this.config.windowDurationSec || 1.5,
          })
        );
      } catch (e: any) {
        console.warn("[MicrophoneStreamer] Failed to send context update:", e.message);
      }
    }
  }

  public async start(): Promise<void> {
    if (this.isStreaming) {
      return;
    }

    this.config.onStatusChange("connecting", "Connecting to live WebSocket stream (/ws/live-stream)...");

    try {
      // 1. Establish WebSocket Connection
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host || "localhost:3000";
      const wsUrl = `${protocol}//${host}/ws/live-stream`;

      const ws = new WebSocket(wsUrl);
      this.socket = ws;
      ws.binaryType = "arraybuffer";

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error("WebSocket connection timeout to " + wsUrl));
        }, 10000);

        ws.onopen = () => {
          clearTimeout(timeout);
          resolve();
        };

        ws.onerror = (_err) => {
          clearTimeout(timeout);
          reject(new Error("WebSocket connection failed. Verify server is running on port 3000."));
        };
      });

      // Send initial configuration handshake
      ws.send(
        JSON.stringify({
          type: "start",
          speaker_id: this.config.speakerId || null,
          threshold: this.config.threshold,
          context: this.config.context,
          window_duration_sec: this.config.windowDurationSec || 1.5,
        })
      );

      // Start keep-alive heartbeat ping every 10s
      this.heartbeatTimer = setInterval(() => {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
          try {
            this.socket.send(JSON.stringify({ type: "ping" }));
          } catch (e) {}
        }
      }, 10000);

      // Handle incoming analysis telemetry
      ws.onmessage = (event) => {
        try {
          if (typeof event.data === "string") {
            const msg = JSON.parse(event.data);
            if (msg.type === "analysis_result") {
              this.config.onResult(msg as LiveStreamAnalysisResult);
            } else if (msg.type === "session_warming_up") {
              this.config.onStatusChange("connecting", msg.message || "Local AI models warming up in memory...");
            } else if (msg.type === "session_ready") {
              this.config.onStatusChange("listening", "Microphone stream active. Analyzing live speech windows in real-time.");
            } else if (msg.type === "analysis_error") {
              console.warn("[MicrophoneStreamer:BackendError]", msg.error);
            } else if (msg.type === "pong" || msg.type === "connected") {
              // Heartbeat/handshake ack
            }
          }
        } catch (e: any) {
          console.warn("[MicrophoneStreamer] Error parsing server message:", e.message);
        }
      };

      ws.onclose = (event) => {
        if (this.isStreaming) {
          this.config.onStatusChange("closed", `Connection closed (code ${event.code})`);
          this.stop();
        }
      };

      // 2. Request User Microphone with fallback constraints
      let stream: MediaStream;
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("Browser mediaDevices API not available in this environment.");
        }
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      } catch (errPrimary: any) {
        // Fallback to basic audio constraint
        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (errFallback: any) {
          throw new Error(
            `Microphone access unavailable (${errFallback.message || errPrimary.message}). You can also stream test audio files directly over WebSocket.`
          );
        }
      }
      this.mediaStream = stream;

      // 3. Audio Processing Pipeline
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) {
        throw new Error("Web Audio API AudioContext not supported by this browser.");
      }
      const audioCtx = new AudioCtx();
      this.audioContext = audioCtx;

      if (audioCtx.state === "suspended") {
        await audioCtx.resume();
      }

      const source = audioCtx.createMediaStreamSource(stream);
      this.sourceNode = source;

      // ScriptProcessor buffer size: 4096 samples
      const bufferSize = 4096;
      const processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      this.processorNode = processor;

      const inputSampleRate = audioCtx.sampleRate;
      const targetSampleRate = 16000;

      processor.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!this.isStreaming || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
          return;
        }

        const inputChannelData = e.inputBuffer.getChannelData(0);

        // Compute volume / RMS for visualizer
        let sumSq = 0;
        let peak = 0;
        for (let i = 0; i < inputChannelData.length; i++) {
          const sample = inputChannelData[i];
          const abs = Math.abs(sample);
          if (abs > peak) peak = abs;
          sumSq += sample * sample;
        }
        const rms = Math.sqrt(sumSq / inputChannelData.length);
        const rmsDb = rms > 0.00001 ? 20 * Math.log10(rms) : -100;
        this.config.onVolume(rmsDb, peak);

        // Resample inputChannelData to 16,000 Hz if needed
        let resampled16k: Float32Array;
        if (inputSampleRate === targetSampleRate) {
          resampled16k = inputChannelData;
        } else {
          const ratio = inputSampleRate / targetSampleRate;
          const newLength = Math.round(inputChannelData.length / ratio);
          resampled16k = new Float32Array(newLength);
          for (let i = 0; i < newLength; i++) {
            const originalIndex = i * ratio;
            const idxFloor = Math.floor(originalIndex);
            const idxCeil = Math.min(inputChannelData.length - 1, idxFloor + 1);
            const fraction = originalIndex - idxFloor;
            resampled16k[i] = inputChannelData[idxFloor] * (1 - fraction) + inputChannelData[idxCeil] * fraction;
          }
        }

        // Convert Float32 [-1.0, 1.0] to signed 16-bit PCM integer buffer (little-endian)
        const pcm16Buffer = new Int16Array(resampled16k.length);
        for (let i = 0; i < resampled16k.length; i++) {
          const s = Math.max(-1.0, Math.min(1.0, resampled16k[i]));
          pcm16Buffer[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Send binary buffer directly to backend
        try {
          if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(pcm16Buffer.buffer);
          }
        } catch (sendErr: any) {
          console.warn("[MicrophoneStreamer] Failed to send audio chunk:", sendErr.message);
        }
      };

      // Connect graph: Source -> Processor -> Destination (muted)
      source.connect(processor);
      const muteGain = audioCtx.createGain();
      muteGain.gain.value = 0;
      processor.connect(muteGain);
      muteGain.connect(audioCtx.destination);

      this.isStreaming = true;
      this.config.onStatusChange("listening", "Microphone stream active. Analyzing live speech windows in real-time.");
    } catch (err: any) {
      this.stop();
      this.config.onStatusChange("error", err.message || "Failed to initialize microphone stream.");
      throw err;
    }
  }

  /**
   * Stream a test audio file/buffer over the WebSocket in real-time chunks (16kHz PCM16).
   */
  public async streamAudioFile(file: File | Blob): Promise<void> {
    if (this.isStreaming) {
      this.stop();
    }

    this.config.onStatusChange("connecting", "Connecting to live WebSocket stream for audio file playback...");

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host || "localhost:3000";
      const wsUrl = `${protocol}//${host}/ws/live-stream`;

      const ws = new WebSocket(wsUrl);
      this.socket = ws;
      ws.binaryType = "arraybuffer";

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("WebSocket timeout")), 10000);
        ws.onopen = () => {
          clearTimeout(timeout);
          resolve();
        };
        ws.onerror = () => {
          clearTimeout(timeout);
          reject(new Error("WebSocket connection failed."));
        };
      });

      ws.send(
        JSON.stringify({
          type: "start",
          speaker_id: this.config.speakerId || null,
          threshold: this.config.threshold,
          context: this.config.context,
          window_duration_sec: this.config.windowDurationSec || 1.5,
        })
      );

      ws.onmessage = (event) => {
        try {
          if (typeof event.data === "string") {
            const msg = JSON.parse(event.data);
            if (msg.type === "analysis_result") {
              this.config.onResult(msg as LiveStreamAnalysisResult);
            }
          }
        } catch (e) {}
      };

      ws.onclose = (event) => {
        if (this.isStreaming) {
          this.config.onStatusChange("closed", `Connection closed (code ${event.code})`);
          this.stop();
        }
      };

      // Decode audio file into AudioBuffer
      const arrayBuf = await file.arrayBuffer();
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      this.audioContext = audioCtx;
      if (audioCtx.state === "suspended") {
        await audioCtx.resume();
      }

      const decodedAudio = await audioCtx.decodeAudioData(arrayBuf);
      const inputChannelData = decodedAudio.getChannelData(0);
      const inputSampleRate = decodedAudio.sampleRate;
      const targetSampleRate = 16000;

      // Resample to 16kHz
      let resampled16k: Float32Array;
      if (inputSampleRate === targetSampleRate) {
        resampled16k = inputChannelData;
      } else {
        const ratio = inputSampleRate / targetSampleRate;
        const newLength = Math.round(inputChannelData.length / ratio);
        resampled16k = new Float32Array(newLength);
        for (let i = 0; i < newLength; i++) {
          const originalIndex = i * ratio;
          const idxFloor = Math.floor(originalIndex);
          const idxCeil = Math.min(inputChannelData.length - 1, idxFloor + 1);
          const fraction = originalIndex - idxFloor;
          resampled16k[i] = inputChannelData[idxFloor] * (1 - fraction) + inputChannelData[idxCeil] * fraction;
        }
      }

      this.isStreaming = true;
      this.config.onStatusChange("listening", "Streaming audio file chunks to WebSocket in real-time (16kHz PCM16)...");

      // Stream in 100ms packets (1600 samples = 3200 bytes)
      const packetSamples = 1600;
      let offset = 0;

      this.fileStreamTimer = setInterval(() => {
        if (!this.isStreaming || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
          clearInterval(this.fileStreamTimer);
          return;
        }

        if (offset >= resampled16k.length) {
          clearInterval(this.fileStreamTimer);
          this.config.onStatusChange("closed", "Audio file stream finished.");
          return;
        }

        const end = Math.min(resampled16k.length, offset + packetSamples);
        const slice = resampled16k.subarray(offset, end);
        offset = end;

        // Compute Volume
        let sumSq = 0;
        let peak = 0;
        for (let i = 0; i < slice.length; i++) {
          const s = slice[i];
          const abs = Math.abs(s);
          if (abs > peak) peak = abs;
          sumSq += s * s;
        }
        const rms = Math.sqrt(sumSq / slice.length);
        const rmsDb = rms > 0.00001 ? 20 * Math.log10(rms) : -100;
        this.config.onVolume(rmsDb, peak);

        const pcm16 = new Int16Array(slice.length);
        for (let i = 0; i < slice.length; i++) {
          const s = Math.max(-1.0, Math.min(1.0, slice[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        try {
          this.socket.send(pcm16.buffer);
        } catch (e) {}
      }, 100);

    } catch (err: any) {
      this.stop();
      this.config.onStatusChange("error", err.message || "Failed to stream audio file.");
      throw err;
    }
  }

  public stop(): void {
    this.isStreaming = false;

    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.fileStreamTimer) {
      clearInterval(this.fileStreamTimer);
      this.fileStreamTimer = null;
    }

    if (this.processorNode) {
      try {
        this.processorNode.disconnect();
      } catch (e) {}
      this.processorNode = null;
    }

    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch (e) {}
      this.sourceNode = null;
    }

    if (this.audioContext) {
      try {
        this.audioContext.close();
      } catch (e) {}
      this.audioContext = null;
    }

    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {}
      this.mediaStream = null;
    }

    if (this.socket) {
      try {
        if (this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(JSON.stringify({ type: "stop" }));
          this.socket.close(1000, "Normal Closure");
        }
      } catch (e) {}
      this.socket = null;
    }

    this.config.onStatusChange("closed", "Microphone stream stopped.");
  }
}

