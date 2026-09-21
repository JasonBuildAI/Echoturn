"""Where a turn's milliseconds go, measured rather than argued about.

    python bench/latency.py                        # the shipped policy
    python bench/latency.py --compare              # ... beside one that waits
    python bench/latency.py --token-ms 25 --compare
    python bench/latency.py --json

It needs the package importable (``pip install -e .``) and nothing else: the
providers are the offline ones, so no socket is opened and the result is the
same with the network unplugged.

That is also the limit of what it can tell you, and it is worth being blunt
about it. A model that takes 800 ms to produce its first token adds 800 ms to
every number below, and nothing measured here can know that. What this measures
is the part the pipeline owns - what happens between the model's first token and
the first sound - and what the first-chunk threshold is worth. Those are the two
things a host can change, and neither is visible from the outside.

``--token-ms`` slows the model down to a given pace per streamed piece, because
that is the whole reason the early flush exists: with an instant model, waiting
for the reply costs nothing and the comparison says so honestly. The pace is
printed with every row, since a latency number without it is not a measurement
of anything.

One more artefact, because it is easy to misread: the voice here is the offline
beep, synthesised in Python. Its cost is real CPU work and it moves with the
length of the text, but it is not what a hosted voice costs - it is a stand-in
that is fast in the same direction as the real thing and slow by a different
amount. Compare rows against each other; do not quote a row as "TTS latency".
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import replace

from echoturn.pipeline import TurnDeps, TurnInput, policy_from_dials, run_turn
from echoturn.providers.mock import MockLLM, MockTTS
from echoturn.text.chunking import ChunkPolicy

# Several sentences, so the shipped policy has something to split and the
# first-chunk threshold has something to be early about. The question marks are
# load-bearing: the sentence boundary the pipeline recognises is the one the
# model is written to end a sentence with, and a full stop is not in that set.
PROMPT = (
    "What is the weather on the coast doing this morning? "
    "How is the traffic on the road into town? "
    "And what is worth doing before the rain arrives?"
)

RUNS = 20

# The three numbers ``done`` reports, in the order they happen.
METRICS = ("first_token_ms", "first_audio_ms", "total_ms")


class PacedLLM:
    """The offline model, slowed to a given pace per streamed piece.

    A real model answers over hundreds of milliseconds and that is the reason
    chunking exists; a mock that answers instantly hides the whole effect. This
    is the same mock with a sleep in front of each piece - nothing else about
    the turn changes.
    """

    def __init__(self, *, piece_ms: float) -> None:
        self.piece_ms = float(piece_ms)
        self._inner = MockLLM()

    def stream(self, messages):
        for piece in self._inner.stream(messages):
            if self.piece_ms > 0:
                time.sleep(self.piece_ms / 1000.0)
            yield piece


def waits_for_the_whole_reply(policy: ChunkPolicy) -> ChunkPolicy:
    """The same policy with early flushing turned off.

    Thresholds nobody reaches and no terminator, so nothing is submitted until
    the turn ends. It is not a policy anybody should ship; it is here to put a
    number on what the early flush buys.
    """
    unreachable = 10**9
    return replace(
        policy,
        chunk_chars=unreachable,
        chunk_min=unreachable,
        first_chars=unreachable,
        first_min=unreachable,
        first_call_chars=unreachable,
        first_call_min=unreachable,
        terminators="",
    )


def one_turn(policy: ChunkPolicy, *, piece_ms: float = 0.0) -> dict:
    """One turn, start to ``done``, returning what it measured.

    Every run gets its own providers: a shared mock would let the first turn's
    leftovers show up in the second turn's numbers.
    """
    deps = TurnDeps(
        llm=PacedLLM(piece_ms=piece_ms), tts=MockTTS(), chunk_policy=policy
    )
    turn = TurnInput(text=PROMPT, input_kind="text", voice_call=True)
    for event in run_turn(turn, deps):
        if event["type"] == "done":
            return dict(event["timings"])
    raise RuntimeError("the turn ended without a done event")


def summarise(rows: list[dict]) -> dict:
    """min, median and p95 per metric, plus the chunk count.

    A mean over twenty turns of a warm process is a number nobody acts on. The
    useful question is whether the slow run was slow because of the policy or
    because the machine hiccupped, and min against p95 answers that; the median
    is what gets quoted downstream.
    """
    out: dict = {"runs": len(rows), "chunks": rows[-1].get("chunks") if rows else None}
    for name in METRICS:
        values = sorted(
            float(row[name]) for row in rows if row.get(name) is not None
        )
        if not values:
            out[name] = None
            continue
        out[name] = {
            "min": round(values[0], 1),
            "median": round(statistics.median(values), 1),
            "p95": round(values[min(len(values) - 1, int(len(values) * 0.95))], 1),
        }
    return out


def measure(policy: ChunkPolicy, *, runs: int = RUNS, piece_ms: float = 0.0) -> dict:
    """Run ``runs`` turns under one policy and summarise them."""
    return summarise([one_turn(policy, piece_ms=piece_ms) for _ in range(runs)])


def policies() -> list[tuple[str, ChunkPolicy]]:
    """What to compare. The shipped one is always in the report."""
    shipped = policy_from_dials()
    return [
        ("shipped", shipped),
        ("waits for the whole reply", waits_for_the_whole_reply(shipped)),
    ]


def render(report: dict[str, dict]) -> str:
    """The report as a table somebody can read in a terminal."""
    width = max([len(name) for name in report] + [26]) + 2
    header = f"{'policy':<{width}}{'chunks':>7}" + "".join(
        f"{name:>17}" for name in ("first token", "first audio", "total")
    )
    lines = [header, "-" * len(header)]
    for name, summary in report.items():
        cells = []
        for metric in METRICS:
            value = summary.get(metric)
            if not value:
                cells.append(f"{'-':>17}")
                continue
            cells.append(f"{value['median']:>9.1f} ({value['p95']:.0f})")
        lines.append(
            f"{name:<{width}}{str(summary.get('chunks')):>7}" + "".join(cells)
        )
    runs = next(iter(report.values())).get("runs") if report else 0
    lines.append("")
    lines.append(f"median (p95) milliseconds over {runs} turns each.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python bench/latency.py",
        description="Measure the pipeline's own share of a turn's latency.",
    )
    parser.add_argument("--runs", type=int, default=RUNS, help="turns per policy")
    parser.add_argument(
        "--token-ms",
        type=float,
        default=0.0,
        help="milliseconds of model pace in front of each streamed piece",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="also measure a policy that waits for the whole reply",
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.token_ms < 0:
        parser.error("--token-ms cannot be negative")

    chosen = policies()
    if not args.compare:
        chosen = chosen[:1]
    pace = f" @ {args.token_ms:g} ms/token" if args.token_ms else " @ instant model"
    report = {
        name + pace: measure(policy, runs=args.runs, piece_ms=args.token_ms)
        for name, policy in chosen
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover - a script, not an entry point
    raise SystemExit(main())
