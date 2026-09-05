/**
 * VoiceShield AI — Telephony & VoIP Audio Integration Adapter
 * Bridges enterprise PBX, SIP trunks, and contact center telephony gateways
 * to VoiceShield real-time deepfake & fraud prevention engine.
 *
 * Handles:
 * - 8kHz G.711 / standard narrowband telephony -> 16kHz linear PCM16 upsampling
 * - Call metadata ingestion (caller ANI, callee DNIS, SIP trunk ID)
 * - Forwarding to VoiceShield streaming WebSocket or REST API
 */

export interface TelephonyCallMetadata {
  callId: string;
  callerAni?: string;       // Inbound caller telephone number
  calleeDnis?: string;      // Destination dialed number
  sipTrunkId?: string;      // VoIP gateway / SIP trunk identifier
  claimedIdentity?: string; // Caller claimed name/id
  claimedRole?: string;     // Caller claimed executive or customer role
  requestedAmount?: number; // Transaction wire amount if conversational IVR
  language?: string;        // Language code hint
}

export class TelephonyAudioAdapter {
  /**
   * Resamples 8kHz 16-bit linear PCM mono audio to 16kHz 16-bit linear PCM mono
   * using linear band-limited interpolation.
   */
  public static resample8kHzTo16kHz(input8kHz: Int16Array | Uint8Array | Buffer): Int16Array {
    let int16In: Int16Array;
    if (input8kHz instanceof Int16Array) {
      int16In = input8kHz;
    } else if (Buffer.isBuffer(input8kHz) || input8kHz instanceof Uint8Array) {
      int16In = new Int16Array(
        input8kHz.buffer,
        input8kHz.byteOffset,
        input8kHz.byteLength / 2
      );
    } else {
      throw new Error("Unsupported audio buffer format for telephony resampling.");
    }

    const inLen = int16In.length;
    if (inLen === 0) return new Int16Array(0);

    const outLen = inLen * 2;
    const output16kHz = new Int16Array(outLen);

    for (let i = 0; i < inLen; i++) {
      const current = int16In[i];
      const next = i + 1 < inLen ? int16In[i + 1] : current;

      output16kHz[i * 2] = current;
      output16kHz[i * 2 + 1] = Math.round((current + next) / 2);
    }

    return output16kHz;
  }

  /**
   * Decodes G.711 mu-Law 8-bit audio sample to 16-bit linear PCM.
   */
  public static decodeMuLawSample(uVal: number): number {
    uVal = ~uVal & 0xff;
    let t = ((uVal & 0x0f) << 3) + 0x84;
    t <<= (uVal & 0x70) >> 4;
    return (uVal & 0x80) !== 0 ? 0x84 - t : t - 0x84;
  }

  /**
   * Decodes an 8kHz G.711 mu-law byte buffer to 16kHz linear PCM16.
   */
  public static decodeMuLawTo16kHz(muLawBytes: Uint8Array | Buffer): Int16Array {
    const len8k = muLawBytes.length;
    const linear8k = new Int16Array(len8k);
    for (let i = 0; i < len8k; i++) {
      linear8k[i] = this.decodeMuLawSample(muLawBytes[i]);
    }
    return this.resample8kHzTo16kHz(linear8k);
  }
}

/**
 * High-level Telephony Session Wrapper.
 * Bridges a PBX/VoIP call to VoiceShield's live stream engine.
 */
export class TelephonyCallSession {
  public metadata: TelephonyCallMetadata;
  public totalAudioMsProcessed: number = 0;
  private onPcm16ChunkReady?: (pcm16Chunk: Int16Array) => void;

  constructor(metadata: TelephonyCallMetadata) {
    this.metadata = metadata;
  }

  /**
   * Registers callback to receive 16kHz PCM chunks for VoiceShield streaming.
   */
  public onProcessedChunk(callback: (pcm16Chunk: Int16Array) => void): this {
    this.onPcm16ChunkReady = callback;
    return this;
  }

  /**
   * Ingests raw 8kHz telephony frame (e.g. 20ms G.711/PCM frame from RTP/SIP stream)
   * and dispatches 16kHz upsampled PCM chunk to VoiceShield.
   */
  public ingest8kHzChunk(raw8kPcm: Int16Array | Uint8Array | Buffer): Int16Array {
    const pcm16 = TelephonyAudioAdapter.resample8kHzTo16kHz(raw8kPcm);
    this.totalAudioMsProcessed += (raw8kPcm.length / 8); // 8 samples per ms at 8kHz

    if (this.onPcm16ChunkReady) {
      this.onPcm16ChunkReady(pcm16);
    }
    return pcm16;
  }
}
