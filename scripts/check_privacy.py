#!/usr/bin/env python3
"""Publish guard: fail if an identifier that must stay private can be committed.

The terms are stored base64-encoded on purpose. This file is scanned by this
very script, so a readable list would make the guard fail on itself - and the
"fix" somebody would then reach for is an ignore rule, which is how a guard
quietly stops working. The encoded form keeps the list out of the repository
while still letting the scanner scan itself.

Usage:

    python scripts/check_privacy.py                  # tracked files and commits
    python scripts/check_privacy.py --no-git         # walk the tree instead
    python scripts/check_privacy.py --self-test      # prove the guard can fail
    python scripts/check_privacy.py --show           # reveal it (local only)

Exit codes: 0 clean, 1 hit, 2 the guard could not run at all.
"""
from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

# A report is (where it was found, line number, which term) - never the term.
Hit = tuple[str, int, int]

# Decoded at runtime by forbidden_terms(); see the module docstring.
FORBIDDEN_B64 = (
    "bnVtYmVyaHVtYW4=",
    "bGlueWl4aW4=",
    "5p6X5LiA5q2G",
    "6buE5rGf5Y2X",
    "eGlhb21pbWltbw==",
    "WElBT01JX1RPS0VOX1BMQU5fQVBJX0tFWQ==",
    "TWlNb1RUUw==",
    "TWlNb0FTUg==",
    "bWltby12Mi41",
)

SKIP_DIRS = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def forbidden_terms() -> list[str]:
    """The decoded list. Only positions are ever printed; see Hit."""
    return [base64.b64decode(item).decode("utf-8") for item in FORBIDDEN_B64]


def _label(index: int) -> str:
    """Terms are referred to by position so a report cannot leak one into logs."""
    return f"term #{index}"


def scan_text(text: str, terms: Sequence[str], where: str) -> list[Hit]:
    """Find every line that contains a term, for every term."""
    hits: list[Hit] = []
    lowered = text.lower()
    for index, term in enumerate(terms, 1):
        needle = term.lower()
        if needle not in lowered:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                hits.append((where, lineno, index))
    return hits


def scan_files(paths: Sequence[str], terms: Sequence[str]) -> list[Hit]:
    hits: list[Hit] = []
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            continue
        hits.extend(scan_text(raw.decode("utf-8", "replace"), terms, str(path)))
    return hits


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


def git_commit_messages(root: Path) -> str:
    """Commit messages are published too: a leak there is just as permanent."""
    proc = subprocess.run(
        ["git", "-C", str(root), "log", "--format=%B"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else ""


def self_test(terms: Sequence[str]) -> int:
    """Prove the guard fails: one canary per term, plus a clean file it ignores."""
    with tempfile.TemporaryDirectory(prefix="echoturn-privacy-") as tmp:
        root = Path(tmp)
        for index, term in enumerate(terms, 1):
            canary = root / f"canary_{index}.txt"
            canary.write_text(f"harmless prefix {term} harmless suffix\n", "utf-8")
            if not scan_files([str(canary)], terms):
                print(
                    f"self-test FAILED: {_label(index)} not detected",
                    file=sys.stderr,
                )
                return 2
        clean = root / "clean.txt"
        clean.write_text("a file with nothing private in it\n", encoding="utf-8")
        if scan_files([str(clean)], terms):
            print("self-test FAILED: clean text was flagged", file=sys.stderr)
            return 2
        # The git path reads a subprocess, and text=True without an explicit
        # encoding decodes with the locale codec - which on a non-UTF-8 machine
        # (GBK here) turned a commit message into a UnicodeDecodeError that the
        # reader thread swallowed, leaving stdout as None and crashing the
        # guard instead of reporting anything. A commit message is exactly
        # where a leak would be published, so this path needs a canary too: one
        # non-ASCII term, in a message that is not ASCII either.
        term = next((item for item in terms if not item.isascii()), terms[0])
        repo = root / "repo"
        repo.mkdir()
        for command in (
            ["init", "-q"],
            [
                "-c",
                "user.name=guard",
                "-c",
                "user.email=guard@example.invalid",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                f"handoff 这一轮说完了 {term}",
            ],
        ):
            subprocess.run(
                ["git", "-C", str(repo), *command],
                capture_output=True,
                check=True,
            )
        if not scan_text(git_commit_messages(repo), terms, "git log"):
            print(
                "self-test FAILED: a term in a non-ASCII commit message "
                "was not detected",
                file=sys.stderr,
            )
            return 2
    print(
        f"privacy guard: self-test ok ({len(terms)} terms, every one detected; "
        "clean text passes; a non-ASCII commit message is read and scanned)"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="publish guard")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument(
        "--no-git", action="store_true", help="walk the tree instead of tracked files"
    )
    parser.add_argument("--self-test", action="store_true", help="prove it can fail")
    parser.add_argument("--show", action="store_true", help="reveal what matched")
    args = parser.parse_args(argv)

    terms = forbidden_terms()
    if not terms:
        print("privacy guard: empty term list, refusing to report success",
              file=sys.stderr)
        return 2
    if args.self_test:
        return self_test(terms)

    root = Path(args.root).resolve()
    hits: list[Hit] = []
    if args.no_git:
        hits.extend(scan_files(walk_files(root), terms))
    else:
        try:
            hits.extend(scan_files(git_tracked_files(root), terms))
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(
                f"privacy guard: cannot list tracked files ({exc}); use --no-git",
                file=sys.stderr,
            )
            return 2
        hits.extend(scan_text(git_commit_messages(root), terms, "git log"))

    if not hits:
        print(f"privacy guard: clean ({len(terms)} terms checked)")
        return 0

    print(f"privacy guard: {len(hits)} forbidden identifier(s) found", file=sys.stderr)
    for where, lineno, index in hits:
        print(f"  {where}:{lineno}: {_label(index)}", file=sys.stderr)
    if args.show:
        for _where, _lineno, index in hits:
            print(f"  {_label(index)} = {terms[index - 1]!r}", file=sys.stderr)
    print(
        "Remove these before publishing. Run with --show to see the term locally.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
