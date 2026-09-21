// Short-term audio buffers, bounded by duration rather than by frame count.

// What is kept from before the client decided somebody had started talking, so
// the first word is not cut off. Two hundred milliseconds is shorter than any
// plausible first syllable and far longer than the meter's own latency.
export const PREROLL_MS = 200;

// The buffer that holds what was said while the reply was busy being made is
// sized from the interruption threshold, because that is the longest a listener
// can be talking without the client having acted on it yet.
const CARRY_RATIO = 4;

/** How much audio the carry buffer holds, given the interruption threshold. */
export function carryMs(bargeMs) {
  return Math.max(1, bargeMs * CARRY_RATIO);
}

/**
 * A queue of microphone frames that forgets its oldest audio first.
 *
 * Bounded by milliseconds rather than by a number of frames. The capture path
 * delivers 128-sample blocks from the worklet and 1024-sample blocks from the
 * fallback, so a frame count means a different length on each; a duration means
 * the same one, and a duration is what every threshold downstream is written
 * in. The oldest audio goes first: it is the part whose meaning the listener
 * has already moved past.
 */
export class FrameRing {
  constructor({ ms, sampleRate }) {
    this.limitMs = Math.max(1, ms);
    this.sampleRate = sampleRate;
    this.frames = [];
    this.ms = 0;
  }

  /**
   * Add one frame and drop whatever no longer fits.
   *
   * The frame's length is measured from the samples themselves rather than
   * passed in. A caller-supplied duration is a second opinion about one
   * quantity, and the two drift apart the first time a block size changes - the
   * buffer is then quietly off by a factor and nothing anywhere reports it.
   */
  push(pcm) {
    this.frames.push(pcm);
    this.ms += (pcm.length / this.sampleRate) * 1000;
    // `length > 1` and not `length`: a block that is longer than the whole ring
    // would otherwise trim itself away and leave the caller holding nothing,
    // which is the one answer that is certainly wrong - the audio that was just
    // handed over is the audio that matters.
    while (this.frames.length > 1 && this.ms > this.limitMs) {
      const dropped = this.frames.shift();
      this.ms -= (dropped.length / this.sampleRate) * 1000;
    }
    if (this.ms < 0) this.ms = 0;
    return this;
  }

  /** Take everything out, leaving the ring empty. */
  drain() {
    const taken = { frames: this.frames, ms: this.ms };
    this.frames = [];
    this.ms = 0;
    return taken;
  }

  clear() {
    this.frames = [];
    this.ms = 0;
    return this;
  }
}
