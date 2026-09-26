import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DROP,
  KEEP,
  NO_VOICE_GIVE_UP_MS,
  PROBE,
  SEND,
  SilenceCursor,
} from "../cursor.js";
import { Dials } from "../dials.js";

const FRAME = 20; // ms; the meter's frames are shorter, the arithmetic is the same

function cursor(overrides = {}) {
  return new SilenceCursor({ dials: new Dials(overrides) });
}

/** Run frames of one kind and return every decision that was not KEEP. */
function run(cursor, { speech = false, ms = FRAME, now = 0 } = {}) {
  return cursor.observe({ dt: ms, speech, now });
}

function speak(cursor, ms, now = 0) {
  let last = KEEP;
  for (let spent = 0; spent < ms; spent += FRAME) last = run(cursor, { speech: true, now });
  return last;
}

/**
 * Stay quiet until something other than KEEP happens, or the budget runs out.
 *
 * Stops at the first decision that ends the recording: a real caller stops
 * there too, and a helper that keeps going reports the same turn being sent
 * over and over.
 */
function stayQuiet(cursor, budgetMs, now = 0) {
  const decisions = [];
  for (let spent = 0; spent <= budgetMs; spent += FRAME) {
    const decision = run(cursor, { now });
    if (decision === KEEP) continue;
    decisions.push({ decision, at: cursor.silenceMs });
    if (decision !== PROBE) break;
  }
  return decisions;
}

test("a pause with no verdict ends the turn at the plain threshold", () => {
  const c = cursor();
  speak(c, 400);
  const decisions = stayQuiet(c, 1200);
  assert.deepEqual(
    decisions.map((d) => d.decision),
    [PROBE, SEND],
  );
  assert.equal(decisions[1].at, 620);
});

test("a finished verdict sends as soon as the candidate pause is reached", () => {
  const c = cursor();
  speak(c, 400);
  c.noteVerdict(true);
  const decisions = stayQuiet(c, 1200);
  assert.deepEqual(decisions, [{ decision: SEND, at: 300 }]);
});

test("an unfinished verdict waits out the reopen window and then sends anyway", () => {
  // Silence already spent before the verdict does not count. A verdict arrives
  // most of a second late, so a window counted from the start of the silence
  // would be over before it began - a window that exists only in the source.
  const c = cursor();
  speak(c, 400);
  for (let spent = 0; spent < 1000; spent += FRAME) run(c);
  c.noteVerdict(false);
  const decisions = stayQuiet(c, 2000);
  assert.equal(decisions.length, 1);
  assert.equal(decisions[0].decision, SEND);
  assert.equal(decisions[0].at, 1800);
});

test("a call waits longer than a typed message before falling back", () => {
  const c = new SilenceCursor({ dials: new Dials(), inCall: true });
  speak(c, 400);
  const decisions = stayQuiet(c, 1200);
  assert.equal(decisions[decisions.length - 1].at, 720);
});

test("a call asks the service sooner than a typed message does", () => {
  // Both halves of the call pair move: the candidate pause comes earlier and
  // the deadline it races comes later, so the probe still lands before it.
  const c = new SilenceCursor({ dials: new Dials(), inCall: true });
  speak(c, 400);
  const decisions = stayQuiet(c, 1200);
  assert.deepEqual(decisions, [
    { decision: PROBE, at: 180 },
    { decision: SEND, at: 720 },
  ]);
});

test("a sound too short to be a sentence is thrown away, not sent", () => {
  // Sent, it reaches a recogniser, and a recogniser asked about a cough invents
  // a word rather than reporting that it heard nothing.
  const c = cursor();
  speak(c, 100);
  const decisions = stayQuiet(c, 1200);
  assert.deepEqual(decisions.map((d) => d.decision), [DROP]);
});

test("a cough never reaches the service as a question", () => {
  const c = cursor();
  speak(c, 100);
  const decisions = stayQuiet(c, 600);
  assert.ok(!decisions.some((d) => d.decision === PROBE));
});

test("the pause is asked about once, not once per frame", () => {
  const c = cursor();
  speak(c, 400);
  const decisions = stayQuiet(c, 400);
  assert.equal(decisions.filter((d) => d.decision === PROBE).length, 1);
});

test("speaking again makes the next pause askable again", () => {
  const c = cursor();
  speak(c, 400);
  assert.equal(stayQuiet(c, 400)[0].decision, PROBE);
  speak(c, 200);
  assert.equal(c.asked, false);
  assert.equal(c.verdict, null);
  const decisions = stayQuiet(c, 400);
  assert.equal(decisions[0].decision, PROBE);
});

test("the service's own speech measurement overrides the local one", () => {
  // The local count is frame levels; the service counted the waveform. When the
  // two disagree, the one that heard the audio is right.
  const c = cursor();
  speak(c, 500);
  c.noteVoiceMs(40);
  assert.equal(c.enough(), false);
  const decisions = stayQuiet(c, 1200);
  assert.deepEqual(decisions.map((d) => d.decision), [DROP]);

  const other = cursor();
  speak(other, 60);
  other.noteVoiceMs(900);
  assert.equal(other.enough(), true);
});

test("a service that measured nothing leaves the local count standing", () => {
  // Zero is a measurement - "there was no speech in this" - and it is not what
  // an absent field means. Read as zero, every answer that left the field out
  // would throw away a recording that was fine.
  const c = cursor();
  speak(c, 400);
  c.noteVoiceMs(null);
  assert.equal(c.voiceMs, null);
  assert.equal(c.enough(), true);
  c.noteVoiceMs("");
  assert.equal(c.voiceMs, null);
  c.noteVoiceMs(0);
  assert.equal(c.voiceMs, 0);
  assert.equal(c.enough(), false);
});

test("a recording nobody spoke into is abandoned", () => {
  const c = cursor();
  assert.equal(run(c, { now: 0 }), KEEP);
  assert.equal(run(c, { now: NO_VOICE_GIVE_UP_MS }), KEEP);
  assert.equal(run(c, { now: NO_VOICE_GIVE_UP_MS + 1 }), DROP);
});

test("a recording with speech in it is not abandoned for being quiet", () => {
  const c = cursor();
  speak(c, 400);
  for (let spent = 0; spent < 1000; spent += FRAME) run(c, { now: NO_VOICE_GIVE_UP_MS });
  // The turn ended on its own terms before the guard could fire.
  assert.equal(c.hasVoice, true);
});
