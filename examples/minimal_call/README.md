# Minimal call

A service that runs the whole pipeline for a browser, in one file. It is
deliberately thin: it owns a model, a voice, a recogniser, one conversation
window and the four routes a page needs. Everything interesting is in the
package it imports, so a host that wants a different shape can read this file
and see exactly which parts are theirs to replace.

```bash
pip install -e ".[web]"
python examples/minimal_call/app.py           # then open http://127.0.0.1:8000
```

Run it as a file rather than as `-m examples.minimal_call.app`, because
`examples` is a common name for an installed package and a directory that only
wins when nothing else claims the name is a directory that works on some
machines.

## It works with no keys at all

The offline providers answer with a beep and a placeholder transcript, so the
wiring can be heard before anything is signed up for. To point it at a real
service, set the two variables and a key:

```bash
export ECHOTURN_LLM_PROVIDER=openai
export ECHOTURN_TTS_PROVIDER=openai
export ECHOTURN_LLM_MODEL=gpt-4o-mini
export ECHOTURN_TTS_MODEL=tts-1
export OPENAI_API_KEY=...
```

## The routes

| route | what it is for |
|---|---|
| `GET /` | the page |
| `GET /client/*` | the browser client, served from `clients/` |
| `GET /config` | the whole dial table, so the page holds no copy of a number |
| `POST /api/transcribe` | one recording: the words, how much was speech, whether it was finished |
| `POST /api/turn` | one turn, as server-sent events |

`/config` returns `echoturn.config.dials()` unchanged. That is the point of it:
there is one table, it is in the package, and the page reads it rather than
carrying a second copy that goes stale while both look correct.

## The one decision this file makes

```python
DEFAULT_SYSTEM_PROMPT = env_str(
    "ECHOTURN_DEMO_SYSTEM",
    "You are a helpful voice assistant. Answer in one or two short sentences.",
)
```

A system prompt is not something a pipeline can guess, and a default that
pretended to be a personality would be worse than a plain instruction. What the
assistant is told it is belongs to the product, so it is here - and a caller can
replace it per request with `system_prompt`.

## What is not here

No settings page, no history, no accounts, no deployment files. A demo that
grows those stops being a demo and starts being a product nobody chose.

## The probe

`POST /api/transcribe` also answers "has this person finished their sentence",
and that answer is **absent** rather than false when there is no model to ask.
The two are different: a judge that says "not finished" and is wrong leaves
somebody waiting for a reply that never comes, so the page has to be able to
tell "no" from "no idea" and fall back to its own silence threshold for the
second.

When the recording is not 16 kHz mono there is no `turn` key and `vad.fallback`
is true with a reason. Resampling to guess would put audio through a model at
the wrong rate and produce confident nonsense.
