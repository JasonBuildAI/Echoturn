// The worklet runs in a scope where `AudioWorkletProcessor` and
// `registerProcessor` exist and none of the page's globals do, so it is loaded
// here the same way: into a context that provides those two and nothing else.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../worklet.js", import.meta.url), "utf8");

function load() {
  const registered = [];
  const posted = [];
  const sandbox = {
    AudioWorkletProcessor: class {
      constructor() {
        this.port = { postMessage: (message) => posted.push(message) };
      }
    },
    registerProcessor(name, processor) {
      registered.push({ name, processor });
    },
  };
  vm.createContext(sandbox);
  new vm.Script(source).runInContext(sandbox);
  assert.equal(registered.length, 1);
  return { name: registered[0].name, Processor: registered[0].processor, posted };
}

test("registers the name the client constructs a node with", () => {
  assert.equal(load().name, "echoturn-mic");
});

test("posts the level and the samples of one block", () => {
  const { Processor, posted } = load();
  const processor = new Processor();
  processor.process([[[0.5, -0.5]]]);
  assert.equal(posted.length, 1);
  assert.equal(posted[0].rms, 0.5);
  assert.deepEqual(Array.from(posted[0].pcm), [0.5, -0.5]);
});

test("stays alive so the microphone keeps delivering", () => {
  const { Processor } = load();
  assert.equal(new Processor().process([[[0.1]]]), true);
});

test("says nothing about a block with no channel in it", () => {
  const { Processor, posted } = load();
  const processor = new Processor();
  processor.process([]);
  processor.process([[]]);
  processor.process([[[], []]]);
  assert.deepEqual(posted, []);
});
