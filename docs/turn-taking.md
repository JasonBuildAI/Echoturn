# Turn taking

Chinese: [turn-taking.zh-CN.md](turn-taking.zh-CN.md)

Three questions, three answers, and they are separate because they fail
differently.

| question | where it is answered | what happens when it is wrong |
|---|---|---|
| has this person finished their sentence? | the client, with the service's opinion | they are talked over, or left waiting |
| is this speech, and how much of it? | `echoturn.vad`, in the service | a cough becomes a turn |
| is somebody interrupting the reply? | the client, against the echo it measured | nobody can interrupt, or the reply interrupts itself |

## Asking whether the sentence is finished

Silence alone cannot answer it. A pause in the middle of a sentence is normal in
every language, and a recogniser handed a pause answers anyway - so a
silence-only rule sends half a sentence to be transcribed and then sends the
other half as a second turn.

So a pause becomes a **question** first. `clients/cursor.js` has three paths,
and only the first is fast:

1. **The service says finished.** The turn is sent as soon as the candidate
   pause is reached, without waiting for the fallback deadline. This is the path
   that makes a reply feel quick.
2. **The service says not finished.** The client waits for a further silence
   and then sends anyway. No model is allowed to leave somebody waiting with no
   answer to their question.
3. **No answer at all** - the model is not installed, the service is older, the
   probe has not returned. The plain silence threshold ends the turn.

The candidate pause is `ECHOTURN_SPECULATE_MS` (300 ms). The fallback is
`ECHOTURN_VAD_END_MS` (600 ms), or `ECHOTURN_VAD_END_CALL_MS` (700 ms) inside a
call, where a pause in the middle of a thought is shorter than it looks on a
keyboard.

A pause is asked about **once**. Asking again on the same pause is asking the
same question about the same audio, and each ask is a transcription. Speech
starting again is what makes the next pause a new question.

### What the service answers with

`POST /api/transcribe` answers three things about one recording in one request:
the words, how much of it was speech, and whether the speaker had finished.

| key | from | when it is absent |
|---|---|---|
| `text` | the recogniser | never (an empty string is an answer) |
| `vad.engine`, `vad.speech_ms` | `echoturn.vad` | the audio is not 16 kHz mono |
| `vad.fallback`, `vad.reason` | the detector that actually ran | when the model ran |
| `turn.complete`, `turn.prob` | `echoturn.endpoint` | no model, or switched off |

`turn` is **absent** rather than false when there is no verdict. A judge that
answers "not finished" and is wrong leaves somebody waiting for a reply that
never comes, so absence has to be distinguishable from a verdict.

### The speech measurement

Two engines, one shape of answer. `ECHOTURN_VAD_ENGINE` picks:

| engine | what it measures | needs |
|---|---|---|
| `silero` (default) | how much real speech there was | `onnxruntime`, a model file |
| `energy` | how loud it was | `numpy` |

`build_vad()` reports which one ran, and `fallback: true` with a `reason` when
the model was asked for and not found. That is a different situation from a host
that turned the model off, and it must not read the same from the outside: the
second is discovered weeks later, by a user complaining that they keep being
talked over.

Both reduce audio to one number per 32 ms block and share the same rule for
counting, in `echoturn.vad.segments`:

* a silence shorter than 100 ms inside a sentence does not end it;
* a segment shorter than 100 ms is dropped - that is a knock, a click, a breath;
* the result is the length of *speech*, not the length of audio, and the
  difference between them is most of a pause.

`ECHOTURN_MIN_SPEECH_MS` (300 ms) is the gate: below it, the recording never
reaches the recogniser.

### When nothing can measure it

The client is not left with nothing. `EnergyVad`'s own floor is documented as a
starting point rather than a measured value - about -34 dBFS - and the client's
local silence cursor runs regardless of what the service says. A service that is
down, slow or refusing costs latency, not the turn.

## Interrupting

The test is not a level. It is `max(floor, echo * ratio)`, **sustained**:

| constant | value | why |
|---|---|---|
| `ECHOTURN_BARGE_MS` | 700 ms | a chair, a door and a cough all produce one loud frame |
| `ECHOTURN_BARGE_FLOOR` | 0.10 | an absolute floor, so breathing and keyboards never reach it |
| `ECHOTURN_BARGE_RATIO` | 3.5 | against the level the reply is coming back at |

Requiring the level to *hold* is what separates a voice from a noise, and it is
why a listener has to say more than one syllable to be heard over a reply. With
the ratio too low, a listener on loudspeakers interrupts themselves halfway
through every reply.

### Measuring the echo

`clients/echo.js` learns how loud the speaker comes back through the
microphone. `ECHOTURN_BARGE_FLOOR` and `ECHOTURN_BARGE_RATIO` are the two
numbers that need it.

* The window opens when the **first sound** comes out of the speaker, not when
  the turn starts. There is one or two seconds of model and first synthesis in
  between, and a window opened at the turn would be over before there was
  anything to learn.
* `GUARD_MS` (500 ms) of that window is listen-only. Nothing said during it can
  count as an interruption, on the grounds that the client has not yet measured
  what it needs to judge with.
* The reference follows a value **below** it quickly (0.25 per frame) and one
  **above** it slowly (0.02). That asymmetry is the protection: one loud frame
  must not drag the gate up to where a voice cannot reach it, which would turn
  interrupting off without saying so.
* The summary is an 80th percentile over at most `SAMPLES_MAX` (120) frames,
  which is generous for a 60 Hz meter.

### What happens to the audio heard while the reply was being made

The client keeps it. `clients/ring.js` holds what was said during the reply -
`ECHOTURN_BARGE_MS * 4`, four times the length of an interruption - and
`PREROLL_MS` (200 ms) of what came before that.

The carry is taken **before** the turn is stopped. Stopping a turn throws away
everything waiting in a buffer, so taking it afterwards leaves the interruption
with nothing to say - which is how a listener reports only being heard from
their second word onwards.

What was said while the reply was still being *written* is kept the same way.
There is nothing to interrupt yet, but the reply starting is usually what stops
somebody mid-sentence, and dropping those frames loses the first half of the
sentence they were saying.

### Stopping a turn

`stopTurn()` raises a sequence number, aborts the fetch, stops the queue and
resets the echo and gate. The sequence number is what actually stops an older
turn from touching anything: the abort races the socket, and the older turn's
events still arrive.

The **echo window and the interruption count are deliberately not reset** when
the turn's stream ends. They describe the sound, not the request, and the last
chunk of a reply is still coming out of the speaker for a second or more after
the stream that asked for it has finished. Clearing them there closes a window
that was just opened, and makes the tail of every reply impossible to interrupt.

## One live turn per conversation

`echoturn.integrations.starlette.LiveTurns` holds one live turn per key, and the
newest one wins: the older turn's `cancel` is set, so its audio stops rather than
interleaving with the new reply. The client does the same thing from its side.
Both are needed - a client that gets it wrong should not be able to corrupt the
record, and a server that only trusts the client cannot stop a turn whose socket
has gone away.

## What is not here

There is no "say a keyword to interrupt" and no intent detection for "answer me
with voice now". The reply mode is what the host decided when the turn started.
A rule that guessed it from the words would be wrong in the cases that matter
and right in the cases that do not.
