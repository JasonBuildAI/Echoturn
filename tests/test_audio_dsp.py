import builtins

import pytest

from echoturn.audio import _dsp
from echoturn.errors import MissingDependencyError


def test_the_numeric_stack_is_available_here():
    assert hasattr(_dsp.numpy(), "ndarray")


def test_a_missing_numeric_stack_names_the_extra_to_install(monkeypatch):
    """Without numpy the feature must say so, not quietly do nothing."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("numpy is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(MissingDependencyError) as excinfo:
        _dsp.numpy()
    assert "echoturn[dsp]" in str(excinfo.value)
    assert _dsp.FEATURE in str(excinfo.value)
