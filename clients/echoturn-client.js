// The browser client, in one import.
//
// Two ways to use this, and they are both supported on purpose.
//
// `Call` is the whole conversation: a microphone, a turn's audio played in
// order, subtitles as they arrive, and the three decisions in between - when a
// pause ends a turn, what counts as talking over the reply, and what to do with
// the audio heard while the reply was being made. A page that wants a voice
// call and nothing else needs this one export.
//
// The rest are the parts it is built from, because a page that already has its
// own conversation state - or its own player, or its own microphone handling -
// should be able to take the piece it needs rather than the whole thing. They
// are modules with no state of their own, so mixing them is not a second
// implementation of anything.
//
// Loading the microphone needs `worklet.js` next to this file; the client
// resolves it from its own URL, so copying the directory is enough.

export { FALLBACK, Dials } from "./dials.js";
export { FALLBACK_BLOCK, Microphone, WORKLET_NAME, WORKLET_URL } from "./mic.js";
export { LEAD_SEC, PlaybackQueue } from "./queue.js";
export { DROP, KEEP, PROBE, SEND, SilenceCursor } from "./cursor.js";
export { FLOOR, LevelTracker, percentile } from "./levels.js";
export { EchoTracker, GUARD_MS } from "./echo.js";
export { InterruptGate } from "./interrupt.js";
export { PREROLL_MS, FrameRing, carryMs } from "./ring.js";
export { NO_VOICE_GIVE_UP_MS } from "./cursor.js";
export {
  TRANSCRIBE_PATH,
  TURN_PATH,
  askService,
  splitFrames,
  streamTurn,
} from "./stream.js";
export { bytesFromBase64, toBase64 } from "./base64.js";
export { ASR_RATE, encodeWav, flatten, resample, wav16k } from "./wav.js";
export {
  Call,
  IDLE,
  LISTENING,
  NO_TRANSCRIPT,
  SPEAKING,
  THINKING,
  meterValue,
} from "./call.js";
