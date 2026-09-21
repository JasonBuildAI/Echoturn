// A voice conversation: microphone in, ordered audio out.

import { toBase64 } from "./base64.js";
import { DROP, PROBE, SEND, SilenceCursor } from "./cursor.js";
import { Dials } from "./dials.js";
import { EchoTracker } from "./echo.js";
import { InterruptGate } from "./interrupt.js";
import { LevelTracker } from "./levels.js";
import { Microphone } from "./mic.js";
import { PlaybackQueue } from "./queue.js";
import { PREROLL_MS, FrameRing, carryMs } from "./ring.js";
import { TURN_PATH, TRANSCRIBE_PATH, askService, streamTurn } from "./stream.js";
import { ASR_RATE, wav16k } from "./wav.js";

/** Nothing is happening. */
export const IDLE = "idle";
/** The microphone is open and somebody is being listened to. */
export const LISTENING = "listening";
/** A turn is running and no sound has come back yet. */
export const THINKING = "thinking";
/** The reply is audible. */
export const SPEAKING = "speaking";

// What a recording with no recognisable words in it says. A host replaces this
// by handling `onNotice`; leaving it empty would leave somebody who just spoke
// into a call with no indication that nothing came of it.
export const NO_TRANSCRIPT = "nothing was recognised in that recording";

// How many frames a recording needs before it can be a sentence at all. The
// duration gate is the meaningful one; this keeps two lone frames of a door
// closing from reaching it.
const MIN_FRAMES = 3;

// Where the level meter's needle sits: below this is the floor of the display,
// and everything above it is scaled up so ordinary speech fills the meter
// rather than creeping along the bottom of it.
const METER_FLOOR = 0.004;
const METER_GAIN = 7;

/** A level for a meter, from the frame's own level. */
export function meterValue(rms) {
  return Math.max(0, Math.min(1, (rms - METER_FLOOR) * METER_GAIN));
}

/**
 * One conversation on one page.
 *
 * The pieces it holds are each a decision that was hard to get right - when a
 * pause ends a turn, how loud and how long an interruption is, what to do with
 * the audio heard while the reply was being made, the order chunks are played
 * in - and this class is the wiring between them and nothing more. Anything a
 * host wants to change about how the conversation behaves is a dial or a
 * provider, not a change here.
 *
 * The state that is easy to get wrong is `busy` versus `capturing` versus
 * `ending`. They are three different things and the microphone is open through
 * all of them: a turn that is running is not a recording that has stopped, and
 * a recording that is being transcribed is not a turn. Collapsing any two of
 * them loses the audio that was said in between - which is the failure a
 * listener reports as "she was not listening to me".
 */
