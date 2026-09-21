"""The workflow decides what "green" means, and nothing here used to read it.

CI went red for a reason no test in this repository could see: the client
suite was handed a quoted glob, so on the Node version in the image the
pattern never resolved and the job failed before running a single test. The
mirror image of that bug is worse - a suite that matches nothing exits zero,
and "no tests ran" is reported as "all tests passed". Both live in the
workflow text, so that is where they are checked.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/ci.yml"
TEXT = WORKFLOW.read_text("utf-8")


def test_the_workflow_is_readable_and_has_jobs():
    """A guard over an empty file passes while checking nothing."""
    assert "jobs:" in TEXT
    assert len(re.findall(r"^  [a-z][\w-]*:$", TEXT, re.MULTILINE)) >= 4


def test_no_run_step_quotes_a_glob():
    """A quoted pattern reaches the program as text, not as a file list.

    The test runner only learned to expand globs itself in Node 21; whatever
    the runner is, the shell expanding it is the version-independent answer.
    """
    quoted = [
        line.strip()
        for line in TEXT.splitlines()
        if re.search(r"[\"'][^\"']*\*[^\"']*[\"']", line)
    ]
    assert quoted == []


def test_the_client_suite_refuses_to_pass_when_it_matched_nothing():
    """The failing direction is invisible: zero files is a zero exit code."""
    assert "shopt -s nullglob" in TEXT
    assert "refusing to report success" in TEXT


def test_every_supported_python_is_in_the_matrix():
    """The versions the package claims and the versions it is tested on must
    be the same list, or the claim is untested."""
    classifiers = (ROOT / "pyproject.toml").read_text("utf-8")
    claimed = set(
        re.findall(r"Programming Language :: Python :: (3\.\d+)", classifiers)
    )
    matrix = re.search(r"python: \[([^\]]+)\]", TEXT)
    assert matrix, "the test job has no python matrix"
    tested = set(re.findall(r"(\d+\.\d+)", matrix.group(1)))
    assert claimed
    assert claimed == tested, f"claimed {sorted(claimed)} but test {sorted(tested)}"


def test_the_suite_that_runs_is_the_suite_that_ships():
    """Installing the package the way a user would is the only way the import
    paths under test are the ones a user gets."""
    assert 'pip install -e ".[dev]"' in TEXT
    assert "python -m pytest" in TEXT
