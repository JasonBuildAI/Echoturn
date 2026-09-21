# Architecture

Echoturn is one pipeline with three seams. The seams are the parts a host
replaces, and everything else is the part that is worth not rewriting.

| seam | what lives there | what it costs to replace |
|---|---|---|
| providers | speech recognition, speech synthesis, text generation | a protocol each, no base class |
| transport | how a turn's events reach a client | one function, `echoturn.integrations.starlette.sse_response` |
| conversation window | what recent context a turn is given | two methods: `window`, `append` |

## Module map

| module | responsibility | needs |
|---|---|---|
| `echoturn.text` | model output to something worth saying out loud | nothing |
| `echoturn.audio` | PCM/WAV containers, resampling, pitch, speed | `numpy` for pitch and speed |
| `echoturn.vad` | is this speech, and how much of it | `numpy`, `onnxruntime` for the model |
| `echoturn.endpoint` | has this person finished their sentence | `numpy`, `onnxruntime` |
| `echoturn.providers` | ASR/TTS/LLM adapters, including offline mocks | `httpx` for the HTTP ones |
| `echoturn.pipeline` | one turn, from text to ordered audio chunks | nothing |
| `echoturn.store` | the recent-messages window, and one implementation | nothing |
| `echoturn.integrations` | serving a turn as server-sent events | `starlette` |
| `echoturn.cli` | a terminal conversation | `sounddevice` for audio |

The core depends on `httpx` and nothing else. There is no web framework in the
import path of a pipeline, no numeric stack in the path of a text turn, and no
audio device in the path of a server. A host that only wants to run turns
against its own model installs one package and gets none of the rest.

## One turn

```
TurnInput ──► promote (system prompt + history + the message)
                  │
                  ▼
              LLMClient.stream ──► pieces ──► sentences ──┬──► sentence events
                  (a thread of its own)                 │
                                                        └──► chunker ──► TTS pool
                                                                              │
                                                          audio events ◄──────┘
                                                          (ordered by idx)
```

Three things run at once and that is the whole design problem:

1. the model is still writing,
2. chunk three is already synthesised,
3. chunk two is not.

The events are a generator, not callbacks, so the consumer decides how much of
that to hold. `ack` and `sink` go out before anything is spent. `done` waits for
every submitted chunk, so it can report what was actually said.

### Threads

One thread produces events (`echoturn-reply`): it reads the model, cuts
sentences, accumulates chunks and submits synthesis. Synthesis runs on a shared
`ThreadPoolExecutor`, sized by `ECHOTURN_TTS_POOL_SIZE` and built once per
process, because the limit is the provider's tolerance of concurrency and not
the number of people talking.

Ordering is a lock and a counter in `_AudioOrder`. A chunk that finishes early
waits in a dictionary until every chunk before it has been emitted, which is why
`idx` exists at all: without it, two sentences of one reply interleave.

Text-only turns never touch the pool. `ECHOTURN_TTS_PROVIDER` is not even
resolved, which is most of what a text turn saves.

### Cancellation

Three ways in, one meaning:

* the caller sets its `threading.Event` (a browser tab closing, a client
  aborting a fetch);
* the consumer closes the generator;
* a newer turn for the same key replaces this one, through
  `LiveTurns`.

All three set the same flag. It is checked between events, so it is felt within
200 ms, and the pipeline then yields `aborted` and stops. Work already handed to
the pool cannot be recalled - the request is out - so at worst one more chunk is
paid for and delivered to nobody.

The SSE bridge cannot close the generator from its own thread: the owner may be
inside `next()`, and closing a running generator raises. It sets the flag and
waits, which is why the flag exists as well as the generator protocol.

## What is deliberately not here

**Memory.** `echoturn.store` holds recent messages, caps them and reopens after
a quiet gap. It does not extract, summarise or retrieve. A window that is only
ever read cannot remember something from a hundred turns ago, and a host that
wants that brings a system for it - the pipeline will not notice.

**A persona.** The system prompt is a field on `TurnInput`. What the assistant
is told it is belongs to the product, not to the transport.

**A UI.** `clients/` is a browser client and `examples/` is a page that uses it,
because a pipeline with no way to hear it is a hard thing to adopt. Neither is
the shape a host has to keep.

## See also

* [events.md](events.md) - the wire contract
* [providers.md](providers.md) - writing an adapter
* [turn-taking.md](turn-taking.md) - endpointing and interruption
* [client.md](client.md) - the browser client
* [tuning.md](tuning.md) - every threshold and what it was measured against