export class Call {
  constructor({
    session = "default",
    systemPrompt = "",
    inputKind = "voice",
    voiceCall = true,
    configUrl = "/config",
    turnUrl = TURN_PATH,
    transcribeUrl = TRANSCRIBE_PATH,
    barge = true,
    dials = null,
    microphone = null,
    clock = () => Date.now(),
    fetch: fetchImpl = null,
    createContext = undefined,
    createOffline = undefined,
    onState = null,
    onTurn = null,
    onSubtitle = null,
    onLevel = null,
    onNotice = null,
    onError = null,
    onDone = null,
  } = {}) {
    this.dials = dials || new Dials();
    this.session = session;
    this.systemPrompt = systemPrompt;
    this.inputKind = inputKind;
    this.voiceCall = voiceCall;
    this.configUrl = configUrl;
    this.turnUrl = turnUrl;
    this.transcribeUrl = transcribeUrl;
    this.barge = barge;
    this.clock = clock;
    this.fetch = fetchImpl;
    this.createOffline = createOffline;
    this.onState = onState;
    this.onTurn = onTurn;
    this.onSubtitle = onSubtitle;
    this.onLevel = onLevel;
    this.onNotice = onNotice;
    this.onError = onError;
    this.onDone = onDone;

    // Every buffer is sized from the settings, never from a number written
    // here: a microphone at 8 kHz and one at 48 kHz are the same duration and
    // very different frame counts.
    this.microphone =
      microphone ||
      new Microphone({ createContext });
    // Wired here rather than by the caller, injected microphone or not: a
    // microphone whose frames go nowhere looks exactly like a working one, and
    // that is not a mistake to leave available.
    this.microphone.onFrame = (frame) => this.onFrame(frame);
    this.level = new LevelTracker();
    this.cursor = new SilenceCursor({ dials: this.dials, inCall: voiceCall });
    this.echo = new EchoTracker({
      floor: this.dials.number("barge_floor"),
      ratio: this.dials.number("barge_ratio"),
    });
    // Named for the gate it holds rather than `interrupt`, which is the method
    // that acts on it: a field assigned from a method's own name replaces that
    // method, and the call site then fails in a way that names the wrong thing.
    this.interruptGate = new InterruptGate({ ms: this.dials.number("barge_ms") });
    this.preroll = new FrameRing({ ms: PREROLL_MS, sampleRate: this.microphone.sampleRate });
    this.rings();

    this.started = false;
    this.muted = false;
    this.busy = false;
    this.capturing = false;
    this.ending = false;
    this.capture = [];
    this.seq = 0;
    this.controller = null;
    this.pending = null;
    this.state = IDLE;
    this.queue = new PlaybackQueue({
      createContext,
      onSpeaking: (on) => {
        // The first sound of the reply is when the echo reference starts being
        // learned. Waiting for the turn to start instead would open the window
        // one or two seconds early - the model and the first synthesis happen
        // in between - and it would be over before there was anything to learn.
        if (on) this.echo.start(this.clock());
        this.emitState();
      },
    });
  }

  /** The rings, rebuilt once the microphone's own rate is known. */
  rings() {
    const rate = this.microphone.sampleRate;
    this.preroll = new FrameRing({ ms: PREROLL_MS, sampleRate: rate });
    this.carry = new FrameRing({
      ms: carryMs(this.dials.number("barge_ms")),
      sampleRate: rate,
    });
  }

  /** Open the settings and the microphone; false when the microphone refuses. */
  async start() {
    if (this.started) return true;
    await this.dials.load(this.configUrl, this.fetch ? { fetch: this.fetch } : {});
    this.rings();
    const opened = await this.microphone.open();
    if (!opened) {
      this.notice(this.microphone.error || "the microphone did not open");
      return false;
    }
    this.started = true;
    this.emitState();
    return true;
  }

  /** Close the microphone and stop everything. */
  stop() {
    this.started = false;
    this.microphone.close();
    this.stopTurn();
    this.capturing = false;
    this.ending = false;
    this.capture = [];
    this.preroll.clear();
    this.carry.clear();
    this.emitState();
  }

  /** Stop capturing without closing the microphone. */
  setMuted(muted) {
    this.muted = Boolean(muted);
    if (this.muted) {
      this.capturing = false;
      this.ending = false;
      this.capture = [];
      this.preroll.clear();
      this.carry.clear();
      this.cursor.reset(this.clock());
      if (this.onLevel) this.onLevel(0);
    }
    this.emitState();
  }

  /** Stop the reply without saying anything. */
  interrupt() {
    if (!this.busy) return false;
    this.stopTurn();
    this.emitState();
    return true;
  }

  /** Send a typed message into the same conversation. */
  async say(text, { inputKind = "text" } = {}) {
    const message = String(text || "").trim();
    if (!message) return false;
    await this.send(message, inputKind, []);
    return true;
  }

  // ---- the frame path ---------------------------------------------------

