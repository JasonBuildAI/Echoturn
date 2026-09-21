"""Detect the separators a model uses to split one answer into several messages.

Both a line of dashes and a blank line count. Requiring the dashes alone would
mean that a model which segments its answer with blank lines is read as having
sent one enormous message, which is exactly what happens in practice: a model
told to use "---" still paragraphs with newlines most of the time.

The separator is structure. It is preserved by cleaning and removed by the
splitter - never earlier, or there would be nothing left to split on.
"""
from __future__ import annotations

import re

# A whole line of three or more dashes (any of the three dash characters, or "=").
MESSAGE_SEP = re.compile(r"^[ \t]*[-—–=]{3,}[ \t]*$")
# The same run written inside a line, which the model does occasionally. That one
# is not structure, it is noise, and it gets removed before reaching synthesis.
STRAY_SEP = re.compile(r"[-—–=]{3,}")
# "this could still grow into a separator": nothing but dashes and spaces so far.
SEP_PREFIX = re.compile(r"^[ \t]*[-—–=]*$")


def is_message_sep(line: str) -> bool:
    """True for an empty line or a line made only of a dash run."""
    t = str(line or "").strip()
    return (not t) or bool(MESSAGE_SEP.match(t))
