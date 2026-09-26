# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

* `done.unspoken`: the messages whose text never made a sound, as message
  indices. A bubble that cannot be played is the worst of both worlds, so the
  turn names the ones that stayed silent rather than leaving a host to infer it
  from which `audio` events arrived. A message with some of its audio is not
  listed; a text-only turn lists nothing.
* `timings.asr_verdict_ms`, `timings.asr_to_first_token_ms`,
  `timings.first_token_to_first_audio_ms` and `timings.total_first_audio_ms`,
  built from what the caller sends in `TurnInput.client_timings`. The recogniser
  runs on the caller's clock, so the delay a person actually notices - they
  stopped speaking, and nothing happened - is the one delay this server cannot
  see. The browser client measures it (`Call.clientTimings`) and sends it with a
  spoken turn; `total_first_audio_ms` is that whole wait. A missing, negative or
  non-numeric value leaves the derived gaps `None`.
* `Call.meter()`: the level a meter should draw, from **whoever is talking**.
  The reply's own level is read from an analyser `PlaybackQueue` puts in the
  playback path while a chunk is live - the largest of the clips playing - and
  muting silences only the microphone's side of it. A context with no
  `createAnalyser` reports zero rather than an invented shape.
* `Call({ warmUrl })` and `WARM_PATH`: a call can ask a host route to open its
  providers' connections as the call opens, so the handshake is paid while the
  microphone is still being opened rather than inside the first reply. Opt-in,
  sent without being awaited, and its answer - including a failure - is ignored.
  `examples/minimal_call/app.py` implements such a route in ten lines.
* `ECHOTURN_SPECULATE_CALL_MS` (`speculate_call_ms`, 180 ms): the candidate
  pause that asks the service whether a sentence is finished, for a call. The
  browser client reads it through `Dials.probeMs({ inCall })`, so a call asks
  180 ms into a pause while a typed message still asks at 300 ms.
* A positioning guide in both languages (`docs/positioning.md` and its Chinese
  counterpart): what the library is genuinely better at, what it deliberately
  does not do, an honest comparison with the larger voice stacks (with the date
  on every figure), the cost shape of a hosted audio-native session, and the
  cases where another project is the right answer.
* Core pipeline: one turn from text to ordered audio chunks, with `ack`,
  `sentence`, `audio`, `sink`, `aborted`, `done` and `error` events.
* Text layer: reasoning trace removal, stage-direction removal, sentence
  iteration and chunking tuned for early first audio.
* Audio layer: PCM/WAV conversion, resampling, pitch measurement and locking,
  and time stretching.
* Providers: ASR/TTS/LLM protocols, offline mocks, and OpenAI-compatible
  adapters.
* Turn detection: energy and Silero VAD, mel front-end and a "sentence finished"
  model, both optional.
* Browser client and a minimal call demo: an AudioWorklet capture path, a
  silence cursor, a barge-in gate, an echo window and a gap-free playback queue.
* Terminal demo, installed as `echoturn-demo`: type at it, or talk to it with
  `--mic`, with `--mock` for a conversation that needs no key and no network.
* `echoturn-fetch-models` to install the optional endpointing models, which stay
  out of the wheel, and `--check` to load what is installed and run it once.
* A settings template (`.env.example`) checked against the code, a `py.typed`
  marker, and console scripts whose targets are checked before release.
* Guides under `docs/`: the architecture and its threads, the event contract,
  writing a provider, turn-taking and barge-in, every knob with what its default
  was measured against, the browser client, and how to read the benchmark.
* `bench/latency.py`, which puts a number on the pipeline's own share of a
  turn's latency and on what flushing early is worth at a given model pace.
* Two repository checks: a publish guard that fails on an identifier that must
  not leave the machine, and a warning for CJK text outside the Chinese README
  that deliberately does not fail the build.

### Changed

* API connections are kept open for 60 seconds of idle time instead of httpx's
  own 5 (`ECHOTURN_HTTP_KEEPALIVE_EXPIRY`). A conversation has quiet gaps in it
  - a reply is generated, spoken and listened to before the next request - and a
  connection that expired during one is a TCP and TLS handshake paid on the next
  reply's critical path.
* The call first-chunk thresholds are 3/2 (were 5/4, and 4/3 in between): a
  spoken turn usually opens with a whole short sentence, and two runs of each on
  the reference setup put the first sound a median 0.12 s earlier at 3/2. The
  cost is a first chunk short enough to sound clipped, so `docs/tuning.md`
  records the measurement and the values to go back to if your own run does not
  find it.
* A failing suite on CI names the tests that failed as annotations on the run,
  because the raw log is served behind a GitHub sign-in and a bare red cross is
  not a report.
* Both READMEs open with a language switch, list the library's advantages in a
  table that points at the positioning guide, and describe the tuning defaults
  as carried over from a running pipeline with the one documented exception,
  rather than as uniformly measured values.

### Fixed

* A chunk of speech that produced no audio is sent to synthesis once more before
  the turn ends, and a message still silent after that is named in
  `done.unspoken`. The commonest failure here is a rate limit or a connection
  that dropped, and a sentence missing from the middle of a reply is far more
  noticeable than one extra request. A chunk that got *some* of its audio out is
  never retried - half of it has already been heard, and a retry would say the
  beginning twice. The second attempt happens before the chunk releases the ones
  behind it, so the audio still comes out where it belongs.
* The meter no longer freezes at its last reading when a call ends, and muting
  no longer zeroes the other side of the call (see `Call.meter()`).
* An SSE stream that says nothing for five seconds sends a comment frame
  (`: keep-alive`). A turn is genuinely quiet while the model writes and while a
  synthesis request is out, and an idle connection is dropped by proxies, mobile
  networks and load balancers - all of which report it as the turn failing. The
  frame carries no `data:` line, so a client that reads events never sees one.
* A closing fence marker that arrives split across chunks closes the fence
  again. The stream hands over a token at a time, and the fence body dropped a
  half-marker along with the code it was skipping - so the fence never closed and
  every sentence written after it was read as code and lost. The longest tail
  that could still turn into the marker is held back now.
* Structured output no longer reaches a bubble or the ear. A `{...}` run that
  parses as a JSON object is removed from the reply and from the sentence stream,
  with the prose on both sides kept, wherever it stands - a model that writes its
  data mid-answer has still written an answer. The streaming path holds a brace
  that may open an object until it closes, so a comma or a question mark inside a
  contract cannot cut a piece of it out, and a brace that opens a line and never
  closes is dropped as half a contract. A reply that is nothing but an object has
  no sentences at all; `done.reply` still carries it, because a host that asked
  for structured output can read what a voice cannot say. Braces in prose are
  untouched in both directions: the cut happens only when the object parses.
* A mistyped setting is no longer ignored in silence. The shipped default is
  still used - one bad line must not stop a conversation - but `echoturn.config`
  logs one line naming the variable, the value it could not read and the default
  it ran on instead. Once per name per process, because a value read per request
  must not print per request. A blank value still means "unset" and stays
  silent; a value outside a fixed list (`ECHOTURN_VAD_ENGINE`) names itself the
  same way before falling back.
* The publish guard crashed instead of reporting when a commit message was not
  pure ASCII: `subprocess` output was decoded with the machine's locale codec,
  which on Windows is not UTF-8. Both repository guards now ask for UTF-8
  explicitly, and the privacy guard's self-test commits a non-ASCII message
  that contains a term and requires the guard to find it.
