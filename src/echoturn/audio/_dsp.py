"""Load the optional numeric stack, or explain what is missing.

Imported inside functions rather than at module import time: the core pipeline
must keep working without these packages, and a top-level import would turn "an
optional feature is unavailable" into "the package does not import".

numpy is the only numeric dependency. A full signal-processing framework would
be a large requirement for every host that only wants the pitch and speed
helpers, so the few transforms that are actually needed are implemented here on
top of numpy instead.
"""
from __future__ import annotations

from ..errors import MissingDependencyError

# The wording is kept in one place: the same missing package can surface from
# pitch measurement, pitch locking and speed changes, and a host that sees three
# different messages for one cause will look for three different problems.
FEATURE = "pitch and speed processing"
EXTRA = "dsp"
PACKAGES = "numpy"


def numpy():
    """Return the numpy module, or raise naming the extra that provides it."""
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise MissingDependencyError(FEATURE, EXTRA, PACKAGES) from exc
    return numpy
