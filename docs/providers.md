# Providers

Chinese: [providers.zh-CN.md](providers.zh-CN.md)

Three protocols, in `echoturn.protocols`. They are `Protocol`s rather than base
classes on purpose: a host that had to inherit from this package would have to
depend on it, and avoiding that is the point.

```python
class ASRClient:
    def transcribe(self, audio: bytes, *, sample_rate: int, fmt: str, lang: str) -> str: ...

class TTSClient:
    def synth(self, text: str, *, emotion: str | None = None, voice: str | None = None) -> bytes: ...
    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None) -> bytes | None: ...

class LLMClient:
    def stream(self, messages) -> Iterator[str]: ...
```

## What each one promises

### `transcribe`

`fmt` names the container - `"wav"`, `"mp3"` - and `lang` is a hint, with
`"auto"` meaning "work it out yourself". The default really is `auto`: a wrong
fixed language is worse than none, because the recogniser then transcribes
confidently into the wrong language instead of reporting that it is unsure.

**An empty string is a valid answer.** It means there was nothing to hear, which
is not a failure and must not be raised as one. `clients/call.js` has a whole
path for it.

`audio` is bytes, not a parsed object, so a host that has already decoded the
clip does not have to re-wrap it to be accepted.

### `synth` and `synth_stream`

`synth` returns one complete clip. `synth_stream` hands each finished piece to
`chunk_cb` as it arrives and returns `None` when it was given a callback - the
audio has already been handed over.

Streaming is what makes a first sound possible before a whole sentence exists,
so it is worth implementing where the provider supports it. A provider that
cannot stream implements `synth` alone and mixes in
`echoturn.providers.base.WholeClipTTS`, which adapts one to the other:

```python
from echoturn.providers.base import WholeClipTTS

class MyVoice(WholeClipTTS):
    provider = "mine"

    def synth(self, text, *, emotion=None, voice=None) -> bytes:
        return b"..."          # a complete WAV
```

`emotion` is an optional tag. A provider with no emotion control ignores it
rather than refusing - the pipeline passes one through for whoever wants it and
has no opinion about who that is.

### `stream`

Yields **text pieces**, not tokens, and not a final response object. A piece can
end in the middle of a word and can contain punctuation, so the caller is the
layer that decides where sentences are. `echoturn.text` is that layer.

A provider that can only answer in one go yields a single piece. Nothing
downstream changes; the first sound just arrives later.

## The shipped adapters

| name | what it is | extra |
|---|---|---|
| `mock` | offline: a beep, a placeholder transcript, an echo | none |
| `openai` | anything serving the OpenAI HTTP shape | none (uses `httpx`) |

`openai` means the protocol, not the company. `ECHOTURN_BASE_URL` is what makes
it a different service: any endpoint with the same routes and the same request
bodies works.

```bash
export ECHOTURN_LLM_PROVIDER=openai
export ECHOTURN_LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=...
python -m echoturn.cli.demo --no-play
```

## Registering one

Add it to the registry and pick it by name:

```python
from echoturn.providers.registry import LLM_PROVIDERS

LLM_PROVIDERS["mine"] = MyModel
```

```bash
export ECHOTURN_LLM_PROVIDER=mine
```

Or pass it straight in, which is what tests do:

```python
run_turn(turn, TurnDeps(llm=MyModel(), tts=MyVoice()))
```

## What a name that does not exist does

`make_llm("gpt4")` raises, with the available names in the message:

```text
unknown LLM provider 'gpt4' (set ECHOTURN_LLM_PROVIDER, or pass the name directly); available: mock, openai
```

Falling back to the mock instead would turn a typo in a config file into a
system that looks like it works, talks in beeps, and never contacts the provider
it was configured for. The default is the mock only when nothing was asked for.

## Timeouts and the connection pool

Every HTTP request carries its own timeout, because one default would have to be
short enough for recognition and long enough for synthesis and would be wrong
for one of them.

| setting | default | for |
|---|---|---|
| `ECHOTURN_LLM_TIMEOUT` | `60.0` | one model call |
| `ECHOTURN_TTS_TIMEOUT` | `120.0` | one synthesis request |
| `ECHOTURN_ASR_TIMEOUT` | `60.0` | one recognition |
| `ECHOTURN_HTTP_POOL_SIZE` | `32` | connections kept open, process-wide |
| `ECHOTURN_HTTP_KEEPALIVE_EXPIRY` | `60.0` | how long an idle one stays open |

The last one is not a request timeout: it is how long a connection sits idle in
the pool before it is dropped. httpx's own default is 5 seconds, which is
shorter than the quiet gaps a conversation has - a reply is generated, spoken
and listened to before the next request goes out - so 5 seconds means that
request pays for a TCP and TLS handshake on the critical path, which is the cost
the shared client exists to avoid. Sixty seconds covers the gaps a call actually
has; lower it if holding sockets that long is not acceptable on your network.

The pool only helps while there is a connection in it, though. The first request
after a process starts - and the first request to a service that has put its own
model to sleep - pays for the handshake and for the provider's cold start, and if
the host has a moment before the first turn (a call screen opening, a
conversation being created), one tiny request spent there moves that cost off the
first reply's critical path. That is host code by design: this package has no
call lifecycle to hang it on, and only the host knows which providers it wired
up.

## Failures

A provider that fails raises. The pipeline catches it at the chunk it happened
in and continues: one failed synthesis is a `warning` on `done` naming the
chunk, and the text of that sentence is still in `reply`. A failed model call is
an `error` event, because there is no reply to continue with.

The message on an `error` event has been through `safe_message`, which strips
URLs, keys and internal paths. The original goes to the host's log.

## The offline providers

`MockTTS` is a beep whose length follows the text and whose pitch follows the
emotion tag. `MockASR` reports what it was given rather than inventing words -
`[mock transcript of 1.4s of wav]`. `MockLLM` echoes the prompt in small pieces.

They are built to be unmistakable, and that is the property that matters most. A
convincing stand-in is one somebody ships by accident and then spends a day
debugging.

They are also byte-for-byte reproducible, which is what makes a test that
asserts "the event stream did not change" possible at all.
