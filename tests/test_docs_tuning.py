"""The tuning table is a copy, so something has to keep it a true one.

`docs/tuning.md` lists every dial by hand: its variable, its key and its
default. Nothing generates it, and a hand-written copy of a table is exactly the
kind of document that goes quietly wrong - a default changed in the code, the
table still claiming the old one, and the next reader treating the table as the
authority. This checks the copy against `DIALS`, so the drift cannot happen
without a test going red.
"""
from __future__ import annotations

import re
from pathlib import Path

from echoturn.config import DIALS

DOC = Path(__file__).resolve().parent.parent / "docs" / "tuning.md"

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


def documented() -> list[tuple[str, str, str]]:
    """Every dial row of the table, as variable, key and default."""
    rows = []
    for line in DOC.read_text("utf-8").splitlines():
        found = ROW.match(line)
        if found:
            rows.append(found.groups())
    return rows


def test_the_table_has_a_row_for_every_dial():
    assert documented(), "the table could not be read at all"
    missing = [
        dial.env for dial in DIALS if dial.env not in {row[0] for row in documented()}
    ]
    assert missing == []


def test_the_table_invents_no_dials_of_its_own():
    known = {dial.env for dial in DIALS}
    assert [row[0] for row in documented() if row[0] not in known] == []


def test_every_row_names_the_key_and_default_the_code_uses():
    """A row right about the variable and wrong about the number is worse."""
    wrong = []
    for env, key, default in documented():
        dial = next((item for item in DIALS if item.env == env), None)
        if dial is None:
            continue
        if dial.key != key or normalise(dial.default) != normalise(default):
            wrong.append(
                f"{env}: the code says {dial.key}={dial.default!r}, "
                f"the table says {key}={default}"
            )
    assert wrong == []
