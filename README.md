# Echoturn

[![CI](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml/badge.svg)](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**English** · [简体中文](README.zh-CN.md)

**A provider-agnostic pipeline for realtime voice conversation.**

Echoturn takes the boring, hard part of a voice assistant — the part that makes
it feel like a person rather than a walkie-talkie — and packages it as a small
library you can drop in front of whatever ASR, LLM and TTS you already pay for:

* **Knowing when the human is done.** Silence alone cannot tell a finished
  sentence from a comma in the middle of one. Echoturn measures *how much real
  speech* there was and *whether the sentence is complete*, then falls back to
  the silence threshold only when it has to.
* **Getting out of the way.** Speak while the assistant is thinking or finishing
  its last sentence and your words are not dropped — they are kept as the
  opening of the next turn.
* **Starting to speak fast.** Text is flushed to synthesis in small chunks as
  soon as the model produces them, so the first sound does not wait for the
  whole answer.
* **Never playing audio out of order.** Synthesis finishes out of order by
  nature; playback is strictly ordered by chunk index, so nothing gets skipped
  or interleaved.

Everything above is provider-agnostic and runs offline against mock providers.

> **Status: early.** The pipeline, providers, VAD and demo are usable; the
> public API is stabilising. See [CHANGELOG.md](CHANGELOG.md).

## Why Echoturn

| advantage | what it means in practice |
|---|---|
| **One dependency in the core** | `pip install echoturn` and read all of it: no web framework, no runtime, no account, no telemetry. The web, ONNX and device pieces are extras you opt into. |
| **A contract small enough to port** | Seven events are the whole public surface, so the transport is yours. The browser demo and the terminal demo are two hosts for the same generator. |
| **Your memory and persona layer stays yours** | Echoturn remembers nothing and decides nothing about what the model is told: it hands you a turn, you assemble the prompt. |
| **Turn-taking that admits when it is guessing** | "Is this sentence finished?" is measured - how much real speech there was, plus an endpointing model - and falls back to the silence deadline only when it must. Missing models are reported, not swallowed. |
| **Interruptions keep the user's words** | Speak over synthesis and what you said becomes the opening of the next turn, with playback gated against the assistant's own echo. |
| **Audio cannot play out of order** | Synthesis finishes out of order by nature; playback is ordered strictly by chunk index, so nothing is skipped, doubled or interleaved. |
| **First sound before the last token** | Text is flushed to synthesis in small chunks while the model is still writing. `bench/latency.py --compare` shows you where that wins - and it also shows you where it loses. |
| **Offline by construction** | Mock ASR, LLM and TTS run the whole pipeline with no key, no network and no model download; CI is green on Python 3.10-3.12 with no secrets. |

The other half of that story is written down too: what the bigger choices do better, the cost shape of a hosted audio-native session, and the cases where you should reach for them instead of this. All of it is in [docs/positioning.md](docs/positioning.md).

## How a turn flows

```
 microphone ──► capture (AudioWorklet) ──► local silence cursor ──┐
                                                                  │
        ┌───────────────────────── "is the sentence finished?" ───┘
        │
        ▼
   POST /api/transcribe ──► ASR ──► text
                                     │
                                     ▼
      POST /api/turn ──► system prompt + window ──► LLM (streaming)
                                     │
                                     ├──► sentence events ──► subtitles
                                     │
                                     └──► chunker ──► TTS ──► audio events (idx)
                                                                  │
                                                                  ▼
                                              ordered playback (WebAudio queue)
```

Text input skips capture and ASR and joins the same pipeline at the prompt
stage: there is exactly one code path per turn, not two.

## Quickstart

The whole pipeline runs with no API keys, no network and no model downloads:

```bash
pip install -e ".[web]"
echoturn-demo --mock                        # terminal: type in, beep out
echoturn-demo --mock --mic                  # talk instead (needs echoturn[cli])
python examples/minimal_call/app.py         # browser: type to it (mock providers)
```

`echoturn-demo` is the console script the package installs; `python -m
echoturn.cli.demo` is the same program, for when you would rather not rely on
`PATH`. Typing sends on enter; in `--mic` mode enter starts a recording and
enter again sends what was said.

With real providers, point a compatible endpoint at it:

```bash
export ECHOTURN_LLM_MODEL=gpt-4o-mini
export ECHOTURN_TTS_MODEL=tts-1
export OPENAI_API_KEY=...
python examples/minimal_call/app.py
```

## Install

```bash
pip install echoturn            # core: pipeline + providers, no web framework
pip install "echoturn[dsp]"     # + pitch and speed processing (numpy)
pip install "echoturn[vad]"     # + local speech detection and endpointing models
pip install "echoturn[web]"     # + FastAPI SSE adapter and the demo page
pip install "echoturn[cli]"     # + sounddevice microphone/speaker demo
```

The core depends only on `httpx`. Web frameworks and ONNX runtimes are extras on
purpose: the pipeline yields plain events, and the host decides how to ship them.

The two ONNX models behind `echoturn[vad]` are not in the wheel, because they are
tens of megabytes. Install them once, where the settings look for them:

```bash
echoturn-fetch-models           # download what is missing (or: python scripts/fetch_models.py)
echoturn-fetch-models --check   # load what is installed and run it once
```

Nothing else needs them. Without the files, turns end on the silence deadline
alone, and both `build_vad` and `build_turn` say so in their answer instead of
degrading quietly.

## Configuration

Every setting is an environment variable and is read when it is used, not at
import time, so a long-running process picks up a change without a restart. The
turn-taking thresholds are collected in one table, `echoturn.config.DIALS`, and
[docs/tuning.md](docs/tuning.md) explains what each one was measured against.
[.env.example](.env.example) lists them all with their defaults; the values in
it are the ones in the code, and a test fails when they drift apart.

| variable | default | what it does |
|---|---|---|
| `ECHOTURN_LLM_PROVIDER` | `mock` | `mock`, or `openai` for anything serving the OpenAI HTTP shape |
| `ECHOTURN_TTS_PROVIDER` | `mock` | as above, for speech synthesis |
| `ECHOTURN_ASR_PROVIDER` | `mock` | as above, for speech recognition |
| `OPENAI_API_KEY` | — | bearer token for the `openai` providers |
| `ECHOTURN_BASE_URL` | `https://api.openai.com/v1` | API root for the `openai` providers |
| `ECHOTURN_LLM_MODEL` / `ECHOTURN_TTS_MODEL` / `ECHOTURN_ASR_MODEL` | `gpt-4o-mini` / `tts-1` / `whisper-1` | model names |
| `ECHOTURN_TTS_VOICE` | `alloy` | voice name |
| `ECHOTURN_MODEL_DIR` | `models` | where the optional ONNX models are looked for |
| `ECHOTURN_HTTP_POOL_SIZE` | `32` | connections kept open for the API calls |
| `ECHOTURN_HTTP_KEEPALIVE_EXPIRY` | `60.0` | seconds an idle connection stays open |
| `ECHOTURN_VAD_ENGINE` | `silero` | `silero` (model) or `energy` (level only) |
| `ECHOTURN_IDLE_SPLIT_SEC` | `600` | a quiet gap this long reopens the context |

## Interfaces

```python
class ASRClient:
    def transcribe(self, audio: bytes, *, sample_rate: int, fmt: str, lang: str) -> str: ...

class TTSClient:
    def synth(self, text: str, *, emotion: str | None, voice: str | None) -> bytes: ...
    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None): ...

class LLMClient:
    def stream(self, messages: list[dict]) -> Iterator[str]: ...
```

Events emitted by `run_turn` (one dict per event, SSE-ready):

| event | meaning |
|---|---|
| `ack` | the user's message is committed; carries its id |
| `sentence` | one speakable sentence, for the typewriter subtitle |
| `audio` | one base64 WAV chunk plus its index and message number |
| `sink` | where the audio should be played (browser, device, ...) |
| `aborted` | the turn was superseded or cancelled |
| `done` | the full reply plus per-turn timing |
| `error` | the turn failed; the message is safe to show to a user |

## Tuning

All thresholds live in one table (`echoturn.config.DIALS`) and are read from the
environment at call time. The defaults were carried over from a pipeline that was
already running rather than invented at the keyboard, and
[docs/tuning.md](docs/tuning.md) records what each one was measured against -
including the one that is a starting point rather than a measurement, which
[docs/turn-taking.md](docs/turn-taking.md) flags where that number is defined.

The chunk thresholds are the ones with a number attached to a decision, and
[docs/benchmarks.md](docs/benchmarks.md) is how to put that number on your own
machine: `python bench/latency.py --compare`.

## Documentation

| document | what it covers |
|---|---|
| [docs/README.md](docs/README.md) | the index: what to read, and in what order |
| [docs/positioning.md](docs/positioning.md) | what Echoturn is good at, what it does not do, and when to use a bigger stack |
| [docs/architecture.md](docs/architecture.md) | modules, threading model, data flow |
| [docs/events.md](docs/events.md) | the wire contract of every event |
| [docs/providers.md](docs/providers.md) | writing an ASR/TTS/LLM adapter |
| [docs/turn-taking.md](docs/turn-taking.md) | endpointing, barge-in, echo handling |
| [docs/tuning.md](docs/tuning.md) | every knob and how its default was measured |
| [docs/client.md](docs/client.md) | the browser client: capture, playback, barge-in |
| [docs/benchmarks.md](docs/benchmarks.md) | what the latency report measures, and how to read it |

Every guide has a Chinese counterpart (`<name>.zh-CN.md`), and so does this
README: [README.zh-CN.md](README.zh-CN.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Two things matter more than anything
else here: a guard must be able to fail, and a documented number must have been
measured.

## License

Apache-2.0. See [LICENSE](LICENSE).
