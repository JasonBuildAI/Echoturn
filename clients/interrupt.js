// Deciding that somebody is talking over the reply rather than at the same time
// as it.

/**
 * Counts how long the microphone has been above the interruption gate.
 *
 * A duration rather than a moment, because a moment is not evidence: a chair, a
 * door and a cough all produce one loud frame. Requiring the level to hold is
 * what separates a voice from a noise, and it is also why a listener has to say
 * more than a syllable to be heard over a reply.
 */
export class InterruptGate {
  constructor({ ms }) {
    this.ms = ms;
    this.runMs = 0;
  }

  /**
   * Feed one frame. True when the interruption has held long enough to be one.
   *
   * The run restarts after firing: one interruption is one interruption, and
   * letting the count continue would fire again on the next frame and cut off
   * whatever the listener's own turn had said in the meantime.
   *
   * `listening` - during the window where the client is measuring how loud the
   * reply comes back - accumulates nothing, so the speaker cannot interrupt
   * themselves while the client is learning what they sound like.
   */
  push(dt, { over, listening = false } = {}) {
    if (listening) {
      this.runMs = 0;
      return false;
    }
    this.runMs = over ? this.runMs + dt : 0;
    if (this.runMs >= this.ms) {
      this.runMs = 0;
      return true;
    }
    return false;
  }

  reset() {
    this.runMs = 0;
    return this;
  }
}
