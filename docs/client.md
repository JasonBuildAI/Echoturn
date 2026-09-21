# The browser client

Chinese: [client.zh-CN.md](client.zh-CN.md)

`clients/` is a set of ES modules with no build step. A page imports them
directly:

```html
<script type="module">
  import { Call } from "/client/echoturn-client.js";
</script>
```

`worklet.js` has to sit next to the module that loads it - `mic.js` resolves the
processor against its own URL - so copying the directory is enough, and a host
that serves it from a subdirectory does not have to configure anything.

## Two ways to use it

**`Call` is the whole conversation**: a microphone, ordered playback,
subtitles, and the three decisions in between. A page that wants a voice call
and nothing else needs this one export.

**The rest are the parts it is built from**, because a page that already has its
own conversation state, its own player or its own microphone handling should be
able to take the piece it needs. They are modules with no state of their own, so
mixing them is not a second implementation of anything.

## The modules

| module | what it is |
|---|---|
| `worklet.js` | the AudioWorklet processor: one block of samples and its level |
| `mic.js` | opening one microphone stream, with a fallback path |
| `levels.js` | the speech floor, the noise reference, percentile |
| `echo.js` | how loud the reply comes back through the microphone |
| `interrupt.js` | requiring a level to hold before it is an interruption |
| `cursor.js` | what a pause means: keep, ask, send, drop |
| `ring.js` | bounded frame buffers, and the carry |
| `queue.js` | decoding and playing chunks in order, without a seam |
| `wav.js` | frames to 16 kHz mono WAV |
| `base64.js` | one base64 implementation, chunked for long clips |
| `stream.js` | reading a turn's events off a streamed response |
| `dials.js` | the settings, and what is used before the service answers |
| `call.js` | the wiring between all of the above |
| `echoturn-client.js` | the entry point that re-exports them |

## A call, end to end

```js
const call = new Call({
  session: "demo",
  onTurn: (text) => show("you", text),
  onSubtitle: (sentence, i) => show("her", sentence, i),
  onState: (state) => label(state),
  onNotice: (text) => note(text),
});

button.onclick = () => call.start();     // the gesture the audio context needs
call.say("hello");                        // or type instead of talking
call.setMuted(true);                      // stop listening, keep the call
call.interrupt();                         // stop the reply
call.stop();                              // close the microphone
```

`start()` loads the settings from `/config` and opens the microphone. It returns
false when the microphone refuses, having already said why through `onNotice`.

## The state it reports

| state | meaning |
|---|---|
| `idle` | nothing is happening |
| `listening` | the microphone is open and somebody is being listened to |
| `thinking` | a turn is running and no sound has come back yet |
| `speaking` | the reply is audible |

`speaking` is checked before `thinking`, and it is about **sound** rather than
about the request. The last chunk of a reply is still coming out of the speaker
for a second or more after the stream that asked for it has ended, and a client
that asked only about the turn would treat its own reply as silence - on
loudspeakers it records the tail of what it is saying and then answers it.

## The three states that look like two

`busy`, `capturing` and `ending` are three different things and the microphone
is open through all of them. A turn that is running is not a recording that has
stopped, and a recording being transcribed is not a turn. Collapsing any two
loses the audio said in between, which is the failure a listener reports as "she
was not listening to me".

## Nothing here holds a threshold

`dials.js` carries a fallback for each number, and it is used only until
`/config` answers. After that the service's table is what the client reads.

That is the point: a page with its own copy of `barge_ratio` keeps using it
after the service has changed, and both look correct in isolation. The fallback
exists so that a page whose very first request fails still has something to work
with, and its values are the same ones the service ships.

A value that is not a number falls back, and so does a **blank** one - which
would otherwise arrive as zero, pass every "is it finite" check, and silence the
threshold it belongs to. A key with no fallback throws, because that is a
mistake in the caller rather than something to absorb.

## Playback

`queue.js` schedules each chunk to begin where the previous one ends, on the
audio clock, so the join is sample-accurate rather than dependent on how quickly
a new element loads. The lead is `LEAD_SEC` (15 ms): starting exactly "now" is a
race the clock usually wins, and a source started in the past begins mid-sample
or not at all.

Decoding starts the moment a chunk arrives and does not wait its turn. It is the
slow part, it can finish out of order, and holding it back behind the previous
chunk's playback adds its whole cost to the gap between sentences.

`stop()` raises a generation number, so a chunk still being decoded is discarded
on its way out rather than played after the interruption - which is how a
stopped reply says two more sentences anyway.

## Capture

`mic.js` opens one stream at a time. Asking for the microphone is asynchronous
and shows a permission prompt that can hang for seconds; a second click during
that window opens a *second* stream, which overwrites the first and leaves it
running with nobody holding a reference to stop it. The symptom is a recording
indicator that stays on with nothing in the interface able to turn it off.

A refusal is not kept: a rejected attempt that was cached would be handed to
every later caller, so one refusal would become permanent and the button would
look broken until the page was reloaded.

The AudioWorklet is the path that is taken, and the fallback to a
`ScriptProcessorNode` is not a preference - it is the difference between a
working microphone and a dead one on a platform where the worklet resolves and
never registers its processor.

## Loading and testing

```bash
node --check clients/echoturn-client.js     # parse only
node --test "clients/tests/*.test.js"       # the behaviour
python -m pytest tests/test_client.py       # the same, from the Python side
```

The tests run under Node with no browser and no bundler. `clients/tests/fakes.js`
holds the stand-ins: a microphone the test pushes frames through, a fetch that
answers the three routes, an offline audio context that renders by taking every
*n*-th sample.
