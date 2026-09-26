# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
