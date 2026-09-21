import { test } from "node:test";
import assert from "node:assert/strict";

import { LEAD_SEC, PlaybackQueue, bytesFromBase64 } from "../queue.js";

/** A stand-in for the audio clock, with just enough of it to schedule on. */
class FakeContext {
  constructor() {
    this.currentTime = 10;
    this.destination = { name: "destination" };
    this.started = [];
  }

  createBufferSource() {
    const context = this;
    const source = {
      buffer: null,
      stopped: false,
      onended: null,
      connect() {},
      start(at) {
        source.startedAt = at;
        context.started.push(source);
      },
      stop() {
        source.stopped = true;
      },
      /** Pretend the clip ran to its end. */
      finish() {
        if (source.onended) source.onended();
      },
    };
    return source;
  }
}

function base64(text) {
  return btoa(text);
}

/**
 * A queue whose decoding is "the first byte of the chunk names its length".
 *
 * The stub decodes exactly what the real one is handed - an ArrayBuffer - so
 * that a change in what the queue passes along fails here rather than silently
 * turning every chunk into a failed decode.
 */
function build({ durations = {}, speaking = [] } = {}) {
  const context = new FakeContext();
  const queue = new PlaybackQueue({
    createContext: () => context,
    onSpeaking: (on) => speaking.push(on),
  });
  const decode = async (buffer) => {
    const key = String.fromCharCode(new Uint8Array(buffer)[0]);
    const duration = durations[key];
    if (duration === undefined) throw new Error("cannot decode");
    return { duration };
  };
  queue.context().decodeAudioData = decode;
  return { context, queue, speaking };
}

test("base64 becomes the bytes it was made from", () => {
  assert.deepEqual(Array.from(bytesFromBase64(base64("\x00\x01\xfe"))), [0, 1, 254]);
});

test("chunks are played by their number, not by when they arrived", async () => {
  const { context, queue } = build({ durations: { a: 1, b: 1, c: 1 } });
  await queue.enqueue(2, base64("c"));
  await queue.enqueue(0, base64("a"));
  await queue.enqueue(1, base64("b"));
  assert.deepEqual(
    context.started.map((source) => source.buffer.duration),
    [1, 1, 1],
  );
  assert.equal(context.started.length, 3);
  assert.ok(context.started[0].startedAt <= context.started[1].startedAt);
  assert.ok(context.started[1].startedAt <= context.started[2].startedAt);
});

test("a later chunk arriving first waits for the one before it", async () => {
  const { context, queue } = build({ durations: { a: 2, b: 1 } });
  await queue.enqueue(1, base64("b"));
  assert.equal(context.started.length, 0, "nothing may be out of order");
  await queue.enqueue(0, base64("a"));
  assert.deepEqual(
    context.started.map((source) => source.buffer.duration),
    [2, 1],
  );
});

test("the join is exact: the next chunk starts where the last one ends", async () => {
  const { context, queue } = build({ durations: { a: 1.5, b: 0.25 } });
  await queue.enqueue(0, base64("a"));
  await queue.enqueue(1, base64("b"));
  const [first, second] = context.started;
  assert.equal(second.startedAt, first.startedAt + 1.5);
});

test("the first chunk is scheduled just ahead of the clock, never behind it", async () => {
  const { context, queue } = build({ durations: { a: 1 } });
  context.currentTime = 42;
  await queue.enqueue(0, base64("a"));
  assert.equal(context.started[0].startedAt, 42 + LEAD_SEC);
});

test("a chunk that will not decode costs its own sentence and nothing else", async () => {
  const { context, queue } = build({ durations: { a: 1, c: 1 } });
  await queue.enqueue(0, base64("a"));
  await queue.enqueue(1, base64("?"));
  await queue.enqueue(2, base64("c"));
  assert.equal(context.started.length, 2);
  assert.ok(context.started[1].startedAt >= context.started[0].startedAt + 1);
});

test("stopping silences what is playing and drops what is still decoding", async () => {
  const { context, queue } = build({ durations: { a: 1, b: 1 } });
  await queue.enqueue(0, base64("a"));
  const inFlight = queue.enqueue(1, base64("b"));
  queue.stop();
  await inFlight;
  assert.equal(context.started.length, 1, "the second chunk never starts");
  assert.equal(context.started[0].stopped, true);
  assert.equal(queue.speaking, false);
});

test("a stop makes the next turn start from its own first chunk", async () => {
  const { context, queue } = build({ durations: { a: 1, b: 1 } });
  await queue.enqueue(0, base64("a"));
  queue.stop();
  await queue.enqueue(0, base64("b"));
  assert.equal(context.started.length, 2);
});

test("the speaking state follows the audio, not the event stream", async () => {
  const { context, queue, speaking } = build({ durations: { a: 1, b: 1 } });
  await queue.enqueue(0, base64("a"));
  await queue.enqueue(1, base64("b"));
  assert.deepEqual(speaking, [true], "one start, however many chunks");
  assert.equal(queue.speaking, true);
  context.started[0].finish();
  assert.equal(queue.speaking, true, "still one chunk playing");
  context.started[1].finish();
  assert.deepEqual(speaking, [true, false]);
});
