"""Measure and correct the pitch of a synthesised clip.

Why this exists: a prompt can ask a synthesis model to keep one voice, and it
still will not. Measured across twelve emotions of one voice, the spread between
groups was the same order of magnitude as the model's own run-to-run spread -
the remaining variation is not something the prompt provoked, it is sampling
noise. Correcting it is therefore a signal-processing job, not a prompt job.

Two costs come with the correction, which is why it is off unless asked for:
phase-vocoder shifting has an audible smeared quality, and it needs the whole
clip, which rules out pushing audio out as it is synthesised. Both are real
trade-offs against a first sound that arrives sooner.

The correction is only applied when the clip is meaningfully off target. Pulling
every clip toward one number would flatten the intonation that carries emotion;
the goal is to stop "this take came out two semitones high", not to remove
expression.

The estimate is a difference function read through its cumulative mean, which is
the short way to say: find the lag at which the signal most resembles itself,
discounting lags that only look good because the frame is short. A plain
autocorrelation peak is happy to report half the true pitch, and half the true
pitch is what a listener hears as "a different person".
"""
from __future__ import annotations

import math

from . import _phase
from ._dsp import numpy

# A mid-range target for a voice, in hertz. Set it to the median of the voice you
# actually use, so that most clips need no correction at all.
DEFAULT_TARGET_HZ = 242.0
MIN_TARGET_HZ = 60.0
MAX_TARGET_HZ = 500.0
# Below this the difference is under 15 cents and nobody can hear it, while the
# processing still leaves its own artefact behind.
MIN_SHIFT_SEMITONES = 0.15
# A quarter of a second: shorter than that and a pitch estimate is guesswork.
MIN_SECONDS = 0.25
VOICED_RMS_FLOOR = 0.15
PCM_SCALE = 32768.0
# The span a human voice occupies. Anything outside it is a different sound, not
# a different person, and reporting it would only pull the correction off target.
MIN_HZ = 70.0
MAX_HZ = 350.0
# A frame of 40 ms every 10 ms: one period of the lowest pitch searched for, and
# an estimate ten times a second, which is enough to see a pitch track move.
FRAME_SECONDS = 0.04
HOP_SECONDS = 0.01
# Above this the lag is a coincidence rather than a repeat. The usual value for
# this test, and the one that keeps a breathy voice from being read as a note.
APERIODICITY_LIMIT = 0.15


def semitone_distance(source_hz: float, target_hz: float) -> float:
    """Signed distance in semitones from ``source_hz`` to ``target_hz``."""
    if source_hz <= 0 or target_hz <= 0:
        return 0.0
    return 12.0 * math.log2(target_hz / source_hz)


def clamp_target(hz: float) -> float:
    """Keep a configured target inside the range a human voice can occupy."""
    value = float(hz)
    return value if MIN_TARGET_HZ <= value <= MAX_TARGET_HZ else DEFAULT_TARGET_HZ


def _frame_hz(np, frame, sample_rate: int) -> float:
    """Fundamental of one frame, or 0.0 when the frame has no usable period."""
    min_lag = max(2, int(sample_rate / MAX_HZ))
    max_lag = min(len(frame) - 1, int(sample_rate / MIN_HZ))
    if max_lag <= min_lag:
        return 0.0
    size = 1
    while size < 2 * len(frame):
        size *= 2
    spectrum = np.fft.rfft(frame, size)
    energy = np.fft.irfft(spectrum * np.conj(spectrum), size)[:max_lag + 1]
    squared = frame ** 2
    # A leading zero so that the running totals can be indexed by lag, including
    # the lag of zero, without a special case.
    running = np.concatenate([np.zeros(1), np.cumsum(squared)])
    total = float(squared.sum())
    lags = np.arange(max_lag + 1)
    head = running[len(frame) - lags]
    tail = total - running[lags]
    # Sum of squared differences between the frame and itself shifted by lag,
    # assembled from the autocorrelation and the two partial energies.
    difference = np.maximum(head + tail - 2.0 * energy, 0.0)
    mean = np.cumsum(difference[1:])
    normalized = np.ones_like(difference)
    normalized[1:] = difference[1:] * lags[1:] / np.maximum(mean, 1e-12)
    search = normalized[min_lag:max_lag + 1]
    below = np.flatnonzero(search < APERIODICITY_LIMIT)
    if not len(below):
        return 0.0
    # The lowest point of the first run that stays under the limit, not the point
    # where it first drops under it and not the lowest point overall. The first
    # lag under the limit is still on the way down; the lowest point overall is
    # as likely to be two periods out, and two periods out is half the pitch.
    gaps = np.flatnonzero(np.diff(below) > 1)
    run_end = int(below[gaps[0]]) if len(gaps) else int(below[-1])
    start = int(below[0])
    lag = min_lag + start + int(np.argmin(search[start:run_end + 1]))
    # Straight-line interpolation over the dip: the true period almost never
    # lands on a whole sample, and at 350 Hz one sample of lag is 5% of pitch.
    if min_lag < lag < max_lag:
        left, middle, right = normalized[lag - 1], normalized[lag], normalized[lag + 1]
        curve = left - 2.0 * middle + right
        if curve > 0:
            lag += 0.5 * (left - right) / curve
    if lag <= 0:
        return 0.0
    return sample_rate / lag


def measure_f0(pcm: bytes, sample_rate: int = 24000) -> float:
    """Median fundamental frequency of the voiced frames, or 0.0 if unmeasurable.

    Silent frames are excluded before taking the median: including them drags
    the estimate toward whatever the estimator reports for noise, which is not a
    pitch at all.
    """
    np = numpy()
    samples = np.frombuffer(bytes(pcm or b""), dtype="<i2").astype(np.float64)
    samples = samples / PCM_SCALE
    frame_length = int(FRAME_SECONDS * sample_rate)
    hop = int(HOP_SECONDS * sample_rate)
    if len(samples) < max(int(sample_rate * MIN_SECONDS), frame_length):
        return 0.0
    count = 1 + (len(samples) - frame_length) // hop
    frames, loudness = [], []
    for i in range(count):
        frame = samples[i * hop:i * hop + frame_length]
        frames.append(frame)
        loudness.append(math.sqrt(float((frame ** 2).mean())))
    floor = max(max(loudness) * VOICED_RMS_FLOOR, 1e-5)
    pitched = [
        hz
        for frame, level in zip(frames, loudness, strict=True)
        if level > floor and (hz := _frame_hz(np, frame, sample_rate))
    ]
    return float(np.median(pitched)) if pitched else 0.0


def lock_pitch(
    pcm: bytes,
    sample_rate: int = 24000,
    *,
    target_hz: float = DEFAULT_TARGET_HZ,
    min_semitones: float = MIN_SHIFT_SEMITONES,
) -> bytes:
    """Shift a whole clip onto ``target_hz`` when it is far enough off.

    Duration and intonation contour are untouched: only the pitch centre moves.
    Returns the input unchanged when the pitch cannot be measured or when the
    distance is below the threshold. The result is exactly as long as the input,
    because the caller has usually already said how long the clip would be.
    """
    np = numpy()
    raw = bytes(pcm or b"")
    measured = measure_f0(raw, sample_rate)
    if measured <= 0:
        return raw
    steps = semitone_distance(measured, clamp_target(target_hz))
    if abs(steps) < min_semitones:
        return raw
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / PCM_SCALE
    shifted = _phase.fit_length(
        np, _phase.pitch_shift(np, samples, steps), len(samples)
    )
    clipped = np.clip(shifted * PCM_SCALE, -PCM_SCALE, PCM_SCALE - 1)
    return clipped.astype("<i2").tobytes()
