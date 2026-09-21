#!/usr/bin/env python3
"""Warn when a file that is meant to be English carries CJK text.

The repository is written in English: comments, docstrings, documentation and
commit messages. Files named ``*.zh-CN.md`` are the deliberate exception, because
they mirror the English ones for people who would rather read Chinese. The
English file of a pair is the authority; the Chinese one says so at the top.

This is a warning and not a gate, and that is not laziness - it is the only
honest setting. The pipeline is language-agnostic, so its tests carry Chinese
punctuation and Chinese words as *data* (a full stop, a filler syllable), and
those are supposed to be there. A rule that cannot tell data from prose would
have to be silenced, and a silenced check is worse than no check. So the default
exit code is 0 with the hits listed, and ``--fail`` turns it into an error for
anybody who wants one in a pre-commit hook.

Usage:

    python scripts/check_language.py             # warn (always exits 0)
    python scripts/check_language.py --fail      # exit 1 on a hit
    python scripts/check_language.py --no-git    # walk the tree instead
    python scripts/check_language.py --self-test # prove it can report

What is printed is where and how much, never the text: a terminal that cannot
render the characters is not a useful place to find out there are some.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

# Han, Hiragana, Katakana and the halfwidth forms. Deliberately not the CJK
# punctuation block on its own: "、" and "。" in a test are data.
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# The one naming convention allowed to be Chinese, and the reason it is allowed.
ALLOWED_SUFFIX = ".zh-CN.md"

SKIP_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def scan_text(text: str) -> tuple[int, list[int]]:
    """How many CJK characters, and which lines they are on."""
    count = 0
    lines: list[int] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        found = len(CJK.findall(line))
        if found:
            count += found
            lines.append(lineno)
    return count, lines


def is_allowed(path: str | Path) -> bool:
    """One exception, by suffix, wherever the file is.

    By suffixes and not by path: an allowed file is allowed wherever it lives, and
    a comparison against a path built from the repository root would also exempt
    every unrelated file that happens to sit at the root - the self-test found
    exactly that, by putting its canary there.
    """
    return Path(path).name.endswith(ALLOWED_SUFFIX)


def walk_files(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        found.append(str(path))
    return found


def git_tracked_files(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [str(root / line) for line in proc.stdout.splitlines() if line.strip()]


def scan_files(paths: Sequence[str]) -> list[tuple[str, int, list[int]]]:
    """(file, how many characters, which lines) for every file that has any."""
    hits: list[tuple[str, int, list[int]]] = []
    for path in paths:
        if is_allowed(path):
            continue
        try:
            raw = Path(path).read_bytes()
        except OSError:
            continue
        count, lines = scan_text(raw.decode("utf-8", "replace"))
        if count:
            hits.append((str(path), count, lines))
    return hits


def self_test() -> int:
    """Prove the scan reports, and that the one allowed file is skipped."""
    with tempfile.TemporaryDirectory(prefix="echoturn-language-") as tmp:
        root = Path(tmp)
        canary = root / "canary.py"
        canary.write_text("# \u8fd9\u662f\u4e00\u53e5\u8bdd\n", "utf-8")
        count, lines = scan_text(canary.read_text("utf-8"))
        if count == 0:
            print("self-test FAILED: CJK text was not seen", file=sys.stderr)
            return 2
        if scan_files([str(canary)]) == []:
            print("self-test FAILED: the scan did not report", file=sys.stderr)
            return 2
        allowed = root / ("anything" + ALLOWED_SUFFIX)
        allowed.write_text("# \u4e2d\u6587\n", "utf-8")
        if scan_files([str(allowed)]):
            print("self-test FAILED: the allowed file was reported", file=sys.stderr)
            return 2
        # A file that merely mentions the suffix is not exempt.
        nearly = root / "NOT-zh-CN.md"
        nearly.write_text("# \u4e2d\u6587\n", "utf-8")
        if not scan_files([str(nearly)]):
            print("self-test FAILED: a near miss was exempted", file=sys.stderr)
            return 2
    print(
        f"language check: self-test ok ({len(lines)} line(s) seen, "
        "allowed file skipped)"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="English-only warning")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument(
        "--no-git", action="store_true", help="walk the tree instead of tracked files"
    )
    parser.add_argument("--self-test", action="store_true", help="prove it reports")
    parser.add_argument(
        "--fail", action="store_true", help="exit 1 on a hit instead of warning"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    root = Path(args.root).resolve()
    if args.no_git:
        paths = walk_files(root)
    else:
        try:
            paths = git_tracked_files(root)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"language check: cannot list tracked files ({exc}); use --no-git",
                  file=sys.stderr)
            return 2

    hits = scan_files(paths)
    if not hits:
        print(f"language check: clean (no CJK outside *{ALLOWED_SUFFIX})")
        return 0

    print(
        f"language check: {len(hits)} file(s) contain CJK text. This is a warning:"
    )
    for path, count, lines in hits:
        shown = ", ".join(str(n) for n in lines[:8])
        more = f", +{len(lines) - 8} more" if len(lines) > 8 else ""
        print(f"  {path}: {count} character(s) on line(s) {shown}{more}")
    print(
        "Comments, docstrings and docs are meant to be English; test data in "
        "other scripts is not, and is why this does not fail the build."
    )
    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
