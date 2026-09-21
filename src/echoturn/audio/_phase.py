"""Change how fast a clip plays, and what pitch it plays at.

Two operations live here that look unrelated and are not: changing speed without
moving pitch, and moving pitch without changing duration. Both come out of the
same phase-vocoder core, so they share a module.

The cheap alternative for speed - dropping or repeating samples - also
transposes the voice, which is a worse artefact than the one it fixes. Keeping a
voice recognisably the same one is the whole point of exposing a speed dial.

Every function here takes the numpy module as its first argument. The numeric
stack is optional, so it cannot be imported at module import time, and passing
it in keeps the caller's one call to ``_dsp.numpy()`` the only place that knows
where it came from.
"""
from __future__ import annotations

# A 2048-sample window with a 512-sample hop: at the 24 kHz speech rate that is
# about 85 ms of context and about 21 ms between frames. Coarse enough to resolve
# the harmonics of a voice, fine enough to follow its pitch as it moves.
N_FFT = 2048
HOP = 512


def window(np):
    """The analysis window, periodic rather than symmetric.

    The frames overlap by three quarters, and it is the periodic window whose
    overlaps sum to a constant - with the symmetric one the reconstruction
    breathes at the frame rate.
    """
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(N_FFT) / N_FFT)


def stft(np, samples):
    """Short-time Fourier transform of a float signal, as (bins, frames)."""
    if len(samples) < N_FFT:
        samples = np.pad(samples, (0, N_FFT - len(samples)))
    padded = np.pad(samples, N_FFT // 2)
    frames = 1 + (len(padded) - N_FFT) // HOP
    starts = HOP * np.arange(frames)[:, None] + np.arange(N_FFT)[None, :]
    return np.fft.rfft(padded[starts] * window(np), axis=1).T


def istft(np, spectrum):
    """Inverse of :func:`stft`, back to float samples.

    Each frame is divided by the window energy that covered it rather than by a
    constant: the first and last frames are covered by fewer windows than the
    middle, and scaling them like the rest is what makes a clip click at both
    ends.
    """
    frames = np.fft.irfft(spectrum.T, n=N_FFT, axis=1) * window(np)
    total = HOP * spectrum.shape[1] + N_FFT
    out = np.zeros(total)
    energy = np.zeros(total)
    win_sq = window(np) ** 2
    for i in range(spectrum.shape[1]):
        start = i * HOP
        out[start:start + N_FFT] += frames[i]
        energy[start:start + N_FFT] += win_sq
    out = np.where(energy > 1e-9, out / np.maximum(energy, 1e-9), 0.0)
    return out[N_FFT // 2:N_FFT // 2 + HOP * spectrum.shape[1]]


def fit_length(np, samples, length):
    """Trim or zero-pad ``samples`` to exactly ``length`` samples.

    The transforms here land within a frame of the length they were asked for.
    A caller that has already told a client how long the audio will be needs the
    exact number, not the neighbouring one.
    """
    target = max(0, int(length))
    if len(samples) == target:
        return samples
    if len(samples) > target:
        return samples[:target]
    return np.pad(samples, (0, target - len(samples)))


def stretch(np, samples, rate):
    """Play ``samples`` at ``rate`` times their speed, pitch unchanged."""
    if rate == 1.0 or len(samples) == 0:
        return samples
    spectrum = stft(np, samples)
    bins, frames = spectrum.shape
    # The frequency each bin stands for, as phase per hop.
    omega = 2.0 * np.pi * HOP * np.arange(bins) / N_FFT
    steps = np.arange(0.0, frames, float(rate))
    # Two pad columns so the last step always has a right neighbour to read.
    tail = np.zeros((bins, 2), dtype=spectrum.dtype)
    padded = np.concatenate([spectrum, tail], axis=1)
    magnitude = np.abs(padded)
    phase = np.angle(padded)
    out = np.empty((bins, len(steps)), dtype=complex)
    phase_acc = phase[:, 0].copy()
    for t, step in enumerate(steps):
        left, frac = int(step), step - int(step)
        mag = (1.0 - frac) * magnitude[:, left] + frac * magnitude[:, left + 1]
        # How far the observed phase ran ahead of the bin it landed in - this is
        # the real frequency of the frame, not the frequency of the bin grid.
        delta = phase[:, left + 1] - phase[:, left] - omega
        delta -= 2.0 * np.pi * np.round(delta / (2.0 * np.pi))
        phase_acc += omega + delta
        out[:, t] = mag * np.exp(1j * phase_acc)
    return istft(np, out)


def resample_linear(np, samples, ratio):
    """Read ``samples`` at a different rate by straight-line interpolation.

    Output length is ``len(samples) / ratio``; a ratio above one shortens the
    clip and raises its pitch. It is deliberately plain interpolation: it is
    used to move a pitch and then corrected by :func:`stretch`, so a sharper
    filter would only cost time to be undone again.
    """
    if ratio == 1.0 or len(samples) < 2:
        return samples
    count = max(1, int(round(len(samples) / ratio)))
    positions = np.arange(count) * ratio
    left = np.floor(positions).astype(int)
    left = np.minimum(left, len(samples) - 2)
    frac = positions - left
    return samples[left] + (samples[left + 1] - samples[left]) * frac


def pitch_shift(np, samples, steps):
    """Move ``samples`` by ``steps`` semitones, duration unchanged."""
    if steps == 0 or len(samples) < 2:
        return samples
    ratio = 2.0 ** (float(steps) / 12.0)
    # Resampling moves the pitch and the duration together; the vocoder then
    # puts the duration back, which leaves only the pitch moved.
    return stretch(np, resample_linear(np, samples, ratio), 1.0 / ratio)
