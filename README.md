# Echoturn

[![CI](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml/badge.svg)](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

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
python -m echoturn.cli.demo --mock          # terminal: text in, mock speech out
python examples/minimal_call/app.py         # browser: type to it (mock providers)
```

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
environment at call time. The defaults are measured values, not guesses — see
[docs/tuning.md](docs/tuning.md) for the reasoning behind each one.

## Documentation

| document | what it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | modules, threading model, data flow |
| [docs/events.md](docs/events.md) | the wire contract of every event |
| [docs/providers.md](docs/providers.md) | writing an ASR/TTS/LLM adapter |
| [docs/turn-taking.md](docs/turn-taking.md) | endpointing, barge-in, echo handling |
| [docs/tuning.md](docs/tuning.md) | every knob and how its default was measured |
| [docs/client.md](docs/client.md) | the browser client: capture, playback, barge-in |

Chinese README: [README.zh-CN.md](README.zh-CN.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Two things matter more than anything
else here: a guard must be able to fail, and a documented number must have been
measured.

## License

Apache-2.0. See [LICENSE](LICENSE).
