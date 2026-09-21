"""Audio plumbing: containers, decoding, resampling and voice consistency."""

from .decode import decode_16k_mono, to_float32
from .encoding import from_base64, to_base64
from .pitch import clamp_target, lock_pitch, measure_f0, semitone_distance
from .resample import resample_pcm16
from .stretch import clamp_rate, time_stretch
from .wav import WavInfo, pcm16_to_wav, read_wav, wav_seconds

__all__ = [
    "WavInfo",
    "clamp_rate",
    "clamp_target",
    "decode_16k_mono",
    "from_base64",
    "lock_pitch",
    "measure_f0",
    "pcm16_to_wav",
    "read_wav",
    "resample_pcm16",
    "semitone_distance",
    "time_stretch",
    "to_base64",
    "to_float32",
    "wav_seconds",
]
