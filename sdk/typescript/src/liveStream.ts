/**
 * VoiceShield AI — TypeScript Live Stream Client
 * Manages WebSocket connection to /ws/live-stream with binary PCM streaming.
 */

import {
  AnalyzeResult,
  LiveStreamErrorEvent,
  LiveStreamOptions,
  LiveStreamResultEvent,
  LiveStreamSessionReadyEvent,
} from "./types";

export type ResultListener = (result: AnalyzeResult, windowIndex: number) => void;
export type ErrorListener = (error: string) => void;
export type ReadyListener = (readyInfo: LiveStreamSessionReadyEvent) => void;
export type CloseListener = () => void;

export class VoiceShieldLiveStream {
  private ws: any = null;
  private wsUrl: string;
  private options: LiveStreamOptions;
  private apiKey?: string;
  private resultListeners: Set<ResultListener> = new Set();
  private errorListeners: Set<ErrorListener> = new Set();
  private readyListeners: Set<ReadyListener> = new Set();
  private closeListeners: Set<CloseListener> = new Set();
  private isClosed = false;

  constructor(
    wsUrl: string,
    options: LiveStreamOptions = {},
    apiKey?: string,
    WebSocketClass?: any
  ) {
    this.wsUrl = wsUrl;
    this.options = options;
    this.apiKey = apiKey;

    const WS =
      WebSocketClass ||
      (typeof WebSocket !== "undefined"
        ? WebSocket
        : typeof (globalThis as any).WebSocket !== "undefined"
        ? (globalThis as any).WebSocket
        : null);

    if (!WS) {
      throw new Error(
        "WebSocket implementation not found. In Node.js environments, provide WebSocketClass or use a polyfill (e.g. 'ws')."
      );
    }

    this.initWebSocket(WS);
  }

  private initWebSocket(WS: any) {
    try {
      this.ws = new WS(this.wsUrl);
      if (this.ws.binaryType !== undefined) {
        this.ws.binaryType = "arraybuffer";
      }

      this.ws.onopen = () => {
        // Send initial start/config handshake payload
        const configMsg = {
          type: "config",
          session_id: this.options.sessionId || `SDK-SES-${Date.now()}`,
          speaker_id: this.options.speakerId,
          threshold: this.options.threshold,
          window_duration_sec: this.options.windowDurationSec || 1.5,
          context: this.options.context || {},
        };
        this.sendJson(configMsg);
      };

      this.ws.onmessage = (event: any) => {
        try {
          const rawData = typeof event.data === "string" ? event.data : event.data.toString?.();
          const parsed = JSON.parse(rawData);

          if (parsed.type === "session_ready") {
            const readyEvt = parsed as LiveStreamSessionReadyEvent;
            this.readyListeners.forEach((fn) => fn(readyEvt));
          } else if (parsed.type === "analysis_result") {
            const resEvt = parsed as LiveStreamResultEvent;
            this.resultListeners.forEach((fn) => fn(resEvt.data, resEvt.window_index));
          } else if (parsed.type === "analysis_error") {
            const errEvt = parsed as LiveStreamErrorEvent;
            this.errorListeners.forEach((fn) => fn(errEvt.error));
          }
        } catch (parseErr) {
          // Ignore non-JSON or internal ping/pong
        }
      };

      this.ws.onerror = (err: any) => {
        const errorMsg = err?.message || "WebSocket connection error.";
        this.errorListeners.forEach((fn) => fn(errorMsg));
      };

      this.ws.onclose = () => {
        this.isClosed = true;
        this.closeListeners.forEach((fn) => fn());
      };
    } catch (e: any) {
      this.errorListeners.forEach((fn) => fn(e.message || "Failed to initialize WebSocket."));
    }
  }

  /**
   * Registers a callback invoked whenever a live analysis result is computed for an audio window.
   */
  public onResult(listener: ResultListener): this {
    this.resultListeners.add(listener);
    return this;
  }

  /**
   * Registers a callback invoked on error.
   */
  public onError(listener: ErrorListener): this {
    this.errorListeners.add(listener);
    return this;
  }

  /**
   * Registers a callback invoked when the backend session is initialized and ready.
   */
  public onReady(listener: ReadyListener): this {
    this.readyListeners.add(listener);
    return this;
  }

  /**
   * Registers a callback invoked when the stream connection closes.
   */
  public onClose(listener: CloseListener): this {
    this.closeListeners.add(listener);
    return this;
  }

  /**
   * Streams raw 16kHz Little-Endian PCM16 audio bytes into the server's analysis window.
   * Can accept Int16Array, Uint8Array, ArrayBuffer, or Node Buffer.
   */
  public sendPcm(pcmData: Int16Array | Uint8Array | ArrayBuffer): void {
    if (this.isClosed || !this.ws || this.ws.readyState !== 1 /* OPEN */) {
      return;
    }

    if (pcmData instanceof Int16Array) {
      this.ws.send(pcmData.buffer);
    } else if (pcmData instanceof Uint8Array) {
      this.ws.send(pcmData.buffer);
    } else if (pcmData instanceof ArrayBuffer) {
      this.ws.send(pcmData);
    } else {
      this.ws.send(pcmData);
    }
  }

  /**
   * Dynamically updates call context (e.g. claimed role, requested amount, transcript keywords).
   */
  public updateContext(context: Record<string, any>): void {
    if (this.isClosed || !this.ws || this.ws.readyState !== 1) {
      return;
    }
    this.sendJson({
      type: "update_context",
      context,
    });
  }

  private sendJson(obj: Record<string, any>): void {
    if (this.ws && this.ws.readyState === 1) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  /**
   * Gracefully terminates the live stream WebSocket session.
   */
  public close(): void {
    this.isClosed = true;
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {
        // ignore
      }
    }
  }
}
