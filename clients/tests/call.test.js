import { test } from "node:test";
import assert from "node:assert/strict";

import { Call, IDLE, LISTENING, NO_TRANSCRIPT, SPEAKING, THINKING, meterValue } from "../call.js";
import { Dials } from "../dials.js";
import { FakeMic, fakeFetch, offlineStub } from "./fakes.js";

const FRAME_MS = 10;
const SPEECH = 0.5;
const QUIET = 0.001;
// A chunk the queue can actually decode. Real base64 matters here: a payload
// that will not decode is dropped by design, and a test that used one would be
// asserting about a dropped chunk while believing it was playing.
const CHUNK = btoa("\x00\x00\x00\x00");

/** A call wired to fakes, with its clock under the test's control. */
function build({
  turns = [],
  transcripts = [],
  config = {},
  mic = null,
  turnOk = true,
  ...options
} = {}) {
  const clock = { now: 1000 };
  const device = mic || new FakeMic({ clock });
  const { asked, fetchImpl } = fakeFetch({ turns, transcripts, config, turnOk });
  const states = [];
  const subtitles = [];
  const notices = [];
  const done = [];
  const levels = [];
  const call = new Call({
    microphone: device,
    dials: new Dials(config),
    clock: () => clock.now,
    fetch: fetchImpl,
    createContext: () => ({
      currentTime: 0,
      state: "running",
      destination: {},
      decodeAudioData: async () => ({ duration: 1 }),
      createBufferSource: () => ({ connect() {}, start() {}, stop() {} }),
    }),
    createOffline: offlineStub().createOffline,
    onState: (state) => states.push(state),
    onSubtitle: (text, index) => subtitles.push({ text, index }),
    onNotice: (text) => notices.push(text),
    onDone: (result) => done.push(result),
    onLevel: (value) => levels.push(value),
    ...options,
  });
  return { call, device, clock, asked, states, subtitles, notices, done, levels };
}

/** Speak for `ms`, then stay quiet for `ms`. */
async function utter(harness, { speechMs = 400, quietMs = 900, rms = SPEECH } = {}) {
  harness.device.feed(speechMs, { rms, frameMs: FRAME_MS });
  harness.device.feed(quietMs, { rms: QUIET, frameMs: FRAME_MS });
  await settle();
}

