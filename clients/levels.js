// Telling a voice apart from the room, using nothing but loudness.

// The absolute floor under every threshold here. Without it, a quiet room
// teaches the tracker that the room is silent, the threshold follows it down to
// nothing, and every breath and keystroke counts as somebody talking.
export const FLOOR = 0.007;

// Above this a frame is taken to be speech and is not allowed to move the noise
// reference. Feeding speech into the reference is how a threshold climbs to the
// speaker's own voice and then stops noticing them.
export const NOISE_MAX = 0.02;

// How much of a qualifying frame reaches the reference. Slow on purpose: one
// door closing must not move it, and a room that gradually gets noisier must.
const NOISE_WEIGHT = 0.06;

// How much louder than the room a voice has to be. Three times is the point
// where a room's own variation stops reaching it.
const NOISE_RATIO = 3;

/**
 * The `p` quantile of `values`, by the nearest-rank method.
 *
 * A quantile rather than a maximum, everywhere a level is being summarised:
 * a maximum follows the one loudest frame ever seen - a cough, a door - and a
 * threshold built on it is a threshold nothing can reach. The quantile is what
 * the sound is typically like.
 *
 * An empty set answers 0, which every caller has to treat as "nothing measured
 * yet" rather than as a measurement.
 */
export function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(p * sorted.length) - 1)];
}

/**
 * The room's loudness, and the threshold a frame has to beat to be a voice.
 *
 * The reference is deliberately never reset. Relearning the room at the start
 * of every turn means the first thing said in a turn is measured against a
 * reference that has not heard the room yet, and a sentence opening quietly
 * gets classified as furniture.
 */
export class LevelTracker {
  constructor({ floor = FLOOR } = {}) {
    this.floor = floor;
    this.noise = 0;
  }

  /** Feed one frame's level. */
  observe(rms) {
    if (rms >= NOISE_MAX) return this.noise;
    this.noise = this.noise ? this.noise * (1 - NOISE_WEIGHT) + rms * NOISE_WEIGHT : rms;
    return this.noise;
  }

  /**
   * The level a frame has to reach to count as speech.
   *
   * The larger of the absolute floor and a multiple of the room, so that
   * neither a silent room nor a noisy one produces a threshold that is wrong
   * in the direction that hurts.
   */
  threshold() {
    return Math.max(this.floor, this.noise * NOISE_RATIO);
  }

  /** Whether one frame's level clears the threshold. */
  isSpeech(rms) {
    return rms >= this.threshold();
  }
}