  onFrame({ rms, pcm }) {
    if (!this.started) return;
    if (this.onLevel) this.onLevel(this.muted ? 0 : rms);
    if (this.muted) return;
    const rate = this.microphone.sampleRate;
    const dt = (pcm.length / rate) * 1000;
    const speech = this.level.isSpeech(rms);
    this.level.observe(rms);
    const now = this.clock();
    // "The reply is being said" is not the same as "a turn is running". The
    // last chunk keeps playing for a second or more after the stream has
    // finished, and during that second a client that asked only about the turn
    // would treat its own reply as silence - on loudspeakers, it records the
    // tail of what it is saying and then answers it.
    const talking = this.busy || this.queue.speaking;
    if (talking) this.whileBusy({ rms, pcm, dt, speech, now });
    else this.whileFree({ rms, pcm, dt, speech, now });
  }

  /** Somebody is talking over the reply, or about to. */
  whileBusy({ rms, pcm, dt, speech, now }) {
    if (!this.barge) {
      // Interrupting is off, so the reply is left alone - but the echo
      // reference keeps drifting, because turning interrupting back on should
      // not start from a stale measurement of the room.
      this.echo.observe(rms, now, { interrupting: true });
      return;
    }
    if (!this.echo.opened) {
      // The reply has not made a sound yet: it is still being written. Nothing
      // here can be an interruption - interrupting is about the reply, not
      // about the waiting - but what is said in the meantime is kept, because
      // the reply starting is what usually stops somebody mid-sentence. The
      // ordinary speech threshold is the right test here: there is no echo to
      // compare against yet.
      if (speech) this.carry.push(pcm);
      return;
    }
    const gate = this.echo.gate();
    const over = rms >= gate;
    this.echo.observe(rms, now, { interrupting: over });
    if (over) this.carry.push(pcm);
    const fired = this.interruptGate.push(dt, {
      over,
      listening: this.echo.isLearning(now),
    });
    if (fired) this.breakIn();
  }

  /** Nothing of ours is being said. */
  whileFree({ rms, pcm, dt, speech, now }) {
    if (!this.capturing) {
      if (this.ending) {
        // Still finishing the last recording. Starting a new one here would
        // send the same pause twice, and dropping the audio would lose the
        // sentence that started during the wait.
        if (speech) this.carry.push(pcm);
        return;
      }
      this.preroll.push(pcm);
      const carried = this.carry.frames.length >= MIN_FRAMES &&
        this.carry.ms >= this.dials.number("min_speech_ms");
      if (carried || (this.carry.frames.length && speech)) {
        // Somebody finished a sentence while the reply was being made, and it
        // is that sentence that starts this recording - not just the last two
        // hundred milliseconds of it.
        this.beginCapture({ voiced: true, carry: this.carry.drain() });
      } else if (speech) {
        this.beginCapture({ voiced: true });
      } else {
        return;
      }
    }
    this.capture.push(pcm);
    const decision = this.cursor.observe({ dt, speech, now });
    if (decision === PROBE) this.probe();
    else if (decision === SEND) this.endCapture({ send: true });
    else if (decision === DROP) this.endCapture({ send: false });
  }

  // ---- recordings -------------------------------------------------------

  /**
   * Start a recording. `carry` is what was heard while the reply was busy; it
   * goes in front, because it is the whole sentence and the preroll is only the
   * last of it.
   */
  beginCapture({ voiced = false, carry = null } = {}) {
    if (this.capturing || !this.microphone.isOpen) return false;
    this.carry.clear();
    this.capture = (carry ? carry.frames : []).concat(this.preroll.drain().frames);
    this.preroll.clear();
    this.cursor.reset(this.clock());
    // The speech measured before the carry arrives is not lost with it: it was
    // speech, and a sentence picked out of the buffer must not be thrown away
    // by the same gate that was meant to stop a creak from being sent.
    if (carry && carry.ms) this.cursor.voicedMs = carry.ms;
    this.cursor.hasVoice = Boolean(voiced);
    this.capturing = true;
    this.emitState();
    return true;
  }

