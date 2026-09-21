"""The optional model files, and the one command that installs them.

Two ONNX models make turn detection work: one measures how much real speech was
there, one decides whether the speaker has finished. Both are tens of megabytes,
so neither is in the wheel nor in the repository. A clone that never installs
them still runs - it just ends turns on the silence deadline alone, which is the
worse but perfectly usable behaviour.

Installing them is an explicit command rather than part of start-up. A download
on the start-up path turns "this machine has no network" into "the service does
not come up", and a conversation that would have worked anyway never happens.

Every file is written beside its destination as ``<name>.part`` and only takes its
real name once the byte count matches. A connection dropped halfway therefore
leaves no half-model behind, and cannot damage one that already worked. The size
is not a formality: a truncated ONNX file loads without complaining and answers
nonsense, so "the file is there" is not evidence of a working model.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

from .config import model_dir

__all__ = [
    "MODELS",
    "Model",
    "by_name",
    "download",
    "fetch_all",
    "installed",
    "main",
    "path_of",
    "smoke",
    "status",
]

USER_AGENT = "echoturn-fetch-models/1.0"
READ_CHUNK = 256 * 1024
# One stalled socket read fails the download instead of hanging the command for
# ever. It is not a limit on the transfer: a slow link simply takes more reads.
TIMEOUT_SEC = 120


class Model(NamedTuple):
    """One file: what it is called, where it comes from, how big it must be."""

    name: str
    url: str
    size: int


# The byte counts are what the sources serve today, and they are what makes
# "complete" a checkable claim rather than a hope. If a source ever publishes a
# different build, the download fails loudly and this table is the thing to
# update - silently accepting the new file would swap the model under the
# thresholds that were measured against the old one.
MODELS: tuple[Model, ...] = (
    Model(
        "silero_vad.onnx",
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/"
        "src/silero_vad/data/silero_vad.onnx",
        2327524,
    ),
    Model(
        "smart-turn-v3.2-cpu.onnx",
        "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/"
        "smart-turn-v3.2-cpu.onnx",
        8679182,
    ),
)


def by_name(name: str) -> Model:
    """The entry for one model. An unknown name raises, as a typo should."""
    for model in MODELS:
        if model.name == name:
            return model
    raise KeyError(name)


def path_of(model: Model | str) -> Path:
    """Where a model lives. Read from the settings now, not copied at import."""
    return model_dir() / (model.name if isinstance(model, Model) else str(model))


def installed(model: Model | str) -> bool:
    """Whether the file is present *and* the size it is supposed to be."""
    model = by_name(model) if isinstance(model, str) else model
    target = path_of(model)
    return target.exists() and target.stat().st_size == model.size


def status() -> list[dict]:
    """What is installed, what is missing, and where it is looked for."""
    out = []
    for model in MODELS:
        target = path_of(model)
        # ``None`` rather than 0 for "not there": a zero-byte file and an absent
        # one are different problems and should not print the same.
        have = target.stat().st_size if target.exists() else None
        out.append(
            {
                "name": model.name,
                "path": str(target),
                "expected": model.size,
                "actual": have,
                "ok": have == model.size,
            }
        )
    return out


def download(model: Model, *, force: bool = False) -> bool:
    """Fetch one model. Returns whether it is installed when this returns."""
    target = path_of(model)
    if not force and installed(model):
        print(f"[{model.name}] already installed ({model.size} bytes) at {target}")
        return True
    if target.exists() and not force:
        print(f"[{model.name}] present but {target.stat().st_size} bytes, expected "
              f"{model.size} - downloading again")
    part = target.with_name(model.name + ".part")
    complete = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{model.name}] downloading {model.url}")
        request = urllib.request.Request(model.url, headers={"User-Agent": USER_AGENT})
        with (
            urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response,
            open(part, "wb") as handle,
        ):
            shutil.copyfileobj(response, handle, READ_CHUNK)
        actual = part.stat().st_size
        if actual != model.size:
            print(f"[{model.name}] FAILED: {actual} bytes, expected {model.size}. "
                  "The source published a different file, or the transfer was cut "
                  "short. Run it again; if it keeps happening do not use this file.")
            return False
        os.replace(part, target)
        complete = True
        print(f"[{model.name}] installed at {target} ({actual} bytes)")
        return True
    except Exception as exc:  # noqa: BLE001 - every network failure gets one answer
        print(f"[{model.name}] FAILED: {type(exc).__name__}: {exc}")
        return False
    finally:
        if not complete and part.exists():
            # Never leave a half file in the model directory: the next run has to
            # start from nothing rather than from a file that looks installed.
            part.unlink()


def fetch_all(*, force: bool = False) -> list[str]:
    """Fetch whatever is missing. Returns the names that are still missing."""
    return [model.name for model in MODELS if not download(model, force=force)]


def smoke() -> int:
    """Load each installed model and run it once.

    It answers "do these files work on this machine", not "are they accurate":
    the input is a second of silence, so the numbers below are not a measurement
    of anything except that the graph runs.
    """
    failed = 0
    for model in MODELS:
        if not installed(model):
            print(f"[{model.name}] not installed - run this command without --check")
            failed += 1
            continue
        try:
            answered = _run_once(model)
        except Exception as exc:  # noqa: BLE001 - the point is to report it
            print(f"[{model.name}] FAILED: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        print(f"[{model.name}] loaded and ran: {answered}")
    return 1 if failed else 0


def _run_once(model: Model):
    """One inference on a second of silence, with whichever judge owns the file."""
    quiet = [0.0] * 16000
    if model.name.endswith("silero_vad.onnx"):
        from .vad.silero import SileroVad

        return SileroVad().report(quiet)
    from .endpoint.turn import SmartTurn

    return SmartTurn().judge(quiet)


def main(argv=None) -> int:
    """The command line: install what is missing, or check what is there."""
    parser = argparse.ArgumentParser(
        prog="echoturn-fetch-models",
        description="Install the optional speech and endpointing models.",
    )
    parser.add_argument(
        "--force", action="store_true", help="download again even if installed"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not download; load what is installed and run it once",
    )
    args = parser.parse_args(argv)

    print(f"model directory: {model_dir()}")
    if args.check:
        return smoke()
    missing = fetch_all(force=args.force)
    print()
    if missing:
        print(f"still missing: {', '.join(missing)} - fix the errors above and "
              "run this again")
        return 1
    print("all models installed; verify them with --check")
    return 0


if __name__ == "__main__":  # pragma: no cover - the console script is the entry
    sys.exit(main())
