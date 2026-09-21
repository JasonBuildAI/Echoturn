import { test } from "node:test";
import assert from "node:assert/strict";

import { TURN_PATH, askService, splitFrames, streamTurn } from "../stream.js";

test("two frames in one read become two events", () => {
  const buffer = 'data: {"type":"ack","id":"M1"}\n\ndata: {"type":"done"}\n\n';
  const { events, rest, broken } = splitFrames(buffer);
  assert.deepEqual(events, [{ type: "ack", id: "M1" }, { type: "done" }]);
  assert.equal(rest, "");
  assert.equal(broken, 0);
});

test("half a frame waits for the rest of it", () => {
  // A read stops wherever the socket decided to stop, and a JSON object cut in
  // half is not a parsing failure - it is not yet anything at all.
  const first = splitFrames('data: {"type":"sent');
  assert.deepEqual(first.events, []);
  assert.equal(first.rest, 'data: {"type":"sent');
  const second = splitFrames(first.rest + 'ence","text":"hi"}\n\n');
  assert.deepEqual(second.events, [{ type: "sentence", text: "hi" }]);
  assert.equal(second.rest, "");
});

test("a frame that carries no readable event is counted, not thrown", () => {
  const { events, broken } = splitFrames('data: {oops\n\ndata: {"type":"sink"}\n\n');
  assert.deepEqual(events, [{ type: "sink" }]);
  assert.equal(broken, 1);
});

test("a frame that carries no data at all is ignored rather than counted", () => {
  const { events, broken } = splitFrames(': keep-alive\n\ndata: {"type":"done"}\n\n');
  assert.deepEqual(events, [{ type: "done" }]);
  assert.equal(broken, 0);
});

function bodyOf(chunks) {
  let index = 0;
  return {
    getReader: () => ({
      read: async () => {
        if (index >= chunks.length) return { value: undefined, done: true };
        const value = new TextEncoder().encode(chunks[index]);
        index += 1;
        return { value, done: false };
      },
    }),
  };
}

test("a turn is posted as json and its events handed over in order", async () => {
  const seen = [];
  const sent = [];
  const result = await streamTurn({
    body: { text: "hello" },
    fetch: async (url, options) => {
      sent.push({ url, options });
      return {
        ok: true,
        status: 200,
        body: bodyOf([
          'data: {"type":"ack"}\n\ndata: {"type":"sentence","text":"one"}\n\n',
          'data: {"type":"audio","idx":0}\n\ndata: {"type":"done","reply":"one"}\n\n',
        ]),
      };
    },
    onEvent: (event) => seen.push(event.type),
  });
  assert.equal(sent[0].url, TURN_PATH);
  assert.equal(sent[0].options.method, "POST");
  assert.equal(sent[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(sent[0].options.body), { text: "hello" });
  assert.deepEqual(seen, ["ack", "sentence", "audio", "done"]);
  assert.equal(result.broken, 0);
});

test("a read that splits a frame does not lose it", async () => {
  const seen = [];
  await streamTurn({
    body: {},
    fetch: async () => ({
      ok: true,
      status: 200,
      body: bodyOf(['data: {"type":"sent', 'ence","text":"hi"}\n\n']),
    }),
    onEvent: (event) => seen.push(event),
  });
  assert.deepEqual(seen, [{ type: "sentence", text: "hi" }]);
});

test("a turn the service refused is an error, not an empty reply", async () => {
  await assert.rejects(
    streamTurn({ body: {}, fetch: async () => ({ ok: false, status: 500 }) }),
    /500/,
  );
});

test("an answer is read as json", async () => {
  const answer = await askService({
    url: "/api/transcribe",
    body: { audio: "..." },
    fetch: async () => ({ ok: true, status: 200, json: async () => ({ text: "hi" }) }),
  });
  assert.deepEqual(answer, { text: "hi" });
});

test("an answer that never comes is no answer rather than a failure", async () => {
  // "No verdict" is something the caller already knows how to handle, and it is
  // the whole reason the plain silence threshold exists.
  const refused = await askService({
    url: "/x",
    body: {},
    fetch: async () => ({ ok: false, status: 503 }),
  });
  assert.equal(refused, null);

  const truncated = await askService({
    url: "/x",
    body: {},
    fetch: async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("truncated");
      },
    }),
  });
  assert.equal(truncated, null);

  const offline = await askService({
    url: "/x",
    body: {},
    fetch: async () => {
      throw new Error("offline");
    },
  });
  assert.equal(offline, null);
});
