# Positioning: what Echoturn is good at, and when to use something else

Echoturn is deliberately small. This page writes the boundaries down: what it
does better than the alternatives, what it refuses to do at all, and which
project to reach for when the answer is not Echoturn.

**Snapshot date: 2026-09-21.** The star counts and prices below are what they
were on that day. Cite them **with the date**, and when they change, change them
here rather than in a second copy somewhere else.

## 1. What this is

A provider-agnostic pipeline for realtime voice conversation, distilled from a
voice assistant that already ran end to end: capture, endpointing, ASR, LLM,
batched synthesis, ordered playback, cancellation and barge-in.

- Roughly 5,200 lines of Python under `src/echoturn/`, meant to be read in one
  sitting. The core installs with `httpx` as its only dependency.
- Seven events are the entire public contract (`ack`, `sentence`, `audio`,
  `sink`, `aborted`, `done`, `error`). [events.md](events.md) is the wire spec.
- The FastAPI/SSE bridge is one optional file. Nothing in the pipeline imports a
  web framework, and nothing in it opens a socket you did not ask for.

## 2. What it deliberately does not do

These are not gaps waiting to be filled. They are the reason the library is
small enough to read, and the reason it can sit under a product that already has
opinions about them.

| not included | why |
|---|---|
| Long-term memory, persona, prompt policy | The host owns what the model is told. A library that also remembered things would fight the memory layer you already built. |
| Accounts, quota, billing, an operations console | Product decisions, not pipeline decisions. |
| WebRTC, telephony, multi-party rooms | Real features of the bigger stacks (section 4) and a different kind of work. |
| Streaming partial transcripts | Echoturn takes a finished utterance. Partials are a transport and provider concern; the pipeline is the same either way. |
| Storage, telemetry, anything that phones home | A voice turn should not create a file or a network call you cannot see. |
| Vendor-specific adapters | One OpenAI-compatible adapter, plus mocks. A vendor endpoint is a small subclass, not a release. |

## 3. Where it is genuinely better

| advantage | what it means in practice |
|---|---|
| One dependency in the core | No web framework, no ORM, no runtime, no account. `[dsp]`, `[vad]`, `[web]` and `[cli]` are extras you opt into. |
| A contract small enough to port | Seven events, documented field by field. Bring your own transport: the browser demo and the terminal demo are two hosts for the same generator. |
| Turn-taking that admits when it is guessing | Endpointing uses measure-speech plus a "sentence finished?" model, and falls back to the silence deadline only when it must. When the optional models are missing, the builders say so in their answer instead of degrading silently. |
| Interruptions do not eat the user's words | Speak during synthesis and what you said becomes the opening of the next turn, and playback is gated against the assistant's own echo so it does not interrupt itself. |
| Audio cannot play out of order | Synthesis finishes out of order by nature; playback is ordered strictly by chunk index, so nothing is skipped, doubled or interleaved. |
| First sound does not wait for the last token | Text is flushed to synthesis in small chunks while the model is still writing. `python bench/latency.py --compare` puts a number on what that is worth at a given model pace, on your machine, and it also reports the case where chunking loses. |
| Offline by construction | Mock ASR, LLM and TTS run the whole pipeline with no key, no network and no model download, and CI runs on three Python versions with no secrets. |
| Guards that are proven to fail | The publish guard ships `--self-test` and a deliberately leaky input; the docs link check fails on a page that is not there. A guard nobody can make red is not a guard. |
| Everything is one table | Every threshold lives in `echoturn.config.DIALS`, is read from the environment at call time, and is checked against [tuning.md](tuning.md) by a test. |

## 4. The honest comparison

Figures are a 2026-09-21 snapshot. The other projects are not just bigger; they
are further along in ways that matter for a product. This table is written so
you can pick them with your eyes open.