  /**
   * Finish a recording: decide, then either send it or keep listening.
   *
   * The decision is deliberately made with the cursor's live state rather than
   * a copy taken now, because the question it answers - has this pause gone on
   * long enough - is the same one the frame path has been asking all along.
   */
  async endCapture({ send = true } = {}) {
    if (!this.capturing || this.ending) return;
    this.capturing = false;
    this.ending = true;
    const frames = this.capture;
    this.capture = [];
    this.preroll.clear();
    const worthSending = send && this.cursor.hasVoice && frames.length >= MIN_FRAMES;
    try {
      if (!worthSending) {
        this.cursor.reset(this.clock());
        this.emitState();
        return;
      }
      // A probe already on its way carries the answer for this pause. Waiting
      // for it here is what lets a "not finished" verdict hold the turn back
      // instead of sending half a sentence.
      if (this.pending) await this.pending.catch(() => "");
      if (!this.cursor.ready()) {
        this.capturing = true;
        this.capture = frames.concat(this.carry.drain().frames);
        this.emitState();
        return;
      }
      await this.send(this.transcript, this.inputKind, frames);
      this.cursor.reset(this.clock());
    } finally {
      this.ending = false;
      this.emitState();
    }
  }

  // ---- talking to the service -------------------------------------------

  /**
   * Ask about the audio recorded so far: the words, how much of it was speech,
   * and whether the speaker had finished.
   *
   * One request answers all three. Sending it at the candidate pause rather
   * than at the end of the turn is what makes a quick reply possible: by the
   * time the turn really ends, the text is already on its way back.
   */
  probe(frames = null) {
    const seq = this.seq;
    const audio = frames || this.capture;
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const promise = (async () => {
      const wav = await wav16k(audio, this.microphone.sampleRate, {
        rate: ASR_RATE,
        createOffline: this.createOffline,
      });
      const answer = await askService({
        url: this.transcribeUrl,
        body: {
          audio: toBase64(wav),
          fmt: "wav",
          sample_rate: ASR_RATE,
          lang: this.dials.text("lang"),
        },
        signal: controller ? controller.signal : undefined,
        fetch: this.fetch || undefined,
      });
      if (seq !== this.seq) return "";
      if (!answer) {
        this.cursor.noteVerdict(null);
        return "";
      }
      const vad = answer.vad || {};
      this.cursor.noteVoiceMs(typeof vad.speech_ms === "number" ? vad.speech_ms : null);
      const turn = answer.turn || {};
      this.cursor.noteVerdict(typeof turn.complete === "boolean" ? turn.complete : null);
      this.transcript = String(answer.text || "").trim();
      return this.transcript;
    })().catch(() => "");
    this.pending = promise;
    return promise;
  }

  /** Send one turn and follow its events. */
  async send(text, inputKind, frames) {
    const message = String(text || "").trim();
    if (!message) {
      // Audio went out and no words came back. Saying so is the difference
      // between "she did not hear me" and "she heard nothing to answer" - the
      // first reads as a broken microphone, and the second is the truth.
      if (frames && frames.length) this.notice(NO_TRANSCRIPT);
      return false;
    }
    this.seq += 1;
    const seq = this.seq;
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    this.controller = controller;
    this.pending = null;
    this.transcript = "";
    this.busy = true;
    this.echo.reset();
    this.interruptGate.reset();
    this.queue.stop();
    this.emitState();
    // Reported here, before the request goes out, and reported as the *caller's*
    // words rather than as the recogniser's answer: what a page puts on screen
    // as the listener's own line has to be the same text the turn was started
    // from, including when that text was typed rather than spoken.
    if (this.onTurn) this.onTurn(message, inputKind);
    const body = {
      text: message,
      session: this.session,
      input_kind: inputKind,
      voice_call: this.voiceCall,
      ...(this.systemPrompt ? { system_prompt: this.systemPrompt } : {}),
    };
    try {
      await streamTurn({
        url: this.turnUrl,
        body,
        signal: controller ? controller.signal : undefined,
        fetch: this.fetch || undefined,
        onEvent: (event) => {
          // A superseded turn's events must not touch the new one's state: the
          // abort races the socket, and the older replies still arrive.
          if (seq === this.seq) this.onEvent(event);
        },
      });
    } catch (err) {
      if (seq === this.seq) this.failed(err);
    }
    if (seq === this.seq) this.finish();
    return true;
  }

