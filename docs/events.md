# Events

Chinese: [events.zh-CN.md](events.zh-CN.md)

One turn is a stream of plain dictionaries. It is a stream rather than a
callback API because the consumer is almost always something that has to send
them somewhere - an SSE response, a websocket, a queue - and because a stream is
the only shape that survives the three things a turn does at once.

`echoturn.events` is the module that builds them, and `EVENT_TYPES` is the list.

## The seven events

| event | fields | meaning |
|---|---|---|
| `ack` | `id` | the message is committed, under this id |
| `sink` | `audio_sink`, `notice` | where the audio comes out |
| `sentence` | `i`, `text` | one speakable sentence of message `i` |
| `audio` | `idx`, `i`, `mime`, `data` | one WAV chunk, base64, position `idx` |
| `aborted` | `reason` | the turn was stopped. Terminal |
| `done` | `reply`, `timings`, `warnings`, `extra` | the finished turn. Terminal |
| `error` | `error` | the turn failed. Terminal |

`aborted`, `done` and `error` are `echoturn.events.TERMINAL`: exactly one of
them ends a stream, and nothing follows it. Three endings rather than one
because "she finished", "we stopped her" and "it broke" need different words on
screen and should not be inferred from an empty reply.

### `ack`

Sent before any money is spent and before anything slow. It is what lets a
client tell "never arrived" from "arrived, and was then interrupted" - without
it both look like a request that failed, and the user retypes a message that was
received the first time.

`id` is `TurnInput.message_id` when the host supplies one, and a generated hex
string when it does not.

### `sink`

Sent second, always. It exists so that deciding where the audio comes out cannot
delay the reply: a host that routes audio somewhere else - a phone, a queue, a
file - answers here rather than inside synthesis. `notice` is shown to a person
as-is; the shipped value is empty.

Today the only value this package emits is `"browser"`, because `clients/` is
the only client it ships. The event is not a placeholder: replacing it is how a
host changes the answer.

### `sentence`

The subtitle stream, and it arrives before the audio does. `i` is which of the
turn's messages the sentence belongs to.

What travels here is the text of each **synthesis request**, not the sentences
of the reply. Those are different things: a chunk is cut to a character budget
and may hold two short sentences, and joining the `sentence` events back
together does not reproduce `done.reply`. `done.reply` is what was said.

Nothing written for a program to read is ever spoken. A fenced block and a JSON
object are removed before the words reach synthesis, and before they reach a
bubble; an object is only removed when it really parses as one, and a brace that
opens a line and never closes is dropped as half a contract. Braces in prose are
left alone. A reply that is nothing but an object therefore produces no
`sentence` and no `audio`, while `done.reply` still carries the object: a host
that asked for structured output can read what a voice cannot say.

### `audio`

One WAV chunk as base64, with `idx` as its position in the turn.

**`idx` is the ordering key, and it is not a hint.** Chunks are synthesised in
parallel and finish out of order as a matter of course, so a client that plays
them as they arrive plays two sentences interleaved. Hold a chunk until every
chunk before it has been played.

WAV rather than raw samples because the browser then decodes it without being
told the sample rate, the channel count or the encoding - three things a speech
provider is free to choose, and three things a client that guessed would get
wrong silently.

`i` is which message the chunk belongs to. A long reply can carry several.

### `aborted`

`reason` is a short word for the client to choose its wording with. The one this
package emits is `"superseded"`: a newer turn replaced this one, or the client
disconnected - the caller cannot tell those apart and does not need to.

An interrupted turn has usually already emitted some `audio`. That audio was
said out loud, so a host recording the conversation should write what actually
made it out rather than nothing.

### `done`

| key | what it holds |
|---|---|
| `reply` | the whole reply, cleaned, as text |
| `timings.first_token_ms` | when the model's first piece arrived |
| `timings.first_audio_ms` | when the first chunk was ready to play |
| `timings.total_ms` | the whole turn |
| `timings.chunks` | how many chunks were submitted |
| `warnings` | parts that worked badly, above all a chunk that never spoke |
| `extra.input_kind` | what the host labelled this turn |

`warnings` is not for things that broke the turn - those are `error` events. It
is for a chunk of speech that failed to synthesise: the text is still in
`reply` and can still be read, and the caller deserves to know it was never
spoken. The format is `"chunk 3: ProviderError"`.

`first_token_ms` and `first_audio_ms` are `None` when they never happened, which
is the honest answer for a text-only turn.

### `error`

`error` is safe to put in front of a person. The exception text is not, and
belongs in the host's log: it carries URLs, keys and internal paths.
`echoturn.errors.safe_message` is what decides which of the two a message is.

## Order

Guaranteed:

* `ack`, then `sink`, then anything else;
* `sentence` and `audio` interleave freely (subtitles lead the voice, by design);
* `audio` events are emitted in `idx` order, however they finished;
* one terminal event, last;
* nothing after the terminal event.

Not guaranteed:

* that `sentence` and `audio` alternate;
* that `i` increases monotonically within `audio` (a chunk belonging to message
  0 can be emitted after one belonging to message 1).

## Over the wire

`echoturn.events.encode` writes one frame per event, exactly:

```
data: {"type":"sentence","i":0,"text":"Hello there."}\n\n
```

Text is not escaped to ASCII. Every hop between here and a browser is UTF-8, and
`\uXXXX` escapes would triple the size of a Chinese reply for no benefit anybody
can observe.

`echoturn.integrations.starlette.sse_response` is the whole bridge: a
synchronous generator on its own thread, pushing into an asyncio queue, with
`Cache-Control: no-cache`, `Connection: keep-alive` and `X-Accel-Buffering: no`
- the last of which is what stops a proxy from turning a stream into a reply
that arrives all at once at the end.

## Reading it from JavaScript

`clients/stream.js` parses these frames. The one rule worth repeating:

```js
const { events, rest } = splitFrames(carry);
```

A chunk boundary does not respect a frame boundary - a read can stop in the
middle of a JSON object - so the tail is carried to the next read and only a
complete frame is parsed. A frame that carries nothing readable is counted, not
thrown: one lost sentence is not a lost reply.
