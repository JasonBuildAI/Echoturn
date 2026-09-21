// Base64, both ways, for audio that travels as text.

// How much of the string is built per call. `String.fromCharCode` takes its
// arguments on the stack, so a large clip turned into one call for the whole
// buffer throws "too many arguments" - at a length that depends on the platform,
// which is the kind of limit that works everywhere except where it matters.
const CHUNK = 0x8000;

/** The bytes behind a base64 string. */
export function bytesFromBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** The base64 text for bytes. Accepts an ArrayBuffer or any typed array. */
export function toBase64(buffer) {
  const bytes = buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : buffer;
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}
