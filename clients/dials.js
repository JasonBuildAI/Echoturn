// The tunable numbers the client needs, and what it uses before the service has
// said what they are.
//
// Every number here also exists in the service's settings table, which is the
// authority: the page reads them from the service at startup and only uses
// these until that answer arrives. They are written down once, here, rather
// than at each place that reads one - a second copy is a copy that goes stale
// while both look correct.

/**
 * What the client assumes before the service has answered, and what it falls
 * back to for any value the service sends that is not a number.
 */
export const FALLBACK = Object.freeze({
  sample_rate: 16000,
  lang: "auto",
  speculate_ms: 300,
  vad_end_ms: 600,
  vad_end_call_ms: 700,
  min_speech_ms: 300,
  reopen_ms: 800,
  barge_ms: 700,
  barge_floor: 0.1,
  barge_ratio: 3.5,
});

export class Dials {
  constructor(values = {}) {
    this.values = { ...FALLBACK, ...values };
  }

  /**
   * One number, or the fallback.
   *
   * A value that is not a number is replaced rather than carried: a settings
   * file with a comma where a decimal point belongs would otherwise reach a
   * comparison as `NaN`, every comparison against it would be false, and the
   * symptom is not an error but a client that never decides anything.
   *
   * A blank value counts as unset, the same way it does on the service. Left
   * alone it would arrive here as the number zero - which is finite, so it
   * would pass every check above and silence the threshold it belongs to.
   *
   * A key with no fallback is a mistake in this file's caller rather than
   * something to absorb, so it throws instead of answering `undefined`.
   */
  number(key) {
    if (!(key in FALLBACK)) throw new Error(`no such dial: ${key}`);
    const raw = this.values[key];
    if (raw === null || raw === undefined || (typeof raw === "string" && !raw.trim())) {
      return FALLBACK[key];
    }
    const value = Number(raw);
    return Number.isFinite(value) ? value : FALLBACK[key];
  }

  /** One string, or the fallback. */
  text(key) {
    const value = this.values[key];
    return typeof value === "string" && value ? value : FALLBACK[key];
  }

  /**
   * How long a silence may last before the turn is sent anyway.
   *
   * Longer inside a call: a pause in the middle of a thought is shorter there
   * than the pause at the end of a typed message.
   */
  endMs({ inCall = false } = {}) {
    return this.number(inCall ? "vad_end_call_ms" : "vad_end_ms");
  }

  /**
   * Take the service's values, keeping the fallbacks for anything missing.
   *
   * Never throws and never leaves the client without a value. A page that is
   * served by something other than the pipeline - a static host, a proxy that
   * strips the route - still has to run, and the difference has to be visible
   * in `source` rather than in a console line nobody reads.
   */
  async load(url, { fetch: fetchImpl = globalThis.fetch } = {}) {
    try {
      const response = await fetchImpl(url);
      if (!response || !response.ok) {
        this.source = "fallback";
        return this;
      }
      const body = await response.json();
      if (body && typeof body === "object") {
        this.values = { ...this.values, ...body };
        this.source = "service";
      } else {
        this.source = "fallback";
      }
    } catch {
      this.source = "fallback";
    }
    return this;
  }
}
