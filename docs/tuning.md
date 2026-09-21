# Tuning

Chinese: [tuning.zh-CN.md](tuning.zh-CN.md)

Every threshold in this package is an environment variable, and `DIALS` in
`echoturn.config` is the only place those numbers are written down. A second
copy in a provider or in a demo page is how one of them ends up stale while
everything still looks fine - which is why the demo page fetches the whole table
from `/config` instead of holding its own.

They are read **when they are used**, not at import time, so a change is visible
to the next request instead of needing a restart.

```python
from echoturn.config import dials
dials()["vad_end_ms"]        # read now
```

## The table

| variable | key | default | what it decides |
|---|---|---|---|
| `ECHOTURN_ASR_SAMPLE_RATE` | `sample_rate` | `16000` | what the recogniser is sent, and the rate the microphone records at |
| `ECHOTURN_ASR_LANG` | `lang` | `auto` | the language hint |
| `ECHOTURN_ASR_INCREMENTAL_MS` | `incremental_ms` | `700` | how often a partial transcript may be asked for |
| `ECHOTURN_VAD_ENGINE` | `vad_engine` | `silero` | `silero` or `energy` |
| `ECHOTURN_SMART_TURN` | `smart_turn` | `true` | whether the endpoint model is consulted at all |
| `ECHOTURN_VAD_END_MS` | `vad_end_ms` | `600` | quiet for this long ends the turn |
| `ECHOTURN_VAD_END_CALL_MS` | `vad_end_call_ms` | `700` | the same, inside a call |
| `ECHOTURN_MIN_SPEECH_MS` | `min_speech_ms` | `300` | below this, there was no sentence |
| `ECHOTURN_REOPEN_MS` | `reopen_ms` | `800` | how long to wait after "not finished" |
| `ECHOTURN_SPECULATE_MS` | `speculate_ms` | `300` | the silence that starts a recognition early |
| `ECHOTURN_BARGE_MS` | `barge_ms` | `700` | how long an interruption has to hold |
| `ECHOTURN_BARGE_FLOOR` | `barge_floor` | `0.10` | the level below which nothing is an interruption |
| `ECHOTURN_BARGE_RATIO` | `barge_ratio` | `3.5` | how far above the echo a voice has to be |
| `ECHOTURN_TTS_FIRST_CHARS` | `tts_first_chars` | `7` | characters before the first synthesis request |
| `ECHOTURN_TTS_FIRST_MIN` | `tts_first_min` | `5` | the shortest text worth spending a request on |
| `ECHOTURN_TTS_CHUNK_CHARS` | `tts_chunk_chars` | `36` | characters per chunk after the first |
| `ECHOTURN_TTS_CHUNK_MIN` | `tts_chunk_min` | `16` | the shortest later chunk |
| `ECHOTURN_TTS_FIRST_CALL_CHARS` | `tts_first_call_chars` | `5` | the first chunk, inside a call |
| `ECHOTURN_TTS_FIRST_CALL_MIN` | `tts_first_call_min` | `4` | the shortest first chunk, inside a call |
| `ECHOTURN_TTS_POOL_SIZE` | `tts_pool_size` | `32` | synthesis requests in flight, process-wide |
| `ECHOTURN_IDLE_SPLIT_SEC` | `idle_split_sec` | `600` | a gap this long reopens the context |

## What each group was measured against

### Recognition

**16000 Hz** is what speech models are fed, so a recording, a resampled clip and
a mock beep are all interchangeable downstream.

**`auto` rather than a language.** A recogniser can usually work it out, and a
wrong fixed language is worse than none: it transcribes confidently into the
wrong language instead of reporting that it is unsure.

### Turn ends

**600 ms of typing, 700 ms inside a call.** A pause in the middle of a thought
is shorter than a pause between two typed messages, so the call threshold is
longer. Both are the *fallback*: a verdict from the endpoint model ends the turn
sooner.

**300 ms of speech minimum.** A table knock of a few tens of milliseconds comes
back from a recogniser as a hallucinated word. The gate is the length of speech,
not the length of audio, so a quiet recording with a word in it still passes.

