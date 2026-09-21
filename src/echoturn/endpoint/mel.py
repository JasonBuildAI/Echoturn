"""Log-mel features in the shape a speech model expects, in numpy.

The endpointing model is an encoder trained on log-mel spectrograms, so what it
is handed has to match how those spectrograms were computed: 25 ms windows, 10 ms
hops, 80 mel bands on a Slaney scale, a base-10 logarithm, and a normalised
waveform. Any one of those being different does not raise anything. It moves the
model's output somewhere meaningless, which is far worse: leaving out the
waveform normalisation alone takes the probability of a finished sentence from
0.97 to around 0.5, where every answer is a coin toss.

This is written against the reference features rather than against a framework.
Pulling in a deep-learning stack for 400-point FFTs and one triangular filter
bank would be two gigabytes of dependency for a few hundred lines of arithmetic.

All the numbers below are properties of the trained model and are not tunable.
"""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
WINDOW = 400
HOP = 160
MELS = 80
CHUNK_SAMPLES = SAMPLE_RATE * 8
# The floor the logarithm is taken above, so that a silent bin is a small number
# and not negative infinity.
CLIP_FLOOR = 1e-10
# The variance floor in the waveform normalisation, for a waveform that is
# entirely silent.
NORM_EPS = 1e-7
# Dynamic range kept below the loudest band, and the scale the result is put on.
DYNAMIC_RANGE_DB = 8.0
SCALE = 4.0


def hz_to_mel(freq):
    """Slaney's scale: linear below 1 kHz, logarithmic above it."""
    f = np.atleast_1d(np.asarray(freq, dtype=np.float64))
    mel = 3.0 * f / 200.0
    high = f >= 1000.0
    mel[high] = 15.0 + np.log(f[high] / 1000.0) * (27.0 / np.log(6.4))
    return mel


def mel_to_hz(mel):
    """The inverse of :func:`hz_to_mel`."""
    m = np.atleast_1d(np.asarray(mel, dtype=np.float64))
    f = 200.0 * m / 3.0
    high = m >= 15.0
    f[high] = 1000.0 * np.exp((m[high] - 15.0) * (np.log(6.4) / 27.0))
    return f


def filterbank() -> np.ndarray:
    """Triangular mel filters, area-normalised, as (bins, mels)."""
    edges = mel_to_hz(
        np.linspace(hz_to_mel(0.0)[0], hz_to_mel(SAMPLE_RATE / 2.0)[0], MELS + 2)
    )
    frequencies = np.linspace(0.0, SAMPLE_RATE / 2.0, WINDOW // 2 + 1)
    gaps = np.diff(edges)
    slopes = edges[np.newaxis, :] - frequencies[:, np.newaxis]
    triangle = np.maximum(
        0.0, np.minimum(-slopes[:, :-2] / gaps[:-1], slopes[:, 2:] / gaps[1:])
    )
    area = (2.0 / (edges[2:] - edges[:-2]))[np.newaxis, :]
    return triangle * area


# A periodic Hann window, not the symmetric one numpy builds by default. One
# extra sample makes every frame slightly different, and eight hundred frames of
# slightly different add up to a probability that is no longer the model's.
WINDOW_FUNCTION = np.hanning(WINDOW + 1)[:-1]
FILTERS = filterbank()


def log_mel(audio, *, normalize: bool = True) -> np.ndarray:
    """(mels, frames) features for a 16 kHz waveform.

    Anything shorter than the model's window is padded at the end and anything
    longer is cut from the front. Which end matters is the caller's business: a
    turn-ending decision needs the most recent speech, and that alignment happens
    where the decision is made rather than here.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size < CHUNK_SAMPLES:
        x = np.pad(x, (0, CHUNK_SAMPLES - x.size))
    elif x.size > CHUNK_SAMPLES:
        x = x[:CHUNK_SAMPLES]
    if normalize:
        x = (x - x.mean()) / np.sqrt(x.var() + NORM_EPS)
    pad = WINDOW // 2
    padded = np.pad(x.astype(np.float64), (pad, pad), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, WINDOW)[::HOP]
    spectrum = np.fft.rfft(frames * WINDOW_FUNCTION, axis=-1)
    power = (spectrum.real ** 2 + spectrum.imag ** 2).T
    mel = np.maximum(CLIP_FLOOR, FILTERS.T @ power)
    out = np.log10(mel)[:, :-1]
    out = np.maximum(out, out.max() - DYNAMIC_RANGE_DB)
    return ((out + SCALE) / SCALE).astype(np.float32)
