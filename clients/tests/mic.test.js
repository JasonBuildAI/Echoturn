import { test } from "node:test";
import assert from "node:assert/strict";

import { FALLBACK_BLOCK, Microphone, WORKLET_NAME, WORKLET_URL } from "../mic.js";

class FakeSource {
  constructor(stream) {
    this.stream = stream;
    this.connected = [];
    this.disconnected = false;
  }
  connect(node) {
    this.connected.push(node);
  }
  disconnect() {
    this.disconnected = true;
  }
}

class FakeNode {
  constructor(kind) {
    this.kind = kind;
    this.connected = [];
    this.disconnected = false;
  }
  connect(node) {
    this.connected.push(node);
  }
  disconnect() {
    this.disconnected = true;
  }
}

class FakeTrack {
  constructor() {
    this.stopped = false;
  }
  stop() {
    this.stopped = true;
  }
}

class FakeContext {
  constructor({ withWorklet = true, workletFails = false } = {}) {
    this.sampleRate = 48000;
    this.state = "running";
    this.resumed = 0;
    this.destination = { name: "destination" };
    this.audioWorklet = withWorklet
      ? {
          added: [],
          addModule: async (url) => {
            this.audioWorklet.added.push(url);
            if (workletFails) throw new Error("registerProcessor never ran");
          },
        }
      : null;
    this.sources = [];
  }
  resume() {
    this.resumed += 1;
    this.state = "running";
    return Promise.resolve();
  }
  createMediaStreamSource(stream) {
    const source = new FakeSource(stream);
    this.sources.push(source);
    return source;
  }
  createScriptProcessor(block) {
    this.block = block;
    return new FakeNode("script");
  }
}

function devices({ fail = false } = {}) {
  const asked = [];
  return {
    asked,
    mediaDevices: {
      getUserMedia: async (constraints) => {
        asked.push(constraints);
        if (fail) throw new Error("Permission denied");
        return { getTracks: () => [new FakeTrack(), new FakeTrack()] };
      },
    },
  };
}

function build({ context = new FakeContext(), deviceSet = devices(), onFrame } = {}) {
  const created = [];
  const mic = new Microphone({
    createContext: () => context,
    mediaDevices: deviceSet.mediaDevices,
    onFrame,
    createWorkletNode: () => {
      const node = new FakeNode("worklet");
      node.port = {};
      created.push(node);
      return node;
    },
  });
  return { mic, context, deviceSet, created };
}

test("frames arrive with a level and the samples they came from", async () => {
  const frames = [];
  const { mic, created } = build({ onFrame: (frame) => frames.push(frame) });
  assert.equal(await mic.open(), true);
  assert.equal(mic.path, "worklet");
  created[0].port.onmessage({ data: { rms: 0.5, pcm: [1, 2] } });
  assert.deepEqual(frames, [{ rms: 0.5, pcm: [1, 2] }]);
});

test("the microphone is asked for once, however many callers ask", async () => {
  // Two streams means the first is left running with nobody holding a reference
  // to stop it, and the interface has no way to turn the microphone off.
  const { mic, deviceSet } = build();
  const results = await Promise.all([mic.open(), mic.open(), mic.open()]);
  assert.deepEqual(results, [true, true, true]);
  assert.equal(deviceSet.asked.length, 1);
});

test("a second call while the first is still settling reuses it", async () => {
  const { mic, deviceSet } = build();
  const first = mic.open();
  const second = mic.open();
  await Promise.all([first, second]);
  assert.equal(deviceSet.asked.length, 1);
});

test("a refusal can be retried", async () => {
  // Keeping the rejected attempt would hand it to every later caller, and one
  // refusal would look like a permanently broken button.
  const deviceSet = devices({ fail: true });
  const { mic } = build({ deviceSet });
  assert.equal(await mic.open(), false);
  assert.match(mic.error, /Permission denied/);
  deviceSet.mediaDevices.getUserMedia = async () => ({ getTracks: () => [] });
  assert.equal(await mic.open(), true);
});

test("the handler is told what it asked for on the microphone", async () => {
  const { mic, deviceSet } = build();
  await mic.open();
  const audio = deviceSet.asked[0].audio;
  assert.equal(audio.echoCancellation, true);
  assert.equal(audio.noiseSuppression, true);
  assert.equal(audio.autoGainControl, true);
});

test("the processor is loaded from this module's own directory", async () => {
  const { mic, context } = build();
  await mic.open();
  assert.deepEqual(context.audioWorklet.added, [WORKLET_URL]);
  assert.ok(WORKLET_URL.endsWith("/worklet.js"));
});

test("where the worklet cannot load, capture still works", async () => {
  // A worklet that resolves and never registers its processor leaves a
  // microphone that looks open and delivers nothing.
  const context = new FakeContext({ workletFails: true });
  const frames = [];
  const { mic, created } = build({ context, onFrame: (frame) => frames.push(frame) });
  assert.equal(await mic.open(), true);
  assert.equal(mic.path, "script");
  assert.match(mic.fallbackReason, /never ran/);

  const node = context.sources[0].connected[0];
  assert.equal(node.kind, "script");
  node.onaudioprocess({
    inputBuffer: { getChannelData: () => Float32Array.from([0.5, 0.5]) },
  });
  assert.equal(frames.length, 1);
  assert.equal(frames[0].rms, 0.5);
  assert.deepEqual(Array.from(frames[0].pcm), [0.5, 0.5]);
  assert.equal(context.block, FALLBACK_BLOCK);
  assert.deepEqual(node.connected, [context.destination]);
  assert.deepEqual(created, [], "no worklet node is built on this path");
});

test("a microphone without audio worklet support goes straight to the fallback", async () => {
  const context = new FakeContext({ withWorklet: false });
  const { mic } = build({ context });
  assert.equal(await mic.open(), true);
  assert.equal(mic.path, "script");
});

test("closing stops the tracks and lets go of the graph", async () => {
  const { mic, context } = build();
  await mic.open();
  const [source] = context.sources;
  assert.equal(mic.close(), true);
  assert.equal(mic.isOpen, false);
  assert.equal(source.disconnected, true);
  assert.equal(mic.close(), false, "closing twice is not a failure");
});

test("frames that carry no samples are not delivered", async () => {
  const frames = [];
  const { mic, created } = build({ onFrame: (frame) => frames.push(frame) });
  await mic.open();
  created[0].port.onmessage({ data: { rms: 0, pcm: [] } });
  created[0].port.onmessage({ data: null });
  assert.deepEqual(frames, []);
});

test("the sample rate comes from the context the frames arrive on", async () => {
  const context = new FakeContext();
  context.sampleRate = 16000;
  const { mic } = build({ context });
  await mic.open();
  assert.equal(mic.sampleRate, 16000);
});
