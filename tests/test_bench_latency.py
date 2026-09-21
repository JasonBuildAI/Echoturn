"""The benchmark is published as a number, so the way it is taken is checked.

A measurement script that quietly measures the wrong thing is worse than no
script: the number outlives the doubt. What is checked here is the part that
would change the answer without changing anything a reader can see - that the
comparison really does take the early flush away, that the summary is the
summary it says it is, and that a run costs a handful of turns and no network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bench():
    """Load the script by path: ``bench`` is a directory, not a package."""
    spec = importlib.util.spec_from_file_location(
        "bench_latency", ROOT / "bench" / "latency.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BENCH = _bench()


def test_the_waiting_policy_really_waits():
    """If it did not, every row of the comparison would be the same policy."""
    shipped = BENCH.policy_from_dials()
    waiting = BENCH.waits_for_the_whole_reply(shipped)
    text = "One sentence here? And a second sentence that is long enough."
    assert shipped.should_flush(text, first=True, call=True)
    assert not waiting.should_flush(text, first=True, call=True)
    assert not waiting.should_flush(text * 20, first=False, call=False)


def test_the_waiting_policy_leaves_the_shipped_one_alone():
    """``replace`` on a frozen dataclass, so the caller's policy is untouched."""
    shipped = BENCH.policy_from_dials()
    before = shipped
    BENCH.waits_for_the_whole_reply(shipped)
    assert shipped == before
    assert shipped.first_chars != 10**9


def test_the_measurement_is_a_turn_and_its_chunk_count():
    """A run has to produce a real turn, not just numbers of the right shape."""
    row = BENCH.one_turn(BENCH.policy_from_dials())
    assert row["chunks"] >= 1
    for metric in BENCH.METRICS:
        assert isinstance(row[metric], int)
        assert row[metric] >= 0


def test_the_prompt_is_long_enough_to_be_split():
    """A prompt of one sentence would make the two policies indistinguishable."""
    shipped = BENCH.policy_from_dials()
    text = BENCH.PROMPT
    assert len(text) > shipped.chunk_chars
    assert any(ch in text for ch in shipped.terminators)


def test_the_summary_reports_a_distribution_not_an_average():
    rows = [{"first_token_ms": n, "first_audio_ms": n * 2, "total_ms": n * 3,
             "chunks": 2} for n in (10, 20, 30, 40)]
    summary = BENCH.summarise(rows)
    assert summary["runs"] == 4
    assert summary["chunks"] == 2
    assert summary["first_token_ms"] == {"min": 10.0, "median": 25.0, "p95": 40.0}
    assert summary["total_ms"]["min"] == 30.0


def test_a_missing_metric_is_not_a_zero():
    """A turn with no audio has no first-audio time; zero would read as instant."""
    summary = BENCH.summarise([{"first_token_ms": 5, "total_ms": 5}])
    assert summary["first_audio_ms"] is None
    assert summary["first_token_ms"]["min"] == 5.0


def test_nothing_to_summarise_does_not_raise():
    summary = BENCH.summarise([])
    assert summary["runs"] == 0
    assert summary["first_token_ms"] is None


def test_the_json_report_is_json(capsys):
    assert BENCH.main(["--runs", "1", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report) == 1
    name, summary = next(iter(report.items()))
    assert name.startswith("shipped")
    assert summary["runs"] == 1


def test_comparing_adds_a_second_row(capsys):
    assert BENCH.main(["--runs", "1", "--compare"]) == 0
    printed = capsys.readouterr().out
    assert "shipped" in printed
    assert "waits for the whole reply" in printed


def test_a_pace_is_named_in_the_row(capsys):
    """A latency number without the model pace it was taken at says nothing."""
    assert BENCH.main(["--runs", "1", "--token-ms", "25"]) == 0
    assert "25 ms/token" in capsys.readouterr().out
    assert BENCH.main(["--runs", "1"]) == 0
    assert "instant model" in capsys.readouterr().out


def test_impossible_arguments_are_refused():
    for bad in (["--runs", "0"], ["--token-ms", "-1"]):
        try:
            BENCH.main(bad)
        except SystemExit as exc:
            assert exc.code != 0
        else:  # pragma: no cover - the guard, not the failure path
            raise AssertionError(f"{bad} was accepted")
