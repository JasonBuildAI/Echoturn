"""The warning is allowed not to fail; it is not allowed to be blind.

``scripts/check_language.py`` exits 0 with a list of hits, which is the right
setting for a rule that cannot tell Chinese test data from Chinese prose. The
risk in that trade is a scanner that reports nothing because it looks at
nothing, so what is checked here is that it sees text, that it reports it, that
it can be made to fail, and that the one allowed file is still skipped.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _guard():
    spec = importlib.util.spec_from_file_location(
        "check_language", ROOT / "scripts" / "check_language.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD = _guard()


def test_the_scan_counts_characters_and_names_the_lines():
    count, lines = GUARD.scan_text("clean\n\u4e00\u4e8c\u4e09\nclean\n\u56db\n")
    assert count == 4
    assert lines == [2, 4]


def test_clean_text_reports_nothing():
    assert GUARD.scan_text("all of this is english\n") == (0, [])


def test_a_cjk_file_is_reported(tmp_path):
    canary = tmp_path / "canary.py"
    canary.write_text("# \u4e00\u53e5\u8bdd\n", "utf-8")
    hits = GUARD.scan_files([str(canary)])
    assert len(hits) == 1
    assert hits[0][0] == str(canary)


def test_the_chinese_readme_is_the_one_exception(tmp_path):
    """By name, and only by name - see the note in is_allowed."""
    allowed = tmp_path / sorted(GUARD.ALLOWED)[0]
    allowed.write_text("# \u4e2d\u6587\n", "utf-8")
    assert GUARD.scan_files([str(allowed)]) == []
    assert GUARD.is_allowed(allowed)
    assert not GUARD.is_allowed(tmp_path / "README.md")


def test_the_self_test_passes():
    assert GUARD.self_test() == 0


def test_the_default_exit_code_warns_rather_than_fails(tmp_path, capsys):
    """A hit must not turn the build red; that is the whole point of the rule."""
    canary = tmp_path / "canary.py"
    canary.write_text("# \u4e00\u53e5\u8bdd\n", "utf-8")
    original = GUARD.walk_files
    GUARD.walk_files = lambda root: [str(canary)]  # type: ignore[assignment]
    try:
        assert GUARD.main(["--root", str(tmp_path), "--no-git"]) == 0
        assert "warning" in capsys.readouterr().out
        assert GUARD.main(["--root", str(tmp_path), "--no-git", "--fail"]) == 1
    finally:
        GUARD.walk_files = original  # type: ignore[assignment]


def test_a_repository_with_nothing_to_report_says_so(tmp_path, capsys):
    clean = tmp_path / "clean.py"
    clean.write_text("# english\n", "utf-8")
    original = GUARD.walk_files
    GUARD.walk_files = lambda root: [str(clean)]  # type: ignore[assignment]
    try:
        assert GUARD.main(["--root", str(tmp_path), "--no-git"]) == 0
        assert "clean" in capsys.readouterr().out
    finally:
        GUARD.walk_files = original  # type: ignore[assignment]


def test_the_tracked_tree_still_has_cjk_in_it():
    """The warning is worth having only while there is something to warn about.

    If this ever fails, the guard has become vacuous - either the test data
    moved to English or the scanner stopped reading, and the second is the one
    that would go unnoticed.
    """
    hits = GUARD.scan_files(GUARD.git_tracked_files(ROOT))
    assert hits, "nothing was reported anywhere, which would make this a no-op"
