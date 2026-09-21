import { test } from "node:test";
import assert from "node:assert/strict";

import { GUARD_MS, SAMPLES_MAX, EchoTracker } from "../echo.js";

const FLOOR = 0.1;
const RATIO = 3.5;

function tracker(overrides = {}) {
  return new EchoTracker({ floor: FLOOR, ratio: RATIO, ...overrides });
}

test("before the speaker has said anything the gate is the absolute floor", () => {
  const echo = tracker();
  assert.equal(echo.gate(), FLOOR);
  assert.equal(echo.opened, false, "nothing has been heard from the speaker yet");
});

test("a tracker that has started is open, and a reset closes it again", () => {
  const echo = tracker();
  echo.start(1000);
  assert.equal(echo.opened, true);
  echo.reset();
  assert.equal(echo.opened, false);
});

test("the guard window is open for its length and then shut", () => {
  const echo = tracker().start(1000);
  assert.ok(echo.isLearning(1000));
  assert.ok(echo.isLearning(1000 + GUARD_MS - 1));
  assert.ok(!echo.isLearning(1000 + GUARD_MS));
});

test("the reference is the typical echo, not the loudest one", () => {
  // A maximum would follow one transient frame and leave a gate a voice can no
  // longer reach, which is interrupting switched off with no error anywhere.
  const echo = tracker().start(0);
  for (let i = 0; i < 20; i += 1) echo.observe(0.02, i, {});
  echo.observe(0.9, 20, {});
  assert.ok(echo.reference < 0.05, `reference was ${echo.reference}`);
  assert.ok(Math.abs(echo.gate() - Math.max(FLOOR, echo.reference * RATIO)) < 1e-9);
});

test("the window keeps a bounded number of frames", () => {
  const echo = tracker().start(0);
  for (let i = 0; i < SAMPLES_MAX * 3; i += 1) echo.observe(0.02, 0, {});
  assert.equal(echo.samples.length, SAMPLES_MAX);
});

test("a frame during the window never counts as tracking", () => {
  const echo = tracker().start(0);
  assert.equal(echo.observe(0.5, 1, { interrupting: true }), "learning");
});

test("the reference is left alone while the listener is interrupting", () => {
  // Otherwise their own voice is mistaken for the speaker's and the gate climbs
  // to the listener's mouth, where nothing can reach it.
  const echo = tracker();
  echo.reference = 0.02;
  for (let i = 0; i < 200; i += 1) echo.observe(0.5, 5000, { interrupting: true });
  assert.equal(echo.reference, 0.02);
});

test("the reference comes down quickly and goes up slowly", () => {
  const down = tracker();
  down.reference = 0.2;
  down.observe(0, 5000, {});
  const fell = 0.2 - down.reference;

  const up = tracker();
  up.reference = 0.2;
  up.observe(0.4, 5000, {});
  const rose = up.reference - 0.2;

  assert.ok(rose < fell, `rose ${rose}, fell ${fell}`);
});

test("the gate never falls below the floor", () => {
  const echo = tracker();
  echo.reference = 0;
  assert.equal(echo.gate(), FLOOR);
});

test("a reset forgets the room and the reference", () => {
  const echo = tracker().start(0);
  echo.observe(0.3, 1, {});
  echo.reset();
  assert.equal(echo.reference, 0);
  assert.deepEqual(echo.samples, []);
  assert.equal(echo.isLearning(1), false);
  assert.equal(echo.gate(), FLOOR);
});
