// Deciding what a pause means.

/** Nothing decided yet; keep collecting. */
export const KEEP = "keep";
/** A candidate pause: worth asking the service whether the turn is over. */
export const PROBE = "probe";
/** Send the turn now. */
export const SEND = "send";
/** Throw the recording away: there was never a sentence in it. */
export const DROP = "drop";

// A recording nobody ever spoke into is abandoned after this long. Silence
// alone cannot end it - there is nothing to end - so without this a muted
// microphone fills a recording forever.
export const NO_VOICE_GIVE_UP_MS = 20000;

/**
 * How long the silence has lasted, how much of the recording was speech, and
 * what that adds up to.
 *
 * Three answers rather than one threshold, because silence on its own cannot
 * tell a finished sentence from a speaker drawing breath - a pause in the
 * middle of a sentence is normal in every language, and a recogniser handed one
 * answers anyway. So a pause first becomes a *question* to the service
 * ("finished?"), and only if the question cannot be answered does the original
 * fallback apply: quiet for long enough ends the turn regardless.

 * The three paths:
 *
 * 1. The service says finished - send as soon as the candidate pause is reached.
 *    This is what makes the reply quick, and it is the only path that is fast.
 * 2. The service says not finished - wait for a further silence, then send
 *    anyway. No model is allowed to leave somebody waiting with no answer to
 *    their question.
 * 3. No answer at all - the endpointing model is not installed, the service is
 *    older, the probe has not returned - fall back to the plain threshold.
 *
 * A pause is asked about once. Asking again on the same pause is asking the
 * same question about the same audio, and each ask is a transcription; the
 * point of the question is to skip the fallback wait, not to poll. Speech
 * starting again is what makes the next pause a new question.
 */
export class SilenceCursor {
  constructor({ dials, inCall = false } = {}) {
    this.dials = dials;
    this.inCall = inCall;
    this.reset(0);
  }

  /** Begin a recording. `now` is only used by the nobody-spoke guard. */
  reset(now = 0) {
    this.silenceMs = 0;
    this.voicedMs = 0;
    this.reopenMs = 0;
    this.verdict = null;
    this.voiceMs = null;
    this.hasVoice = false;
    this.asked = false;
    this.startedAt = now;
    // A flag rather than a truth test on `startedAt`: a clock reading of zero is
    // a legitimate instant, and `if (this.startedAt)` would quietly skip the
    // guard for it - the kind of check that is wrong exactly where a test cannot
    // see it, because a test that starts at zero is the common case.
    this.started = true;
    return this;
  }

  /** How much silence ends the turn when nothing else can decide it. */
  get endMs() {
    return this.dials.endMs({ inCall: this.inCall });
  }

  /** Whether the recording has been quiet long enough to send. */
  ready() {
    if (this.verdict === true) return this.silenceMs >= this.dials.number("speculate_ms");
    if (this.verdict === null) return this.silenceMs > this.endMs;
    return this.silenceMs > this.endMs && this.reopenMs >= this.dials.number("reopen_ms");
  }

  /**
   * Whether there was a sentence here.
   *
   * The service's measurement wins when there is one: it counted the waveform,
   * this counts frame levels, and a frame that is loud enough to clear the
   * threshold is not the same thing as a frame with a voice in it. Both exist
   * because the local count is also what gates the probe - a chair creaking
   * must not reach a recogniser at all, where it produces a confident "Hm."
   */
  enough() {
    const needed = this.dials.number("min_speech_ms");
    return (this.voiceMs === null ? this.voicedMs : this.voiceMs) >= needed;
  }

  /** The service answered whether the turn was finished. */
  noteVerdict(finished) {
    this.verdict = finished === null || finished === undefined ? null : Boolean(finished);
    return this;
  }

  /** The service measured how much of the recording was speech. */
  noteVoiceMs(ms) {
    this.voiceMs = Number.isFinite(Number(ms)) ? Number(ms) : null;
    return this;
  }

  /**
   * Feed one frame and get the decision it produces.
   *
   * Speech is contagious in both directions: one frame of it clears the silence
   * count, and it also throws away whatever the last pause concluded. That
   * verdict was about a different pause, and using it for this one is how a
   * client answers half a sentence.
   */
  observe({ dt, speech, now = 0 }) {
    if (speech) {
      this.hasVoice = true;
      this.silenceMs = 0;
      this.voicedMs += dt;
      this.reopenMs = 0;
      this.verdict = null;
      this.voiceMs = null;
      this.asked = false;
      return KEEP;
    }
    this.silenceMs += dt;
    // Only the silence *after* the verdict counts towards the reopen window.
    // The window answers "how much longer is he willing to wait", and silence
    // that happened before the question was asked is not part of that: by the
    // time a verdict arrives the recording has usually been quiet for most of a
    // second already, so a window measured from the start of the silence would
    // be over before it began.
    if (this.verdict === false) this.reopenMs += dt;

    // Not `verdict !== true`: a pause already answered as finished does not
    // need the same question put to it again.
    if (
      !this.asked &&
      this.verdict !== true &&
      this.hasVoice &&
      this.enough() &&
      this.silenceMs >= this.dials.number("speculate_ms")
    ) {
      this.asked = true;
      return PROBE;
    }
    if (!this.hasVoice) {
      if (this.started && now - this.startedAt > NO_VOICE_GIVE_UP_MS) return DROP;
      return KEEP;
    }
    if (!this.enough()) return this.silenceMs > this.endMs ? DROP : KEEP;
    return this.ready() ? SEND : KEEP;
  }
}
