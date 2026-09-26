import { test } from "node:test";
import assert from "node:assert/strict";

import { FALLBACK, Dials } from "../dials.js";

test("the fallbacks are the values the service ships with", () => {
  const dials = new Dials();
  for (const [key, value] of Object.entries(FALLBACK)) {
    assert.equal(dials.number(key), value, key);
  }
});

test("a value from the service wins", () => {
  const dials = new Dials({ vad_end_ms: 900 });
  assert.equal(dials.number("vad_end_ms"), 900);
});

test("a value that is not a number is replaced rather than carried", () => {
  // NaN would sail through every comparison as false and the client would never
  // decide anything, with no error anywhere.
  const dials = new Dials({ barge_ratio: "3,5", min_speech_ms: null, reopen_ms: "" });
  assert.equal(dials.number("barge_ratio"), FALLBACK.barge_ratio);
  assert.equal(dials.number("min_speech_ms"), FALLBACK.min_speech_ms);
  assert.equal(dials.number("reopen_ms"), FALLBACK.reopen_ms);
  assert.ok(Number.isFinite(dials.number("barge_ratio")));
});

test("asking for a dial that does not exist is a mistake, not a zero", () => {
  assert.throws(() => new Dials().number("nothing_like_this"), /no such dial/);
});

test("a call waits longer than a typed message", () => {
  const dials = new Dials();
  assert.equal(dials.endMs(), 600);
  assert.equal(dials.endMs({ inCall: true }), 700);
});

test("a call asks sooner than a typed message", () => {
  // The probe is part of the turn inside a call rather than a shortcut around
  // it, so the candidate pause is smaller there while the deadline is later.
  const dials = new Dials();
  assert.equal(dials.probeMs(), 300);
  assert.equal(dials.probeMs({ inCall: true }), 180);
});

test("text falls back when it is empty or the wrong kind", () => {
  assert.equal(new Dials({ lang: "" }).text("lang"), "auto");
  assert.equal(new Dials({ lang: "en" }).text("lang"), "en");
  assert.equal(new Dials({ lang: 7 }).text("lang"), "auto");
});

test("loading takes what the service sends and keeps the rest", async () => {
  const dials = new Dials();
  const fetched = [];
  await dials.load("/config", {
    fetch: async (url) => {
      fetched.push(url);
      return { ok: true, json: async () => ({ vad_end_ms: 750 }) };
    },
  });
  assert.deepEqual(fetched, ["/config"]);
  assert.equal(dials.number("vad_end_ms"), 750);
  assert.equal(dials.number("min_speech_ms"), FALLBACK.min_speech_ms);
  assert.equal(dials.source, "service");
});

test("a service that does not answer leaves a working client", async () => {
  const dials = new Dials();
  await dials.load("/config", {
    fetch: async () => ({ ok: false, status: 404, json: async () => ({}) }),
  });
  assert.equal(dials.source, "fallback");
  assert.equal(dials.number("vad_end_ms"), FALLBACK.vad_end_ms);

  await dials.load("/config", {
    fetch: async () => {
      throw new Error("offline");
    },
  });
  assert.equal(dials.source, "fallback");
  assert.ok(Number.isFinite(dials.number("vad_end_ms")));
});
