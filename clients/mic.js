// Opening the microphone, once, and reading frames from it.

// The block size on the fallback path: about twenty milliseconds at 48 kHz,
// which is fine for every threshold downstream and short enough that a level
// change is noticed while it is still happening.
export const FALLBACK_BLOCK = 1024;

// The processor name registered by `worklet.js`.
export const WORKLET_NAME = "echoturn-mic";

// Where the processor lives, resolved against this module rather than written
// as a path from the site root: the client can be served from a subdirectory,
// or from wherever a host's bundler put it, without a setting to keep in step.
export const WORKLET_URL = new URL("./worklet.js", import.meta.url).href;

function defaultContext() {
  const Ctor = globalThis.AudioContext || globalThis.webkitAudioContext;
  return new Ctor();
}

/**
 * One microphone, its audio graph, and the frames coming out of it.
 *
 * `open` is safe to call concurrently and that is the point of the promise it
 * keeps. Asking for the microphone is asynchronous and shows a permission
 * prompt that can hang for seconds, and until it resolves there is nothing to
 * point at - so a second click during that window opens a *second* stream,
 * which overwrites the first and leaves it running with nobody holding a
 * reference to stop it. The symptom is a recording indicator that stays on with
 * nothing in the interface able to turn it off.
 *
 * The failure also has to be retryable. A rejected attempt that was kept would
 * be handed to every later caller, so one refusal would become permanent: the
 * button would look broken until the page was reloaded.
 */
export class Microphone {
  constructor({
    onFrame = null,
    createContext = defaultContext,
    mediaDevices = null,
    createWorkletNode = null,
    workletUrl = WORKLET_URL,
    block = FALLBACK_BLOCK,
  } = {}) {
    this.onFrame = onFrame;
    this.createContext = createContext;
    this.mediaDevicesOption = mediaDevices;
    this.createWorkletNode = createWorkletNode;
    this.workletUrl = workletUrl;
    this.block = block;
    this.context_ = null;
    this.media = null;
    this.opening = null;
    this.error = "";
    this.path = "";
    this.fallbackReason = "";
  }

  context() {
    if (!this.context_) this.context_ = this.createContext();
    return this.context_;
  }

  get sampleRate() {
    return (this.context_ && this.context_.sampleRate) || 48000;
  }

  /**
   * Whether a stream is open.
   *
   * Named `isOpen` rather than `open` because `open()` is the method that
   * starts one, and a class cannot hold both: the later definition wins, and
   * either a getter that returns a function or a method that is compared as a
   * boolean is a mistake that reads as correct at the call site.
   */
  get isOpen() {
    return this.media !== null;
  }

  devices() {
    return this.mediaDevicesOption || globalThis.navigator.mediaDevices;
  }

  /** Open the microphone; true when frames will start arriving. */
  async open() {
    if (this.media) return true;
    if (this.opening) return this.opening;
    const attempt = this.openOnce();
    this.opening = attempt;
    try {
      return await attempt;
    } finally {
      // Only clear the slot if it is still this attempt: a caller that arrives
      // while this one is settling must not have its own attempt dropped.
      if (this.opening === attempt) this.opening = null;
    }
  }

  async openOnce() {
    this.error = "";
    try {
      const ctx = this.context();
      if (ctx.state === "suspended") await ctx.resume();
      const stream = await this.devices().getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const source = ctx.createMediaStreamSource(stream);
      let node;
      try {
        node = await this.workletNode(ctx);
        this.path = "worklet";
      } catch (err) {
        // The fallback is not a preference, it is the difference between a
        // working microphone and a dead one on a platform where the worklet
        // resolves and never registers its processor.
        this.path = "script";
        this.fallbackReason = String((err && err.message) || err);
        node = this.scriptNode(ctx);
      }
      source.connect(node);
      // The fallback is only driven while it is connected to something that
      // consumes audio; it writes silence, so none of it is played back.
      node.connect(ctx.destination);
      this.media = { stream, source, node };
      return true;
    } catch (err) {
      this.error = String((err && err.message) || err);
      return false;
    }
  }

  async workletNode(ctx) {
    if (!ctx.audioWorklet) throw new Error("no audioWorklet in this context");
    await ctx.audioWorklet.addModule(this.workletUrl);
    const node =
      this.createWorkletNode !== null
        ? this.createWorkletNode(ctx, WORKLET_NAME)
        : new globalThis.AudioWorkletNode(ctx, WORKLET_NAME);
    node.port.onmessage = (event) => this.deliver(event.data);
    return node;
  }

  scriptNode(ctx) {
    const node = ctx.createScriptProcessor(this.block, 1, 1);
    node.onaudioprocess = (event) => {
      const channel = event.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < channel.length; i += 1) sum += channel[i] * channel[i];
      this.deliver({ rms: Math.sqrt(sum / channel.length), pcm: channel.slice() });
    };
    return node;
  }

  deliver(frame) {
    if (frame && frame.pcm && frame.pcm.length && this.onFrame) this.onFrame(frame);
  }

  /** Stop the stream and take the graph apart. */
  close() {
    const media = this.media;
    this.media = null;
    this.path = "";
    if (!media) return false;
    try {
      media.source.disconnect();
      media.node.disconnect();
    } catch {
      // Already disconnected; stopping the tracks below is what matters.
    }
    for (const track of media.stream.getTracks()) track.stop();
    return true;
  }
}