  onEvent(event) {
    const kind = event && event.type;
    if (kind === "sentence") {
      if (this.onSubtitle) this.onSubtitle(String(event.text || ""), Number(event.i || 0));
      return;
    }
    if (kind === "audio") {
      // Not awaited: reading the stream must not wait for a decode, and the
      // queue puts chunks back into order anyway.
      this.queue.enqueue(Number(event.idx || 0), String(event.data || ""));
      this.emitState();
      return;
    }
    if (kind === "sink") {
      if (event.notice) this.notice(String(event.notice));
      return;
    }
    if (kind === "error") {
      this.error = String(event.error || "");
      this.notice(this.error);
      return;
    }
    if (kind === "aborted") {
      this.aborted = String(event.reason || "");
      return;
    }
    if (kind === "done") {
      this.reply = String(event.reply || "");
      if (this.onDone) {
        this.onDone({
          reply: this.reply,
          timings: event.timings || {},
          warnings: event.warnings || [],
        });
      }
      const warnings = event.warnings || [];
      for (const warning of warnings) this.notice(String(warning));
    }
  }

  /**
   * Somebody started talking over the reply.
   *
   * The audio already collected is taken *before* the turn is stopped: stopping
   * a turn throws away everything waiting in a buffer, so taking it afterwards
   * would leave the interruption with nothing to say - which is how a listener
   * reports only being heard from their second word onwards.
   */
  breakIn() {
    const carry = this.carry.drain();
    this.stopTurn();
    this.beginCapture({ voiced: true, carry });
  }

  /** Stop the turn in flight, whatever it was doing. */
  stopTurn() {
    this.seq += 1;
    if (this.controller) {
      try {
        this.controller.abort();
      } catch {
        // Already finished. The sequence number above is what actually stops
        // the older turn from touching anything.
      }
      this.controller = null;
    }
    this.queue.stop();
    this.busy = false;
    this.echo.reset();
    this.interruptGate.reset();
    this.carry.clear();
    this.pending = null;
    this.emitState();
  }

  /**
   * The turn is over. The audio may not be.
   *
   * The echo window and the interruption count are deliberately left alone
   * here: they describe the sound, not the request, and the last chunk of a
   * reply is still coming out of the speaker for a second or more after the
   * stream that asked for it has ended. Clearing them here closes a window that
   * was just opened and makes the tail of every reply impossible to interrupt.
   * They are cleared where the audio actually stops - a cancelled turn, and the
   * start of the next one.
   */
  finish() {
    this.busy = false;
    this.controller = null;
    this.emitState();
  }

  failed(err) {
    this.busy = false;
    this.controller = null;
    const message = (err && err.message) || String(err);
    // Both, and the order matters: a host that wants to stop the call on a
    // failure has to hear about it before the notice goes on screen, and a host
    // that only handles notices still learns that something went wrong.
    if (this.onError) this.onError(err);
    this.notice(message);
    this.emitState();
  }

  // ---- reporting --------------------------------------------------------

  notice(text) {
    if (text && this.onNotice) this.onNotice(String(text));
  }

  currentState() {
    // Sound first. A page shows this to somebody who wants to know whether they
    // will be heard over the top of it, and the answer to that is whether audio
    // is coming out - not whether the server has finished writing.
    if (this.queue.speaking) return SPEAKING;
    if (this.busy) return THINKING;
    if (this.capturing) return LISTENING;
    return IDLE;
  }

  emitState() {
    const state = this.currentState();
    if (state === this.state) return;
    this.state = state;
    if (this.onState) this.onState(state);
  }
}
