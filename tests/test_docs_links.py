"""A link to a file that is not there is a promise nobody kept.

Every document in this repository points at other documents, and a link is the
one kind of wrong that nothing notices: the page still renders, the tests still
pass, and the reader finds a 404 in the one place they went looking for an
answer. The module list in the package docstring has the same problem in a
different shape - a name that reads as a place to look, and is not one.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import echoturn

ROOT = Path(__file__).resolve().parent.parent
MARKDOWN = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
MARKDOWN += sorted((ROOT / "docs").glob("*.md"))

# A relative link: not http(s), not a mail link, not a bare `#anchor`.
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)")

# `echoturn.something`, in the backticks the docstrings use.
MODULE = re.compile(r"``(echoturn(?:\.[a-z_]+)+)``")


def links(path: Path) -> list[str]:
    return LINK.findall(path.read_text("utf-8"))


def test_there_is_something_to_check():
    """A guard that found no documents would pass by looking at nothing."""
    assert len(MARKDOWN) > 2
    assert any(links(path) for path in MARKDOWN)


def test_every_relative_link_points_at_a_file_that_exists():
    missing = []
    for path in MARKDOWN:
        for link in links(path):
            target = (path.parent / link).resolve()
            if not target.exists():
                missing.append(f"{path.name} -> {link}")
    assert missing == []


def test_every_module_the_package_docstring_names_can_be_imported():
    named = sorted(set(MODULE.findall(echoturn.__doc__ or "")))
    assert named, "the package docstring names no modules"
    broken = []
    for name in named:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            broken.append(f"{name}: {exc}")
    assert broken == []


def test_every_module_in_the_package_is_named_in_the_docstring():
    """A module nobody is told about is a module nobody finds."""
    named = set(MODULE.findall(echoturn.__doc__ or ""))
    present = {
        f"echoturn.{path.parent.name}"
        for path in (ROOT / "src" / "echoturn").glob("*/__init__.py")
    }
    assert present - named == set()
