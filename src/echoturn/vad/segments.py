"""Turn a stream of speech probabilities into a length of speech.

Both engines in this package reduce audio to one number per block and then have
to answer the same question: how much of this was somebody talking. The rule is
here, once, in plain Python, so that the cheap engine and the model agree on what
a word like "speech length" means.

Three decisions are folded into that rule, and they are all about the same
mistake - counting something that was not speech:

* A short silence inside a sentence does not end it. Block-level gaps below the
  limit are ignored and the segment continues.
* A short segment is dropped rather than counted. A knock on a desk clears any
  level threshold for a few tens of milliseconds, and reported as speech it makes
  the caller believe somebody said a word.
* Deliberately, the result is the length of speech and not the length of audio.
  A caller gating on "did they say a whole sentence" needs the first, and the
  difference between them is most of a pause.
"""
from __future__ import annotations

from collections.abc import Iterable

# One analysis block. 32 ms is what the model consumes in one step at 16 kHz, and
# keeping the cheap engine on the same grid means the two report comparable
# numbers rather than numbers that differ by their own block size.
BLOCK_MS = 32.0
# Probability above which a block counts as speech.
THRESHOLD = 0.5
# Silence long enough to separate two segments. Below this it is a pause inside a
# sentence, which is normal in every language.
MIN_SILENCE_MS = 100.0
# Segments shorter than this are dropped: that is a knock, a click or a breath.
MIN_SEGMENT_MS = 100.0


def speech_ms(
    probs: Iterable[float],
    *,
    block_ms: float = BLOCK_MS,
    threshold: float = THRESHOLD,
    min_silence_ms: float = MIN_SILENCE_MS,
    min_segment_ms: float = MIN_SEGMENT_MS,
) -> int:
    """Milliseconds of speech in a sequence of per-block probabilities.

    Rounds to whole milliseconds because callers compare this against a
    configured threshold in milliseconds, and a fraction there is a comparison
    nobody can reproduce.
    """
    total = 0.0
    current = 0.0
    silence = 0.0
    for prob in probs:
        if prob > threshold:
            current += block_ms
            silence = 0.0
            continue
        silence += block_ms
        if silence >= min_silence_ms:
            if current >= min_segment_ms:
                total += current
            current = 0.0
    if current >= min_segment_ms:
        total += current
    return int(round(total))


def mean_speech_prob(probs: Iterable[float], *, threshold: float = THRESHOLD) -> float:
    """How confident the speech blocks were, or 0.0 if there were none.

    Reported for logs and dashboards. It deliberately does not take part in the
    decision above: averaging a probability across a whole recording mixes
    confident speech with confident silence and produces a number that describes
    neither.
    """
    hits = [float(prob) for prob in probs if prob > threshold]
    return sum(hits) / len(hits) if hits else 0.0
