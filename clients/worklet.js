// Forward microphone frames to the page.
//
// Loaded with `audioWorklet.addModule(url)` from a real URL rather than from a
// blob. Some Chrome versions resolve a blob module and then never run
// `registerProcessor`, and from the page that failure looks like a missing
// processor rather than a loading problem. A file served over HTTP has no such
// case.
//
// One call per 128 frames, which is the worklet block size. Nothing downstream
// counts blocks: every threshold in the client is expressed in milliseconds and
// converted with the context's sample rate, so a different block size would not
// quietly change what a threshold means.
class MicrophoneProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      let sum = 0;
      for (let i = 0; i < channel.length; i += 1) {
        sum += channel[i] * channel[i];
      }
      this.port.postMessage({
        rms: Math.sqrt(sum / channel.length),
        pcm: channel.slice(),
      });
    }
    // True keeps the processor alive. Returning false - or nothing - retires it
    // after the first block, and the microphone then looks open while nothing
    // arrives from it.
    return true;
  }
}

registerProcessor("echoturn-mic", MicrophoneProcessor);
