import { test } from "node:test";
import assert from "node:assert/strict";

import { ASR_RATE, encodeWav, flatten, resample, wav16k } from "../wav.js";

function text(view, offset, length) {
  let out = "";
  for (let i = 0; i < length; i += 1) out += String.fromCharCode(view.getUint8(offset + i));
  return out;
}

function samples(buffer) {
  const view = new DataView(buffer);
  const count = view.getUint32(40, true) / 2;
  const pcm = new Int16Array(buffer, 44, count);
  return Array.from(pcm);
}

/** An offline context that renders by keeping every `factor`-th sample. */
function offlineRecorder() {
  const built = [];
  const createOffline = (channels, length, rate) => {
    const offline = {
      channels,
      length,
      rate,
      source: null,
      destination: { name: "destination" },
      createBuffer(c, n, r) {
        const channel = new Float32Array(n);
        return {
          length: n,
          rate: r,
          copyToChannel(data) {
            channel.set(data);
          },
          channel,
        };
      },
      createBufferSource() {
        const source = {
          buffer: null,
          connect() {},
          start() {},
        };
        offline.source = source;
        return source;
      },
      async startRendering() {
        const input = offline.source.buffer.channel;
        const factor = Math.round(input.length / offline.length) || 1;
        const out = new Float32Array(offline.length);
        for (let i = 0; i < out.length; i += 1) out[i] = input[Math.min(i * factor, input.length - 1)];
        return { getChannelData: () => out };
      },
    };
    built.push(offline);
    return offline;
  };
  return { built, createOffline };
}

test("the header describes one channel of sixteen bit pcm", () => {
  const buffer = encodeWav(new Float32Array([0, 0, 0]), 16000);
  const view = new DataView(buffer);
  assert.equal(text(view, 0, 4), "RIFF");
  assert.equal(text(view, 8, 8), "WAVEfmt ");
  assert.equal(text(view, 36, 4), "data");
  assert.equal(view.getUint32(16, true), 16, "fmt chunk size");
  assert.equal(view.getUint16(20, true), 1, "uncompressed");
  assert.equal(view.getUint16(22, true), 1, "mono");
  assert.equal(view.getUint32(24, true), 16000, "sample rate");
  assert.equal(view.getUint32(28, true), 32000, "byte rate");
  assert.equal(view.getUint16(32, true), 2, "block align");
  assert.equal(view.getUint16(34, true), 16, "bits per sample");
});

test("the declared sizes match the samples that are there", () => {
  const buffer = encodeWav(new Float32Array(100), 8000);
  const view = new DataView(buffer);
  assert.equal(view.getUint32(40, true), 200);
  assert.equal(view.getUint32(4, true), 36 + 200);
  assert.equal(buffer.byteLength, 44 + 200);
});

test("samples are scaled to the two ends of sixteen bits", () => {
  const buffer = encodeWav(new Float32Array([1, -1, 0]), 16000);
  assert.deepEqual(samples(buffer), [32767, -32768, 0]);
});

test("samples outside the range are clamped rather than wrapped", () => {
  // Wrapping turns a loud passage into noise, which a recogniser will happily
  // transcribe as words.
  const buffer = encodeWav(new Float32Array([2, -2, 1.5]), 16000);
  assert.deepEqual(samples(buffer), [32767, -32768, 32767]);
});

test("frames are joined in the order they were captured", () => {
  // Halves and quarters, because they are exact in single precision and the
  // assertion is about the join rather than about rounding.
  const frames = [Float32Array.from([0.5]), Float32Array.from([0.25, 0.125])];
  assert.deepEqual(Array.from(flatten(frames)), [0.5, 0.25, 0.125]);
});

test("resampling asks for the target rate and a proportional length", async () => {
  const { built, createOffline } = offlineRecorder();
  const input = Float32Array.from(Array.from({ length: 48000 }, (_, i) => i));
  const out = await resample(input, 48000, 16000, { createOffline });
  assert.equal(built.length, 1);
  assert.equal(built[0].rate, 16000);
  assert.equal(built[0].length, 16000);
  assert.equal(built[0].source.buffer.rate, 48000, "the source keeps its own rate");
  assert.equal(out.length, 16000);
});

test("a length that does not divide evenly is rounded up, not truncated", async () => {
  const { built, createOffline } = offlineRecorder();
  await resample(new Float32Array(44100), 44100, 16000, { createOffline });
  assert.equal(built[0].length, Math.ceil((44100 * 16000) / 44100));
});

test("a recording already at the target rate is not rendered again", async () => {
  // The offline render is the expensive part, and it returns what it was given.
  const { built, createOffline } = offlineRecorder();
  const buffer = await wav16k([new Float32Array([0, 0])], ASR_RATE, { createOffline });
  assert.equal(built.length, 0);
  assert.equal(new DataView(buffer).getUint32(24, true), ASR_RATE);
});

test("captured frames become a sixteen kilohertz wav", async () => {
  const { built, createOffline } = offlineRecorder();
  const frames = [new Float32Array(480), new Float32Array(480)];
  const buffer = await wav16k(frames, 48000, { createOffline });
  const view = new DataView(buffer);
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint32(40, true), 320 * 2);
  assert.equal(built.length, 1);
});

test("a recording with nothing in it is still a valid file", async () => {
  const { built, createOffline } = offlineRecorder();
  const buffer = await wav16k([], 48000, { createOffline });
  assert.equal(buffer.byteLength, 44);
  assert.equal(new DataView(buffer).getUint32(40, true), 0);
  assert.equal(built.length, 0, "nothing to resample, nothing to invent");
});
