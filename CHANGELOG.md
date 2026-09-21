# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
