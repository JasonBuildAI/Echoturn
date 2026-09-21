import { test } from "node:test";
import assert from "node:assert/strict";

import * as client from "../echoturn-client.js";

// What a host is told it can import. A name that disappears from here is a
// breaking change for every page built on this client, and it is the kind of
// change that no test of the behaviour would notice.
const PUBLIC = [
  "ASR_RATE",
  "Call",
  "DROP",
  "Dials",
  "EchoTracker",
  "FALLBACK",
  "FALLBACK_BLOCK",
  "FLOOR",
  "FrameRing",
  "GUARD_MS",
  "IDLE",
  "InterruptGate",
  "KEEP",
  "LEAD_SEC",
  "LISTENING",
  "LevelTracker",
  "Microphone",
  "NO_TRANSCRIPT",
  "NO_VOICE_GIVE_UP_MS",
  "PROBE",
  "PREROLL_MS",
  "PlaybackQueue",
  "SEND",
  "SPEAKING",
  "SilenceCursor",
  "THINKING",
  "TRANSCRIBE_PATH",
  "TURN_PATH",
  "WORKLET_NAME",
  "WORKLET_URL",
  "askService",
  "bytesFromBase64",
  "carryMs",
  "encodeWav",
  "flatten",
  "meterValue",
  "percentile",
  "resample",
  "splitFrames",
  "streamTurn",
  "toBase64",
  "wav16k",
];

test("every name the entry point promises is exported", () => {
  const missing = PUBLIC.filter((name) => !(name in client));
  assert.deepEqual(missing, []);
});

test("nothing is exported to the browser that is not a module of its own", () => {
  for (const [name, value] of Object.entries(client)) {
    assert.ok(value !== undefined && value !== null, `${name} is empty`);
  }
});

test("the client is usable without a page: its pieces work on their own", () => {
  // The reason the pieces are exported at all. A host with its own player
  // should be able to take the cursor and leave the queue.
  const dials = new client.Dials({ vad_end_ms: 200 });
  const cursor = new client.SilenceCursor({ dials });
  for (let i = 0; i < 50; i += 1) cursor.observe({ dt: 20, speech: true });
  assert.equal(cursor.ready(), false);
});
