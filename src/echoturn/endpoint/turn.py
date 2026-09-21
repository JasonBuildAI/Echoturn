"""Deciding whether the speaker has finished, with a small local model.

Silence answers "is there sound", which is not the question. A pause in the
middle of a sentence is normal, and one measured Chinese pause was 520 ms long -
longer than the silence threshold a call would use to end a turn. Gating on
silence therefore means talking over people, always, in the middle of their
sentences.

This model answers the actual question: given the audio so far, was that the end
of a turn. It is fed eight seconds of log-mel features, right-aligned, and
answers with a probability.

Right-aligned is not a detail. The window always holds the *most recent* eight
seconds, padded at the front when there is less than that: the end of the audio
has to land at the end of the window. Padding at the other end hands the model a
silence and gets a different answer for the same words.

The decision is advisory in this package. A model that says "not finished" and is
wrong leaves a speaker waiting for a reply that never comes, which reads as
broken, so the caller is expected to keep a silence-based deadline as a backstop.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..config import model_dir
from .mel import SAMPLE_RATE, log_mel

MODEL_FILE = "smart-turn-v3.2-cpu.onnx"
WINDOW_SAMPLES = SAMPLE_RATE * 8
# The model has around eight million parameters, so four threads is where the
# returns stop: the rest spend their time waiting for each other.
THREADS = 4
COMPLETE_THRESHOLD = 0.5


class SmartTurn:
    """A turn-ending classifier backed by a model file."""

    engine = "smart-turn"

    def __init__(self, path: str | Path | None = None, *, session=None) -> None:
        self.path = Path(path) if path else model_dir() / MODEL_FILE
        self.last_error = ""
        self.load_ms = 0.0
        self._session = session
        self._lock = threading.Lock()

    def ready(self) -> bool:
        """Whether the model is available. Cheap: no session is built to answer it."""
        return self._session is not None or self.path.exists()

    def load(self):
        """Build the session on first use, or return None and record why."""
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
                options.intra_op_num_threads = THREADS
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

    def window(self, samples):
        """The last eight seconds, padded at the front when there are fewer."""
        np = _numpy()
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size > WINDOW_SAMPLES:
            return x[-WINDOW_SAMPLES:]
        if x.size < WINDOW_SAMPLES:
            return np.pad(x, (WINDOW_SAMPLES - x.size, 0))
        return x

    def judge(self, samples) -> dict | None:
        """``{"complete": bool, "prob": float}``, or None when there is no model."""
        session = self.load()
        if session is None:
            return None
        try:
            features = log_mel(self.window(samples))[None, ...]
            out = session.run(None, {"input_features": features})
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail a turn
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        prob = float(_numpy().asarray(out[0]).reshape(-1)[0])
        return {"complete": prob > COMPLETE_THRESHOLD, "prob": prob}


def _numpy():
    from ..audio._dsp import numpy

    return numpy()
