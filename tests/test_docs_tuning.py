"""The tuning table is a copy, so something has to keep it a true one.

`docs/tuning.md` lists every dial by hand: its variable, its key and its
default. Nothing generates it, and a hand-written copy of a table is exactly the
kind of document that goes quietly wrong - a default changed in the code, the
table still claiming the old one, and the next reader treating the table as the
authority. This checks the copy against `DIALS`, so the drift cannot happen
without a test going red.

The Chinese page has the same table, and a translation is the easiest place in a
repository for a number to go stale: it is updated by somebody reading the other
file, which is precisely when a figure gets retyped. So it is checked the same
way, from the same source.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from echoturn.config import DIALS

DOCS = [
    Path(__file__).resolve().parent.parent / "docs" / name
    for name in ("tuning.md", "tuning.zh-CN.md")
]

# `| `VAR` | `key` | `default` | ... |`, which is every row of the one table
# whose first three columns are the dial itself.
ROW = re.compile(r"^\|\s*`([A-Z_]+)`\s*\|\s*`([a-z_]+)`\s*\|\s*`([^`]+)`\s*\|")


def normalise(value: object) -> str:
    """One cell and one default, in a shape they can be compared in.

    Written as text so that `16000`, `16000.0` and `1.6e4` are the same number,
    and lowercased so that `true` in a table and `True` in Python are the same
    boolean. Anything that is not a number is its own text.
    """
    text = str(value).strip().strip("`").strip()
    try:
        return repr(float(text))
    except ValueError:
        return text.lower()


def documented(doc: Path) -> list[tuple[str, str, str]]:
    """Every dial row of one table, as variable, key and default."""
    rows = []
    for line in doc.read_text("utf-8").splitlines():
        found = ROW.match(line)
        if found:
            rows.append(found.groups())
    return rows


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_the_table_has_a_row_for_every_dial(doc: Path):
    assert documented(doc), "the table could not be read at all"
    named = {row[0] for row in documented(doc)}
    missing = [
        dial.env for dial in DIALS if dial.env not in named
    ]
    assert missing == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_the_table_invents_no_dials_of_its_own(doc: Path):
    known = {dial.env for dial in DIALS}
    assert [row[0] for row in documented(doc) if row[0] not in known] == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_every_row_names_the_key_and_default_the_code_uses(doc: Path):
    """A row right about the variable and wrong about the number is worse."""
    wrong = []
    for env, key, default in documented(doc):
        dial = next((item for item in DIALS if item.env == env), None)
        if dial is None:
            continue
        if dial.key != key or normalise(dial.default) != normalise(default):
            wrong.append(
                f"{env}: the code says {dial.key}={dial.default!r}, "
                f"the table says {key}={default}"
            )
    assert wrong == []


def test_the_two_tables_have_the_same_rows():
    """Translated pages drift in a different direction from stale ones.

    A translation loses a row far more easily than it invents one, and the
    per-page checks above would not notice a row that is simply missing from
    both counts. This one compares the two pages to each other.
    """
    english, chinese = (documented(doc) for doc in DOCS)
    assert english == chinese
