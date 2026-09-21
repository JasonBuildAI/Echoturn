"""The publish guard has to be provably able to fail, not just present."""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_privacy.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_privacy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


def test_self_test_detects_every_term_and_ignores_clean_text(monkeypatch):
    proc = _run("--self-test")
    assert proc.returncode == 0, proc.stderr
    assert "self-test ok" in proc.stdout


def test_repository_is_clean():
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert "clean" in proc.stdout


def test_canary_file_is_flagged(tmp_path):
    module = _load_guard()
    leak = tmp_path / "leak.md"
    term = module.forbidden_terms()[0]
    leak.write_text(f"harmless prefix {term} harmless suffix\n", encoding="utf-8")
    proc = _run("--root", str(tmp_path), "--no-git")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "term #1" in proc.stderr


def test_report_does_not_print_the_term_itself(tmp_path):
    """A public CI log must not become the leak it was warning about."""
    module = _load_guard()
    term = module.forbidden_terms()[0]
    (tmp_path / "leak.txt").write_text(term + "\n", encoding="utf-8")
    proc = _run("--root", str(tmp_path), "--no-git")
    assert proc.returncode == 1
    assert term not in proc.stderr + proc.stdout


def test_terms_are_not_stored_in_plaintext():
    """The guard scans itself, so the list must not be readable in its source."""
    module = _load_guard()
    source = SCRIPT.read_text(encoding="utf-8")
    for term in module.forbidden_terms():
        assert term not in source


def test_every_term_is_specific_enough():
    """Short entries would flag unrelated words; single names are 3 characters."""
    module = _load_guard()
    terms = module.forbidden_terms()
    assert len(terms) >= 5
    for term in terms:
        assert len(term) >= 3, term
        assert len(term) >= 5 or not term.isascii(), term