| project | snapshot 2026-09-21 | strong at | what it does not give you that Echoturn does |
|---|---|---|---|
| [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | 13,290 stars / 1,684 forks, Apache-2.0, created 2024-08-07, PyPI `1.0.0` (2026-09-06); its README says it is the conversation backend for thousands of Reachy Mini robots | A batteries-included local stack: VAD, streaming STT, LLM and TTS wired together and served over the OpenAI Realtime GA event set (WebSocket and WebRTC) | A pipeline you can embed in your own process and your own event contract; a core with one dependency; no opinions about memory or persona either way - it is a server, not a library |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | 15,726 stars / 2,726 forks | An orchestration framework with a large service ecosystem, multi-agent patterns and client SDKs | A readable single-path turn; Echoturn is what you would read to understand the turn, not what you would use to reach forty vendors |
| [livekit/agents](https://github.com/livekit/agents) | 14,297 stars / 3,765 forks | WebRTC transport, SIP telephony, job scheduling, scale | Transport. Echoturn has no WebRTC and no telephony; if you need a phone number, this is the project, not this one |
| OpenAI Realtime (hosted) | official pricing 2026-09-21: audio $32 / 1M input and $64 / 1M output tokens (`gpt-realtime-2.1`; the mini tier is $10 / $20), text $4 / $24, `gpt-live-1` voice sessions $0.05 per minute with backend model and tool usage billed separately | Native full duplex and native interruption with zero operations | Your providers, your cost shape (section 6), your transport, and a pipeline you can run offline in CI |

If you are choosing today, the usual answer is one of them: pick a stack when
you need a phone number, a browser transport you did not write, forty
integrations, or a server you never touch. Echoturn is for the case where the
conversation layer is *yours* and the pipeline is the part you would rather not
write again.

## 5. The part where nobody is ahead: endpointing

The "is this sentence finished?" model is not a differentiator, and this page
will not pretend it is. The Hugging Face stack loads `pipecat-ai/smart-turn-v3`
v3.2 in `src/speech_to_speech/VAD/smart_turn.py`; Echoturn's optional endpoint
model is the same repository and the same version, fetched by
`echoturn-fetch-models`.

What differs is depth of engineering around it. Their speculative-turn
machinery is finer-grained than Echoturn's two dials: they delay starting STT
and the LLM while a turn is incomplete, and treat resumed speech as a new
revision whose previous output is discarded. That is a real advantage, and it is
worth copying.

## 6. Cost shape: pay per use versus burn per second

A cascade bills **when there is content**: audio is transcribed when there is
speech, text is synthesized when there are characters, and both go through
providers you already have rates for. An audio-native session bills **the
conversation as audio tokens**, including the seconds where nothing new is said.

Using the official 2026-09-21 prices above: audio tokens cost eight times the
text input price and roughly three times the text output price of the same
model. Cached audio input is cheap ($0.40 / 1M), so replayed history does not
snowball; what accumulates is every newly spoken second, on both sides.

Do the arithmetic for your own call before you pick:

```
minutes of audio per day  x  $0.06-0.17 per two-way minute  =  daily cost per user
```

That per-minute range is an **estimate**, not a measurement: the vendor
publishes token prices, and the conversion depends on the audio tokenization
rate (this page assumed 10-30 tokens per second). Run it for your own
conversation lengths, and treat the result as an order of magnitude, not a
quote. For short, bursty conversations the two shapes can land close together;
for hours of open microphone they do not.

## 7. Status, and the parts that are not done

- Early software with one maintainer, no production deployments and no released
  downstream users. [CHANGELOG.md](../CHANGELOG.md) is the honest record.
- The offline suite runs against mock providers. There is no end-to-end
  evaluation of a real ASR/LLM/TTS chain: no WER, no MOS, no comparison against
  a baseline.
- No WebRTC, no telephony, no streaming partial ASR: the browser demo posts a
  finished recording.
- The energy-based VAD floor is a starting point rather than a measured value;
  [turn-taking.md](turn-taking.md) says so where the number is defined. Latency
  claims must be measured on your own machine with `bench/latency.py`.

## 8. Re-measuring this page

- Star and fork counts: a `ungh.cc` snapshot on 2026-09-21 (the GitHub API was
  rate-limited that day);
- OpenAI prices: <https://developers.openai.com/api/docs/pricing>, fetched
  2026-09-21;
- Endpointing model provenance: `src/speech_to_speech/VAD/smart_turn.py` in the
  Hugging Face repository, read 2026-09-21.

When any of these move, update this page and its date. Do not open a second copy
of the numbers in the README.
