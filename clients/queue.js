// Playing a turn's audio, in order, without audible joins.
//
// Imported rather than re-exported: there is one base64 implementation in this
// client, and a second copy under a different name is a second place for the
// chunk-size limit to be got wrong.
import { bytesFromBase64 } from "./base64.js";

// How far ahead of the clock the first chunk is scheduled. Starting exactly
// "now" is a race the clock usually wins, and a source started in the past
// begins mid-sample or not at all.
export const LEAD_SEC = 0.015;

function defaultContext() {
  const Ctor = globalThis.AudioContext || globalThis.webkitAudioContext;
  return new Ctor();
}

/**
 * A queue of decoded chunks, played one after another on the audio clock.
 *
 * Two things here are the reason this is not a list of `<audio>` elements.
 *
 * The seam: the next chunk is scheduled to begin where the previous one ends,
 * so the join is sample-accurate rather than dependent on how quickly a new
 * element loads. Loading a new element between every sentence is audible, and
 * it is audible precisely where a listener is paying most attention.
 *
 * The order: chunks are numbered by the position they hold in the turn, and
 * they are played by that number. Synthesis runs in parallel, so the arrival
 * order of a turn's audio is not the order it is meant to be heard in, and a
 * client that plays them as they arrive interleaves two sentences.
 *
 * Decoding starts the moment a chunk arrives and does not wait its turn. It is
 * the slow part, it can finish out of order, and holding it back behind the
 * previous chunk's playback adds its whole cost to the gap between sentences.
 */
export class PlaybackQueue {
  constructor({ createContext = defaultContext, onSpeaking = null } = {}) {
    this.createContext = createContext;
    this.onSpeaking = onSpeaking;
    this.context_ = null;
    this.generation = 0;
    this.expected = 0;
    this.waiting = new Map();
    this.playAt = 0;
    this.live = [];
  }

  /** The audio context, started on first use and resumed if it went to sleep. */
  context() {
    if (!this.context_) this.context_ = this.createContext();
    if (this.context_.state === "suspended") {
      // A page that has not been interacted with yet starts suspended. The
      // promise is not awaited: whoever asked for playback is usually a socket
      // message, and there is nothing to wait for - the scheduled sources will
      // simply start when the context does.
      Promise.resolve(this.context_.resume()).catch(() => {});
    }
    return this.context_;
  }

  /** Whether anything is scheduled or playing. */
  get speaking() {
    return this.live.length > 0;
  }

  /**
   * Decode one chunk and play it in its place.
   *
   * `generation` is read before the decode and checked after it: a chunk that
   * finishes decoding after the turn it belongs to was stopped must not start
   * playing, and a decode is long enough for that to happen.
   */
  async enqueue(idx, base64) {
    const generation = this.generation;
    let clip = null;
    try {
      const bytes = bytesFromBase64(base64);
      clip = await this.context().decodeAudioData(bytes.buffer);
    } catch {
      // A chunk that will not decode is one sentence lost, not the turn: the
      // index is still consumed so the rest of the audio keeps its order.
      clip = null;
    }
    if (generation !== this.generation) return;
    this.waiting.set(idx, clip);
    this.drain();
  }

  /** Schedule everything whose turn it is. */
  drain() {
    const ctx = this.context();
    while (this.waiting.has(this.expected)) {
      const clip = this.waiting.get(this.expected);
      this.waiting.delete(this.expected);
      this.expected += 1;
      if (clip) this.schedule(clip);
    }
  }

  schedule(clip) {
    const ctx = this.context();
    const source = ctx.createBufferSource();
    source.buffer = clip;
    source.connect(ctx.destination);
    const at = Math.max(this.playAt, ctx.currentTime + LEAD_SEC);
    source.start(at);
    this.playAt = at + clip.duration;
    if (!this.live.length && this.onSpeaking) this.onSpeaking(true);
    this.live.push(source);
    source.onended = () => {
      this.live = this.live.filter((item) => item !== source);
      if (!this.live.length && this.onSpeaking) this.onSpeaking(false);
    };
  }

  /**
   * Silence everything and start over.
   *
   * The generation goes up, so any chunk still being decoded is discarded on
   * its way out rather than played after the interruption - which is how a
   * stopped reply says two more sentences anyway.
   */
  stop() {
    this.generation += 1;
    for (const source of this.live) {
      try {
        source.stop();
      } catch {
        // Already ended. Stopping it twice is not a failure worth reporting.
      }
    }
    this.live = [];
    this.waiting.clear();
    this.expected = 0;
    this.playAt = this.context_ ? this.context_.currentTime : 0;
    if (this.onSpeaking) this.onSpeaking(false);
    return this;
  }
}
