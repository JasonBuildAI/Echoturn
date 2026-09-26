// Reading a turn off the wire.

/** The two routes this client calls. A host may point them elsewhere. */
export const TURN_PATH = "/api/turn";
export const TRANSCRIBE_PATH = "/api/transcribe";
// The route a host may serve to open its providers' connections before anybody
// speaks. It is named here for the same reason as the other two - the client
// knows what a turn is and a page does not - but unlike them it is not a default:
// a call only asks when a host hands it this URL (see ``Call``'s ``warmUrl``),
// because a host without the route should not pay a 404 on every call.
export const WARM_PATH = "/api/call/start";

// The prefix every data frame carries. Server-sent events reserve a few other
// field names, and a frame can carry nothing but a comment.
const DATA = "data: ";

function parseFrame(frame) {
  for (const line of frame.split("\n")) {
    if (!line.startsWith(DATA)) continue;
    try {
      return JSON.parse(line.slice(DATA.length));
    } catch {
      return null;
    }
  }
  return undefined;
}

/**
 * Split whatever has arrived into whole events, keeping the partial one.
 *
 * Chunk boundaries do not respect frame boundaries: a read can stop in the
 * middle of a JSON object, and parsing that fragment fails for a reason that
 * has nothing to do with the reply. So the tail is carried to the next read and
 * only a complete frame - one ending in a blank line - is ever parsed.
 *
 * `broken` counts frames that carried no readable event. Counted rather than
 * thrown: one unreadable frame is one lost sentence, and the rest of the turn
 * is still worth having.
 */
export function splitFrames(buffer) {
  const events = [];
  let broken = 0;
  let rest = buffer;
  for (;;) {
    const edge = rest.indexOf("\n\n");
    if (edge < 0) break;
    const frame = rest.slice(0, edge);
    rest = rest.slice(edge + 2);
    const event = parseFrame(frame);
    if (event === undefined) continue;
    if (event === null) broken += 1;
    else events.push(event);
  }
  return { events, rest, broken };
}

/**
 * Post a turn and hand each event to `onEvent` as it arrives.
 *
 * Read as a stream rather than awaited as a whole body, because the whole point
 * of sending events is that the first sentence is ready long before the last
 * one. Awaiting the body would hold the first sound until the end of the reply,
 * which is the one delay a listener notices.
 */
export async function streamTurn({
  url = TURN_PATH,
  body,
  signal = undefined,
  fetch: fetchImpl = globalThis.fetch,
  onEvent = null,
} = {}) {
  const response = await fetchImpl(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(`the service answered ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let carry = "";
  let broken = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    carry += decoder.decode(value, { stream: true });
    const split = splitFrames(carry);
    carry = split.rest;
    broken += split.broken;
    if (onEvent) for (const event of split.events) onEvent(event);
  }
  return { broken };
}

/**
 * Ask the service something and read one JSON answer.
 *
 * A failure here is an answer of its own: no verdict. The caller already has a
 * path for that - the plain silence threshold - so a service that is down, slow
 * or refusing costs a little latency rather than the turn. It is not silent
 * either: `null` comes back and the caller decides what to say about it.
 */
export async function askService({
  url,
  body,
  signal = undefined,
  fetch: fetchImpl = globalThis.fetch,
} = {}) {
  try {
    const response = await fetchImpl(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}
