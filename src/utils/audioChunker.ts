/**
 * Audio Chunker Utility for Phase 7A: Simulated Real-Time Voice Analysis.
 * 
 * Slices an input audio file into ~4.0-second sequential chunk windows using the browser's
 * Web Audio API (AudioContext) and encodes each slice into a standard 16-bit PCM WAV Blob (16kHz Mono)
 * suitable for the VoiceShield backend preprocessing & inference pipeline.
 */

import { AudioChunkWindow } from "../types";

/**
 * Encodes Float32Array PCM audio samples into a standard 16-bit PCM WAV Blob.
 */
export function encodePcmWav(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bytesPerSample = 2; // 16-bit PCM
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  // Helper to write ASCII strings
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  // RIFF identifier
  writeString(0, "RIFF");
  // RIFF chunk length
  view.setUint32(4, 36 + dataSize, true);
  // RIFF type
  writeString(8, "WAVE");
  // format chunk identifier
  writeString(12, "fmt ");
  // format chunk length
  view.setUint32(16, 16, true);
  // sample format (1 = PCM)
  view.setUint16(20, 1, true);
  // channel count
  view.setUint16(22, numChannels, true);
  // sample rate
  view.setUint32(24, sampleRate, true);
  // byte rate
  view.setUint32(28, byteRate, true);
  // block align
  view.setUint16(32, blockAlign, true);
  // bits per sample
  view.setUint16(34, 16, true);
  // data chunk identifier
  writeString(36, "data");
  // data chunk length
  view.setUint32(40, dataSize, true);

  // Write PCM audio samples (clamped 16-bit signed integers)
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * Resamples an AudioBuffer to 16,000 Hz Mono Float32Array using standard linear interpolation.
 */
export function resampleTo16kMono(audioBuffer: AudioBuffer): { samples: Float32Array; sampleRate: number } {
  const targetSampleRate = 16000;
  const originalSampleRate = audioBuffer.sampleRate;
  const numChannels = audioBuffer.numberOfChannels;
  const originalLength = audioBuffer.length;

  // Mix down channels to mono Float32Array
  let monoOriginal: Float32Array;
  if (numChannels === 1) {
    monoOriginal = audioBuffer.getChannelData(0);
  } else {
    monoOriginal = new Float32Array(originalLength);
    for (let c = 0; c < numChannels; c++) {
      const channelData = audioBuffer.getChannelData(c);
      for (let i = 0; i < originalLength; i++) {
        monoOriginal[i] += channelData[i] / numChannels;
      }
    }
  }

  if (originalSampleRate === targetSampleRate) {
    return { samples: monoOriginal, sampleRate: targetSampleRate };
  }

  // Resample to targetSampleRate
  const ratio = originalSampleRate / targetSampleRate;
  const targetLength = Math.round(originalLength / ratio);
  const resampled = new Float32Array(targetLength);

  for (let i = 0; i < targetLength; i++) {
    const origIndex = i * ratio;
    const indexLow = Math.floor(origIndex);
    const indexHigh = Math.min(indexLow + 1, originalLength - 1);
    const weight = origIndex - indexLow;
    resampled[i] = monoOriginal[indexLow] * (1 - weight) + monoOriginal[indexHigh] * weight;
  }

  return { samples: resampled, sampleRate: targetSampleRate };
}

/**
 * Slices an audio file into sequential ~4.0-second chunk windows.
 * 
 * @param file The audio File or Blob to slice.
 * @param targetChunkDurationSec The duration of each chunk window (default: 4.0s).
 * @param minLastChunkDurationSec Minimum required duration for the final trailing chunk (default: 1.0s).
 */
export async function sliceAudioIntoWindows(
  file: File | Blob,
  targetChunkDurationSec = 4.0,
  minLastChunkDurationSec = 1.0
): Promise<AudioChunkWindow[]> {
  const arrayBuffer = await file.arrayBuffer();
  
  // Use AudioContext to decode audio format
  const audioContext = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
  
  let audioBuffer: AudioBuffer;
  try {
    audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  } finally {
    if (audioContext.state !== "closed") {
      audioContext.close().catch(() => {});
    }
  }

  const { samples: pcm16k, sampleRate } = resampleTo16kMono(audioBuffer);
  const totalDurationSec = pcm16k.length / sampleRate;
  const samplesPerChunk = Math.round(targetChunkDurationSec * sampleRate);
  const minSamplesLastChunk = Math.round(minLastChunkDurationSec * sampleRate);

  const chunkWindows: AudioChunkWindow[] = [];
  let chunkIndex = 0;
  let cursor = 0;

  while (cursor < pcm16k.length) {
    const endCursor = Math.min(cursor + samplesPerChunk, pcm16k.length);
    const chunkSamples = pcm16k.subarray(cursor, endCursor);
    const chunkLen = chunkSamples.length;

    // If trailing chunk is shorter than minLastChunkDurationSec and not the only chunk, pad or combine
    if (chunkLen < minSamplesLastChunk && chunkWindows.length > 0) {
      // Append remaining samples to the last chunk or pad to min length
      const padded = new Float32Array(samplesPerChunk);
      padded.set(chunkSamples);
      const startTimeSec = cursor / sampleRate;
      const endTimeSec = totalDurationSec;
      const wavBlob = encodePcmWav(padded, sampleRate);
      chunkWindows.push({
        index: chunkIndex,
        startTimeSec: Number(startTimeSec.toFixed(2)),
        endTimeSec: Number(endTimeSec.toFixed(2)),
        blob: wavBlob,
        filename: `chunk_${chunkIndex + 1}_${startTimeSec.toFixed(1)}s_${endTimeSec.toFixed(1)}s.wav`,
      });
      break;
    }

    const startTimeSec = cursor / sampleRate;
    const endTimeSec = endCursor / sampleRate;
    const wavBlob = encodePcmWav(chunkSamples, sampleRate);

    chunkWindows.push({
      index: chunkIndex,
      startTimeSec: Number(startTimeSec.toFixed(2)),
      endTimeSec: Number(endTimeSec.toFixed(2)),
      blob: wavBlob,
      filename: `chunk_${chunkIndex + 1}_${startTimeSec.toFixed(1)}s_${endTimeSec.toFixed(1)}s.wav`,
    });

    cursor = endCursor;
    chunkIndex++;
  }

  return chunkWindows;
}