/** Let the promises the frame path started run to completion. */
async function settle(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

test("a level for the meter stays between nothing and full", () => {
  assert.equal(meterValue(0), 0);
  assert.equal(meterValue(-1), 0);
  assert.equal(meterValue(1), 1);
  assert.ok(meterValue(0.05) > 0 && meterValue(0.05) < 1);
});

test("starting loads the settings and opens the microphone", async () => {
  const { call, asked, device } = build({ config: { vad_end_ms: 750 } });
  assert.equal(await call.start(), true);
  assert.equal(asked.config.length, 1);
  assert.equal(device.opened, 1);
  assert.equal(call.dials.number("vad_end_ms"), 750);
});

test("a microphone that refuses is reported and does not start the call", async () => {
  const { call, notices } = build({ mic: new FakeMic({ opens: false }) });
  assert.equal(await call.start(), false);
  assert.deepEqual(notices, ["Permission denied"]);
  assert.equal(call.started, false);
});

test("a sentence followed by a pause becomes one turn", async () => {
  const { call, asked, device } = build({
    transcripts: [{ text: "hello there" }],
    turns: [[{ type: "done", reply: "Hello." }]],
  });
  await call.start();
  await utter({ device });
  assert.equal(asked.transcribe.length, 1, "the audio was recognised once");
  assert.equal(asked.turn.length, 1);
  assert.equal(asked.turn[0].body.text, "hello there");
  assert.equal(asked.turn[0].body.session, "default");
  assert.equal(asked.turn[0].body.voice_call, true);
  assert.equal(asked.turn[0].body.input_kind, "voice");
});

test("a verdict of finished sends the turn sooner than the fallback would", async () => {
  const { call, asked, device } = build({
    transcripts: [{ text: "done", turn: { complete: true } }],
    turns: [[{ type: "done", reply: "ok" }]],
  });
  await call.start();
  device.feed(400, { rms: SPEECH, frameMs: FRAME_MS });
  device.feed(300, { rms: QUIET, frameMs: FRAME_MS });
  await settle();
  device.feed(20, { rms: QUIET, frameMs: FRAME_MS });
  await settle();
  assert.equal(asked.turn.length, 1, "sent at the candidate pause, not the fallback");
});

test("a verdict of unfinished holds the turn back past the fallback", async () => {
  const { call, asked, device } = build({
    transcripts: [{ text: "half a", turn: { complete: false } }],
    turns: [[{ type: "done", reply: "go on" }]],
  });
  await call.start();
  device.feed(400, { rms: SPEECH, frameMs: FRAME_MS });
  device.feed(1200, { rms: QUIET, frameMs: FRAME_MS });
  await settle();
  assert.equal(asked.turn.length, 0, "not sent while the model says he is still talking");
});

test("a sound too short to be a sentence is not recognised or sent", async () => {
  const { call, asked, device } = build({ transcripts: [{ text: "hm" }] });
  await call.start();
  device.feed(60, { rms: SPEECH, frameMs: FRAME_MS });
  device.feed(1200, { rms: QUIET, frameMs: FRAME_MS });
  await settle();
  assert.equal(asked.turn.length, 0);
  assert.equal(asked.transcribe.length, 0, "a creak never reaches a recogniser");
});

test("the words of the reply arrive as subtitles before the audio does", async () => {
  const { call, subtitles, device } = build({
    transcripts: [{ text: "say it" }],
    turns: [
      [
        { type: "ack", id: "M1" },
        { type: "sentence", i: 0, text: "One." },
        { type: "audio", idx: 0, i: 0, data: "" },
        { type: "sentence", i: 1, text: "Two." },
        { type: "done", reply: "One. Two." },
      ],
    ],
  });
  await call.start();
  await utter({ device });
  assert.deepEqual(subtitles, [
    { text: "One.", index: 0 },
    { text: "Two.", index: 1 },
  ]);
});

test("the finished reply is reported once, and the call goes quiet again", async () => {
  const { call, done, states, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [[{ type: "sentence", i: 0, text: "Hi." }, { type: "done", reply: "Hi.", timings: { first: 0.2 } }]],
  });
  await call.start();
  await utter({ device });
  assert.equal(done.length, 1);
  assert.equal(done[0].reply, "Hi.");
  assert.deepEqual(done[0].timings, { first: 0.2 });
  assert.equal(call.state, IDLE);
  assert.ok(states.includes(LISTENING));
  assert.ok(states.includes(THINKING));
});

test("a chunk of audio is handed to the queue with its number", async () => {
  const played = [];
  const { call, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [
      [
        { type: "audio", idx: 1, i: 0, data: "b" },
        { type: "audio", idx: 0, i: 0, data: "a" },
        { type: "done", reply: "" },
      ],
    ],
  });
  call.queue.enqueue = async (idx, data) => played.push([idx, data]);
  await call.start();
  await utter({ device });
  assert.deepEqual(played, [[1, "b"], [0, "a"]]);
});

test("the reply is audible before its chunks have finished arriving", async () => {
  // The state is what a page shows, and it has to say "speaking" while sound
  // is coming out - not while the last sentence is still being fetched.
  const states = [];
  const { call, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [[{ type: "audio", idx: 0, i: 0, data: CHUNK }, { type: "done", reply: "" }]],
    onState: (state) => states.push(state),
  });
  await call.start();
  await utter({ device });
  assert.ok(states.includes(SPEAKING), `states were ${states}`);
});

test("the tail of the reply still counts as the reply", async () => {
  // The stream ends before the audio does. In that second the client is still
  // being heard through the microphone, and treating it as silence is how a
  // speaker ends up interrupting itself and answering its own last word.
  const { call, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [[{ type: "audio", idx: 0, i: 0, data: CHUNK }, { type: "done", reply: "" }]],
  });
  await call.start();
  await utter({ device });
  assert.equal(call.busy, false, "the turn is over");
  assert.equal(call.queue.speaking, true, "and the sound is not");
  // What the reply itself sends back: loud enough to be chatter, not to be heard.
  device.feed(600, { rms: 0.05, frameMs: FRAME_MS });
  assert.equal(call.capturing, false, "its own echo is not somebody talking");
  // Somebody talking over it, at a level and for a length that is.
  device.feed(900, { rms: 0.5, frameMs: FRAME_MS });
  assert.equal(call.capturing, true);
});

