import { test } from "node:test";
import assert from "node:assert/strict";

import { FLOOR, NOISE_MAX, LevelTracker, percentile } from "../levels.js";

test("an unheard room leaves the threshold at the absolute floor", () => {
  // The failure this prevents is on a muted or silent input: a threshold of
  // zero makes every frame speech, and the client sends a turn for the noise.
  const tracker = new LevelTracker();
  assert.equal(tracker.threshold(), FLOOR);
  assert.ok(tracker.threshold() > 0);
});

test("the reference drifts towards the frames that qualify as room", () => {
  const tracker = new LevelTracker();
  for (let i = 0; i < 200; i += 1) tracker.observe(0.004);
  assert.ok(Math.abs(tracker.noise - 0.004) < 0.0005, `noise was ${tracker.noise}`);
});

test("speech does not move the reference", () => {
  const tracker = new LevelTracker();
  for (let i = 0; i < 200; i += 1) tracker.observe(0.004);
  const before = tracker.noise;
  for (let i = 0; i < 200; i += 1) tracker.observe(0.2);
  assert.equal(tracker.noise, before);
});

test("one loud frame does not move the reference", () => {
  const tracker = new LevelTracker();
  for (let i = 0; i < 200; i += 1) tracker.observe(0.004);
  const before = tracker.noise;
  tracker.observe(NOISE_MAX + 0.0001);
  assert.equal(tracker.noise, before);
});

test("a louder room means a higher threshold", () => {
  const quiet = new LevelTracker();
  const loud = new LevelTracker();
  for (let i = 0; i < 400; i += 1) {
    quiet.observe(0.002);
    loud.observe(0.006);
  }
  assert.ok(quiet.threshold() < loud.threshold());
  assert.equal(quiet.threshold(), FLOOR);
});

test("a voice over a noisy room still counts as speech", () => {
  const tracker = new LevelTracker();
  for (let i = 0; i < 400; i += 1) tracker.observe(0.006);
  assert.ok(tracker.isSpeech(0.1));
  assert.ok(!tracker.isSpeech(tracker.threshold() - 0.001));
});

test("the quantile is the typical value, not the largest one", () => {
  const values = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.9];
  assert.equal(percentile(values, 0.8), 0.1);
  assert.equal(percentile(values, 1), 0.9);
});

test("the quantile of nothing is zero, and of one value is that value", () => {
  assert.equal(percentile([], 0.8), 0);
  assert.equal(percentile([0.25], 0.8), 0.25);
});
