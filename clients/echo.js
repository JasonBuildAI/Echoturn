// How loud the speaker's own voice comes back through the microphone.

import { percentile } from "./levels.js";

// How long after the speaker's first sound the client only listens to itself.
//
// Nothing said during this window can count as an interruption, so it is also
// the shortest a listener has to wait before interrupting can work at all. On
// headphones it costs that much and no more; on loudspeakers it is what stops
// the reply from interrupting itself at the first syllable.
export const GUARD_MS = 500;

// How many frames the guard window's summary is built from. Half a second is
// about thirty frames at a 60 Hz meter, so this is generous rather than tight.
export const SAMPLES_MAX = 120;

// The reference follows a value below it quickly and one above it slowly. The
// asymmetry is the whole protection: a single loud frame - a cough, a chair -
// must not drag the gate up to where a voice cannot reach it, which would turn
// interrupting off silently. Coming down quickly is what restores sensitivity
// when the speaker gets quieter.
const FALLING = 0.25;
const RISING = 0.02;

/**
 * What the speaker's voice measures coming back through the microphone, and the
 * level a listener has to beat to count as interrupting.
 *
 * Time is passed in rather than read, so the guard window is a value a test can
 * walk through instead of a sleep.
 */
export class EchoTracker {
  constructor({ floor, ratio, guardMs = GUARD_MS, samplesMax = SAMPLES_MAX } = {}) {
    this.floor = floor;
    this.ratio = ratio;
    this.guardMs = guardMs;
    this.samplesMax = samplesMax;
    this.reference = 0;
    this.samples = [];
    this.until = 0;
  }

  /** The speaker has started; open the guard window. */
  start(now) {
    this.until = now + this.guardMs;
    this.samples = [];
    this.reference = 0;
    return this;
  }

  /**
   * Whether the speaker has made a sound yet.
   *
   * Three states, not two: nothing heard from the speaker, inside the window,
   * and past it. The first is what tells a client that a reply is still being
   * written - there is nothing yet to be talking over, and no echo to measure -
   * and reading it as "inside the window" would make every interruption wait
   * for a window that had not opened.
   */
  get opened() {
    return this.until > 0;
  }

  /** Whether the guard window is still open. */
  isLearning(now) {
    return now < this.until;
  }

  /**
   * Feed one frame. `interrupting` says whether the listener is mid-interruption
   * already, which is when their own voice must not be taken for the speaker's.
   */
  observe(rms, now, { interrupting = false } = {}) {
    if (this.isLearning(now)) {
      this.samples.push(rms);
      if (this.samples.length > this.samplesMax) this.samples.shift();
      this.reference = percentile(this.samples, 0.8);
      return "learning";
    }
    if (!interrupting) {
      const weight = rms < this.reference ? FALLING : RISING;
      this.reference += (rms - this.reference) * weight;
    }
    return "tracking";
  }

  /**
   * The level an interruption has to beat: the larger of the absolute floor and
   * a multiple of what comes back.
   *
   * Both halves are needed. The floor keeps a quiet room's own noise from
   * counting as a voice; the ratio keeps a speaker on loudspeakers from being
   * interrupted by their own reply.
   */
  gate() {
    return Math.max(this.floor, this.reference * this.ratio);
  }

  reset() {
    this.until = 0;
    this.samples = [];
    this.reference = 0;
    return this;
  }
}
