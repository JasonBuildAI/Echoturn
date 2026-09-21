import { test } from "node:test";
import assert from "node:assert/strict";

import { bytesFromBase64, toBase64 } from "../base64.js";

test("base64 becomes the bytes it was made from", () => {
  assert.deepEqual(Array.from(bytesFromBase64(btoa("\x00\x01\xfe"))), [0, 1, 254]);
});

test("bytes become base64 and come back unchanged", () => {
  const bytes = new Uint8Array(1024);
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = (i * 7) % 256;
  assert.deepEqual(Array.from(bytesFromBase64(toBase64(bytes))), Array.from(bytes));
});

test("a buffer is accepted as readily as a typed array", () => {
  const bytes = new Uint8Array([1, 2, 3]);
  assert.equal(toBase64(bytes.buffer), toBase64(bytes));
});

test("a clip longer than one call to fromCharCode still encodes", () => {
  // A single call for the whole buffer throws once the buffer is big enough,
  // and "big enough" is a platform detail - so a recording that works while
  // testing fails on a longer one.
  const bytes = new Uint8Array(0x8000 * 3 + 17);
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = i % 251;
  const text = toBase64(bytes);
  assert.deepEqual(Array.from(bytesFromBase64(text)), Array.from(bytes));
});

test("an empty buffer encodes to an empty string", () => {
  assert.equal(toBase64(new Uint8Array(0)), "");
  assert.equal(bytesFromBase64("").length, 0);
});
