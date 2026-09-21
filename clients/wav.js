// Turning captured frames into a file a recogniser will accept.

// The rate speech recognition is sent at.
//
// Sixteen kilohertz carries the whole band speech needs, and a recording at the
// context's rate is three times the size for the part of the spectrum that
// carries nothing. Upload time sits in the most sensitive wait there is - the
// one between somebody finishing a sentence and seeing their words - so the
// three times is paid exactly where it is felt most.
export const ASR_RATE = 16000;

function defaultOffline(channels, length, rate) {
  const Ctor = globalThis.OfflineAudioContext || globalThis.webkitOfflineAudioContext;
  return new Ctor(channels, length, rate);
}

/** Every frame's samples in one array, in the order they were captured. */
export function flatten(frames) {
  let total = 0;
  for (const frame of frames) total += frame.length;
  const flat = new Float32Array(total);
  let offset = 0;
  for (const frame of frames) {
    flat.set(frame, offset);
    offset += frame.length;
  }
  return flat;
}

/**
 * One channel of 16-bit PCM with a WAV header in front of it.
 *
 * Built by hand rather than by a codec because there is no codec for this: the
 * browser can decode audio and cannot encode it. The header is the whole
 * format - a recogniser reading it learns the rate, the width and the channel
 * count, which is exactly what a provider is free to choose otherwise.
 */
export function encodeWav(samples, sampleRate) {
  const count = samples.length;
  const buffer = new ArrayBuffer(44 + count * 2);
  const view = new DataView(buffer);
  const text = (offset, value) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + count * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // 1 = uncompressed PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, count * 2, true);

  const pcm = new Int16Array(buffer, 44);
  for (let i = 0; i < count; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i]));
    // The negative side reaches one step further than the positive one, which
    // is what two's complement gives: -1 is -32768 and +1 is 32767.
    pcm[i] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return buffer;
}

/**
 * `samples` at another rate, using the platform's own resampler.
 *
 * Not decimation. Dropping samples is fine when the rates divide evenly - 48 to
 * 16, every third one - and an aliasing mess when they do not, and the rates
 * that do not divide evenly are exactly the ones real hardware reports, like
 * 44.1 kHz. A resampler with a proper filter is available in every browser, so
 * there is no reason to write a worse one.
 */
export async function resample(samples, from, to, { createOffline = defaultOffline } = {}) {
  const length = Math.max(1, Math.ceil((samples.length * to) / from));
  const offline = createOffline(1, length, to);
  const buffer = offline.createBuffer(1, samples.length, from);
  buffer.copyToChannel(samples, 0);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0);
}

/** The captured frames as 16 kHz mono WAV. */
export async function wav16k(
  frames,
  sampleRate,
  { rate = ASR_RATE, createOffline = defaultOffline } = {},
) {
  const flat = flatten(frames);
  // Already the right rate: rendering it again would cost a full pass over the
  // audio and return the same samples. Nothing recorded at all is worth the
  // same answer - a resampler asked for zero samples still hands back one, and
  // a file with an invented sample in it is worse than an empty one.
  if (sampleRate === rate || !flat.length) return encodeWav(flat, rate);
  const resampled = await resample(flat, sampleRate, rate, { createOffline });
  return encodeWav(resampled, rate);
}
