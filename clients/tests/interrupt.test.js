import { test } from "node:test";
import assert from "node:assert/strict";

import { InterruptGate } from "../interrupt.js";

const MS = 700;
const FRAME = 20;

function gate() {
  return new InterruptGate({ ms: MS });
}

/** Feed `ms` of one kind of frame, returning how many times it fired. */
function feed(gate, ms, { over = true, listening = false } = {}) {
  let fired = 0;
  for (let spent = 0; spent < ms; spent += FRAME) {
    if (gate.push(FRAME, { over, listening })) fired += 1;
  }
  return fired;
}

test("a level that holds long enough is an interruption", () => {
  const g = gate();
  assert.equal(feed(g, MS - FRAME), 0);
  assert.equal(feed(g, FRAME), 1);
});

test("one loud frame is not an interruption", () => {
  const g = gate();
  assert.equal(g.push(FRAME, { over: true }), false);
  assert.equal(feed(g, MS * 2, { over: false }), 0);
});

test("a quiet frame in the middle starts the count again", () => {
  // Without this, a stutter - or a syllable-shaped noise - adds up to a voice.
  const g = gate();
  feed(g, MS - FRAME);
  g.push(FRAME, { over: false });
  assert.equal(feed(g, MS - FRAME), 0);
  assert.equal(feed(g, FRAME), 1);
});

test("one interruption is one interruption", () => {
  const g = gate();
  assert.equal(feed(g, MS), 1);
  assert.equal(g.runMs, 0, "the run restarts after firing");
  assert.equal(feed(g, MS - FRAME), 0, "and it has to be earned again");
  assert.equal(feed(g, FRAME), 1);
});

test("the speaker cannot interrupt themselves while being measured", () => {
  const g = gate();
  assert.equal(feed(g, MS * 3, { listening: true }), 0);
  assert.equal(g.runMs, 0);
  assert.equal(feed(g, MS), 1, "once the window closes, interrupting works");
});

test("a reset forgets a partly counted interruption", () => {
  const g = gate();
  feed(g, MS - FRAME);
  g.reset();
  assert.equal(g.runMs, 0);
  assert.equal(feed(g, MS - FRAME), 0);
});
