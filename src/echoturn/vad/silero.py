"""Speech detection with a small local model, over ONNX Runtime.

Level thresholds cannot tell speech from any other loud sound, and they cannot
say how long somebody actually spoke - a knock on a desk and a three-second
sentence look similar to an energy meter and differ by a factor of a hundred in
truth. This measures the truth, and that number is what the turn logic gates on.

The model's input contract is unusually easy to get wrong in a way that does not
raise anything. It takes 512 samples at a time, and each of those calls also has
to carry the last 64 samples of the previous call, with a recurrent state that
accumulates across calls. Leave the 64 samples out and the same recording scores
around 0.09 instead of 0.89 - which looks exactly like a model that does not
work. Samples are fed as floats in [-1, 1], not as integers.

One block costs about 0.2 ms on one core, so the session is pinned to one thread:
more threads would spend their time contending over a job that is already short.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..config import model_dir
from .segments import mean_speech_prob, speech_ms

MODEL_FILE = "silero_vad.onnx"
SAMPLE_RATE = 16000
BLOCK = 512
CONTEXT = 64
STATE_SHAPE = (2, 1, 128)
THRESHOLD = 0.5
CHUNK_MS = BLOCK * 1000.0 / SAMPLE_RATE
# Long recordings are cut to their last minute, the way a buffer that holds
# speech is: what matters is the end of it, and the beginning is history.
MAX_AUDIO_MS = 60_000


class SileroVad:
    """A speech-length detector backed by a model file."""

    engine = "silero"

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        session=None,
    ) -> None:
        self.path = Path(path) if path else model_dir() / MODEL_FILE
        self.last_error = ""
        self.load_ms = 0.0
        self._session = session
        self._lock = threading.Lock()

    def ready(self) -> bool:
        """Whether the model file is there. Cheap on purpose - no session, no import."""
        return self._session is not None or self.path.exists()

    def load(self):
        """Build the session on first use, or return None and say why.

        Loading is what costs a second and a half; it happens once, on the first
        turn, rather than at import for a process that may never hear anything.
        """
        if self._session is not None:
            return self._session
        if not self.path.exists():
            self.last_error = f"no model file at {self.path}"
            return None
        with self._lock:
            if self._session is not None:
                return self._session
            try:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.inter_op_num_threads = 1
                options.intra_op_num_threads = 1
                options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )
                started = time.time()
                self._session = ort.InferenceSession(
                    str(self.path),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                self.load_ms = (time.time() - started) * 1000.0
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001 - a missing model is not a crash
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._session = None
            return self._session

    def warm(self) -> bool:
        """Pay the load once, off the path of a real turn."""
        return self.load() is not None

    def probabilities(self, samples) -> list[float] | None:
        """Speech probability per block, or None when there is no model to ask."""
        session = self.load()
        if session is None:
            return None
        np = _numpy()
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        cap = SAMPLE_RATE * MAX_AUDIO_MS // 1000
        if x.size > cap:
            x = x[-cap:]
        blocks = max(1, -(-x.size // BLOCK))
        state = np.zeros(STATE_SHAPE, dtype=np.float32)
        context = np.zeros(CONTEXT, dtype=np.float32)
        probs: list[float] = []
        try:
            for index in range(blocks):
                part = x[index * BLOCK:(index + 1) * BLOCK]
                if part.size < BLOCK:
                    part = np.pad(part, (0, BLOCK - part.size))
                fed = np.concatenate([context, part]).reshape(1, -1).astype(np.float32)
                out = session.run(
                    None,
                    {
                        "input": fed,
                        "state": state,
                        "sr": np.array(SAMPLE_RATE, dtype=np.int64),
                    },
                )
                probs.append(float(np.asarray(out[0]).reshape(-1)[0]))
                state = np.asarray(out[1])
                context = fed[0, -CONTEXT:]
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail a turn
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        return probs

    def report(self, samples) -> dict | None:
        """Speech length and confidence, or None when the model could not answer."""
        probs = self.probabilities(samples)
        if probs is None:
            return None
        return {
            "engine": self.engine,
            "speech_ms": speech_ms(probs, block_ms=CHUNK_MS, threshold=THRESHOLD),
            "prob": mean_speech_prob(probs, threshold=THRESHOLD),
        }


def _numpy():
    from ..audio._dsp import numpy

    return numpy()
