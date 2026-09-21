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
* Browser client and a minimal call demo.
