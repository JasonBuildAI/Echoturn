// Stand-ins the client tests drive by hand.

/** A recorded response body, delivered in the chunks given. */
export function bodyOf(chunks) {
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

/** The events, as the frames a service would send them in. */
export function sse(events) {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
}

/** An offline context that renders by taking every `factor`-th sample. */
export function offlineStub() {
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
          channel,
          copyToChannel(data) {
            channel.set(data);
          },
        };
      },
      createBufferSource() {
        const source = { buffer: null, connect() {}, start() {} };
        offline.source = source;
        return source;
      },
      async startRendering() {
        const input = offline.source.buffer.channel;
        const factor = Math.round(input.length / offline.length) || 1;
        const out = new Float32Array(offline.length);
        for (let i = 0; i < out.length; i += 1) {
          out[i] = input[Math.min(i * factor, input.length - 1)];
        }
        return { getChannelData: () => out };
      },
    };
    built.push(offline);
    return offline;
  };
  return { built, createOffline };
}

/** A microphone the test pushes frames through. */
export class FakeMic {
  constructor({ sampleRate = 16000, opens = true, clock = null } = {}) {
    this.sampleRate = sampleRate;
    this.opens = opens;
    // Time advances with the audio, which is what a real microphone does. A
    // frozen clock turns every time-based window into one that never closes.
    this.clock = clock;
    this.error = "";
    this.isOpen = false;
    this.onFrame = null;
    this.opened = 0;
    this.closed = 0;
  }

  async open() {
    this.opened += 1;
    if (!this.opens) {
      this.error = "Permission denied";
      return false;
    }
    this.isOpen = true;
    return true;
  }

  close() {
    this.closed += 1;
    this.isOpen = false;
    return true;
  }

  /** Deliver `ms` of one level, in frames of `frameMs`. */
  feed(ms, { rms = 0.5, frameMs = 10 } = {}) {
    const length = Math.round((this.sampleRate * frameMs) / 1000);
    for (let spent = 0; spent < ms; spent += frameMs) {
      this.onFrame({ rms, pcm: new Float32Array(length) });
      if (this.clock) this.clock.now += frameMs;
    }
  }
}

/**
 * A fetch that answers the three routes the client uses, and records what it
 * was asked. `turns` is a list of event arrays, one per turn request.
 */
export function fakeFetch({
  config = {},
  turns = [],
  transcripts = [],
  turnOk = true,
} = {}) {
  const asked = { config: [], transcribe: [], turn: [] };
  const fetchImpl = async (url, options) => {
    if (url === "/config") {
      asked.config.push({ url, options });
      return { ok: true, status: 200, json: async () => config };
    }
    const body = options && options.body ? JSON.parse(options.body) : {};
    if (url === "/api/transcribe") {
      asked.transcribe.push({ url, body, options });
      const index = asked.transcribe.length - 1;
      const answer = transcripts[Math.min(index, transcripts.length - 1)] || {};
      return { ok: true, status: 200, json: async () => answer };
    }
    if (url === "/api/turn") {
      asked.turn.push({ url, body, options });
      if (!turnOk) return { ok: false, status: 500 };
      const index = asked.turn.length - 1;
      const events = turns[Math.min(index, turns.length - 1)] || [];
      // One chunk per event, which is how a real response arrives: reading the
      // stream is what lets a decode of the first audio begin long before the
      // last event is written.
      return { ok: true, status: 200, body: bodyOf(events.map((event) => sse([event]))) };
    }
    throw new Error(`unexpected request to ${url}`);
  };
  return { asked, fetchImpl };
}
