"""Errors a host is expected to handle, as opposed to bugs."""
from __future__ import annotations


class EchoturnError(Exception):
    """Base class for everything this package raises on purpose."""


class MissingDependencyError(EchoturnError):
    """An optional extra is needed for what was asked.

    Optional features fail loudly rather than quietly doing nothing. A silent
    no-op here would be indistinguishable from a working pipeline: the host would
    see audio coming out, just without the processing it configured, and nothing
    anywhere would say so. The message names the extra to install.
    """

    def __init__(self, feature: str, extra: str, packages: str) -> None:
        super().__init__(
            f"{feature} needs the optional '{extra}' extra "
            f"(pip install \"echoturn[{extra}]\"); it provides {packages}"
        )
        self.feature = feature
        self.extra = extra
        self.packages = packages


class ProviderError(EchoturnError):
    """A provider (ASR, TTS, LLM) refused or failed the request.

    ``message`` is safe to show to a user; ``detail`` is for logs only and may
    contain anything the remote service said.
    """

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message