test("a failed turn is reported and leaves the call usable", async () => {
  const { call, notices, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [[{ type: "error", error: "the provider refused" }]],
  });
  await call.start();
  await utter({ device });
  assert.deepEqual(notices, ["the provider refused"]);
  assert.equal(call.state, IDLE);
  assert.equal(call.busy, false);
});

test("a service that fails outright is reported rather than swallowed", async () => {
  const { call, notices, device } = build({ transcripts: [{ text: "hi" }], turnOk: false });
  await call.start();
  await utter({ device });
  assert.equal(notices.length, 1);
  assert.match(notices[0], /500/);
});

test("a host that wants to stop the call on a failure is told first", async () => {
  const failures = [];
  const order = [];
  const { call, device } = build({
    transcripts: [{ text: "hi" }],
    turnOk: false,
    onError: (err) => {
      order.push("error");
      failures.push(err);
    },
    onNotice: () => order.push("notice"),
  });
  await call.start();
  await utter({ device });
  assert.equal(failures.length, 1);
  assert.match(failures[0].message, /500/);
  assert.deepEqual(order, ["error", "notice"]);
});

test("a recording with no words in it says so", async () => {
  const { call, notices, device } = build({ transcripts: [{ text: "" }] });
  await call.start();
  await utter({ device });
  assert.deepEqual(notices, [NO_TRANSCRIPT]);
});

test("muting stops the recording and drops what was in it", async () => {
  const { call, asked, device, levels } = build({ transcripts: [{ text: "hi" }] });
  await call.start();
  device.feed(200, { rms: SPEECH, frameMs: FRAME_MS });
  call.setMuted(true);
  assert.equal(call.capturing, false);
  device.feed(1000, { rms: SPEECH, frameMs: FRAME_MS });
  await settle();
  assert.equal(asked.turn.length, 0, "a muted call sends nothing, however loud it is");
  assert.equal(levels[levels.length - 1], 0);
  call.setMuted(false);
  await utter({ device });
  assert.equal(asked.turn.length, 1);
});

test("the level meter follows the microphone and stops when muted", async () => {
  const { call, device, levels } = build({});
  await call.start();
  device.feed(20, { rms: SPEECH, frameMs: FRAME_MS });
  assert.ok(levels.some((value) => value > 0));
  call.setMuted(true);
  assert.equal(levels[levels.length - 1], 0);
});

test("a typed message goes into the same conversation", async () => {
  const { call, asked } = build({
    turns: [[{ type: "done", reply: "yes" }]],
  });
  await call.start();
  assert.equal(await call.say("are you there"), true);
  assert.equal(asked.turn[0].body.text, "are you there");
  assert.equal(asked.turn[0].body.input_kind, "text");
  assert.equal(await call.say("   "), false);
});

test("stopping closes the microphone and leaves nothing running", async () => {
  const { call, device } = build({ transcripts: [{ text: "hi" }] });
  await call.start();
  device.feed(200, { rms: SPEECH, frameMs: FRAME_MS });
  call.stop();
  assert.equal(device.closed, 1);
  assert.equal(call.busy, false);
  assert.equal(call.capturing, false);
  assert.equal(call.state, IDLE);
});

test("interrupting stops the reply without closing the microphone", async () => {
  const { call, asked, device } = build({
    transcripts: [{ text: "hi" }],
    turns: [[{ type: "sentence", i: 0, text: "A long repl" }, { type: "done", reply: "A long reply" }]],
  });
  await call.start();
  await utter({ device });
  call.busy = true;
  assert.equal(call.interrupt(), true);
  assert.equal(call.busy, false);
  assert.equal(device.isOpen, true);
  assert.equal(call.interrupt(), false, "nothing left to interrupt");
  assert.equal(asked.turn.length, 1);
});

test("a page is told the words each turn was started from", async () => {
  const sent = [];
  const { call, device } = build({
    transcripts: [{ text: "spoken words" }],
    turns: [[{ type: "done", reply: "ok" }]],
    onTurn: (text, kind) => sent.push({ text, kind }),
  });
  await call.start();
  await utter({ device });
  assert.deepEqual(sent, [{ text: "spoken words", kind: "voice" }]);
});

test("a typed turn is reported as typed, not as heard", async () => {
  const sent = [];
  const { call } = build({
    turns: [[{ type: "done", reply: "ok" }]],
    onTurn: (text, kind) => sent.push({ text, kind }),
  });
  await call.say("typed words");
  assert.deepEqual(sent, [{ text: "typed words", kind: "text" }]);
});
