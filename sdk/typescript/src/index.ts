/**
 * VoiceShield AI — Official TypeScript SDK
 * Reusable client for banking, contact center, and enterprise voice security integrations.
 */

export { VoiceShieldClient } from "./client";
export {
  VoiceShieldLiveStream,
  type ResultListener,
  type ErrorListener,
  type ReadyListener,
  type CloseListener,
} from "./liveStream";
export * from "./types";