**800 ms to wait after "not finished".** Ending a turn early is the better
mistake: a wrong "not finished" leaves somebody talking to something that looks
broken, while a wrong "finished" is a reply they can simply talk over.

**300 ms to start recognising.** The text is already on its way by the time the
turn does end, which is most of what makes a quick reply possible. It has to
stay below the end point, or the turn ends before the speculation was ever
useful.

The single most important thing to know about the pair `speculate_ms` and
`vad_end_ms`: the first must be smaller than the second.

### Interruption

The test is `max(barge_floor, echo * barge_ratio)`, **sustained** for
`barge_ms`. Three numbers because they answer three different failures:

* the floor catches keyboards, breathing and desk bumps that never reach 0.10;
* the ratio catches the reply coming back through the microphone - a speaker on
  loudspeakers that ignored the ratio interrupts itself halfway through every
  reply;
* the duration catches the single loud frame that a chair or a door produces.

With `barge_ratio` too low, nobody on loudspeakers can be heard over a reply.
With `barge_ms` too low, they interrupt each other constantly. The values here
were arrived at by using it on both headphones and a speaker.

### Synthesis chunking

The trade is audible seams against latency. One sentence per request gives a
seam between sentences, because each request starts its intonation from scratch.
Waiting for more text costs first-sound latency.

**The first chunk has its own, much smaller threshold** - 7 characters against
36 - because listeners judge speed almost entirely on the first sound. A call
gets a smaller one again (5), because a spoken turn is usually one or two
sentences and the seam a very short first chunk creates is one nobody notices
over a phone.

The `_MIN` values are the floor under each of those: a chunk shorter than them
is not worth a request, so the chunker keeps accumulating.

#### What counts as an ending

A sentence is cut at `。`, `！`, `？`, `!` and `?`; a comma, a colon, a semicolon
or an ellipsis only becomes a cut once the buffer is long enough to be worth
sending. An ASCII full stop is **not** an ending, which is a real limitation for
a reply written in English: a paragraph of English prose with full stops in it
arrives as one long chunk and gets one synthesis request.

This is the behaviour this library was extracted from rather than a decision
made here, so it is written down instead of quietly changed - the thresholds
above were measured against it, and widening the set of endings would move every
number on this page. `tests/test_text_sentences.py` pins it in both directions:
one test for the endings that cut, one for the one that does not.

### Synthesis concurrency

**32 in flight, for the whole process.** It is sized for the provider's
tolerance of concurrency, not for the number of people talking. A pool per turn
would put fifteen hundred threads on the machine at five hundred simultaneous
calls, and the time everybody spends waiting for a free core is time they spend
not hearing anything.

It is read when the pool is built, which is once per process, so changing it
needs a restart. That is the one setting here that does.

### The context gap

**600 seconds.** Within it, the conversation continues; past it, the model
starts fresh and the tokens are saved.

It affects nothing else. History, transcripts and everything a host stores are
untouched by it, and there is exactly **one** such clock in the system. A second
idle concept - "the window reopened" and "the reply mode reset" as two timers -
is how the two end up disagreeing about the same silence.

## Bad values

A value that cannot be read falls back to the default, and never to something
else. `ECHOTURN_BARGE_RATIO=3,5` is 3.5, the shipped ratio - never 0, which
would make every sound from the microphone an interruption.

`ECHOTURN_VAD_ENGINE` is the one setting with a fixed list. A name that is not
one of them becomes `silero`, because this runs on the path of a live
conversation and a typo in a config file should not stop the audio.

An empty value counts as unset. A config file line of
`ECHOTURN_TTS_PROVIDER=` means "use the default", and a factory that took the
empty string at face value would report an unknown provider called `""` - which
reads from the outside as "it stopped speaking and nobody changed anything".

## A different microphone needs a different number

The defaults were chosen against one setup. A different room, microphone or
accent is usually one of these values away from working, which is why they are
settings and not constants:

* being talked over too often → raise `barge_ms` or `barge_ratio`;
* unable to interrupt → lower `barge_ratio`, or lower `barge_floor` if the
  microphone is quiet;
* replies arrive before they have finished a sentence → raise `vad_end_ms`;
* replies feel slow to start → lower `tts_first_chars` (at the cost of more
  requests and more seams).
