import { test } from "node:test";
import assert from "node:assert/strict";

import { PREROLL_MS, FrameRing, carryMs } from "../ring.js";

const SR = 48000;
const BLOCK = 128; // the worklet's block, and the fallback's is eight times it
const DT = (BLOCK / SR) * 1000;
const LARGE = 1024; // the fallback's block
const LARGE_DT = (LARGE / SR) * 1000;

function frame(tag, length = BLOCK) {
  const pcm = new Float32Array(length);
  pcm[0] = tag;
  return pcm;
}

function tags(ring) {
  return ring.frames.map((pcm) => pcm[0]);
}

test("a frame count is not the limit, a duration is", () => {
  // The same duration has to survive on both capture paths, and they deliver
  // blocks of different sizes.
  const small = new FrameRing({ ms: PREROLL_MS, sampleRate: SR });
  const large = new FrameRing({ ms: PREROLL_MS, sampleRate: SR });
  for (let i = 0; i < 200; i += 1) {
    small.push(frame(i));
    large.push(frame(i, LARGE));
  }
  // Within a block of the limit on either side: the trim happens between
  // frames, so the ring never holds more than the limit and never holds much
  // less either.
  assert.ok(Math.abs(small.ms - PREROLL_MS) < 2 * DT);
  assert.ok(Math.abs(large.ms - PREROLL_MS) < 2 * LARGE_DT);
  assert.ok(small.frames.length > large.frames.length);
});

test("the oldest audio is the audio that goes", () => {
  const ring = new FrameRing({ ms: 50, sampleRate: SR });
  for (let i = 0; i < 40; i += 1) ring.push(frame(i));
  const kept = tags(ring);
  assert.equal(kept[kept.length - 1], 39);
  assert.ok(!kept.includes(0), `kept ${kept}`);
  assert.deepEqual(kept, [...kept].sort((a, b) => a - b));
});

test("draining takes the audio and leaves nothing behind", () => {
  const ring = new FrameRing({ ms: 500, sampleRate: SR });
  ring.push(frame(1));
  ring.push(frame(2));
  const taken = ring.drain();
  assert.deepEqual(taken.frames.map((pcm) => pcm[0]), [1, 2]);
  assert.ok(taken.ms > 0);
  assert.deepEqual(ring.frames, []);
  assert.equal(ring.ms, 0);
});

test("clearing forgets the audio but does not resize the ring", () => {
  const ring = new FrameRing({ ms: PREROLL_MS, sampleRate: SR });
  ring.push(frame(1));
  ring.clear();
  assert.equal(ring.ms, 0);
  assert.equal(ring.limitMs, PREROLL_MS);
});

test("the carry buffer is about four interruption thresholds long", () => {
  assert.equal(carryMs(700), 2800);
  assert.equal(carryMs(0.2), 1);
});

test("a frame longer than the whole ring still leaves one frame", () => {
  // Dropping everything would send an empty recording downstream, and the
  // fallback path's blocks are long enough for this to happen at a small limit.
  const ring = new FrameRing({ ms: 1, sampleRate: SR });
  ring.push(frame(7));
  assert.deepEqual(tags(ring), [7]);
});
