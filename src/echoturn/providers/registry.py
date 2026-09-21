"""Pick a provider by name.

The name comes from the environment by default and from the caller when there is
one, so a host can put the choice in a config file and still override it in a
test. Names are matched in any case and with surrounding space, because they come
out of files people edit by hand.

The default is the offline provider. That is a deliberate choice about first
impressions: somebody who installs this should be able to run it, hear something
and change it, without an account first. Nothing about it is silent - the mock
voice is a beep and the mock transcript says so.

A name that is not in the registry is refused, with the available names in the
message. Falling back to the mock instead would turn a typo in a config file into
a working-looking system that never talks to the provider it was configured for.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..config import env_str
from .mock import MockASR, MockLLM, MockTTS


def _openai_tts():
    # Imported inside the factory: the adapter pulls in an HTTP client, and a host
    # that only ever uses the offline providers should not pay for it.
    from .openai_compatible import OpenAICompatibleTTS

    return OpenAICompatibleTTS()


def _openai_asr():
    from .openai_compatible import OpenAICompatibleASR

    return OpenAICompatibleASR()


def _openai_llm():
    from .openai_compatible import OpenAICompatibleLLM

    return OpenAICompatibleLLM()


# Provider names are the keys here, and the value is a factory rather than an
# instance: building a provider can read a key or import a client library, and
# neither should happen for a provider nobody asked for.
#
# "openai" means "anything that serves the OpenAI HTTP shape", which is the point
# of the adapter - the name is the protocol, not the company.
TTS_PROVIDERS: dict[str, Callable[[], Any]] = {"mock": MockTTS, "openai": _openai_tts}
ASR_PROVIDERS: dict[str, Callable[[], Any]] = {"mock": MockASR, "openai": _openai_asr}
LLM_PROVIDERS: dict[str, Callable[[], Any]] = {"mock": MockLLM, "openai": _openai_llm}

DEFAULT_PROVIDER = "mock"


def _pick(
    kind: str,
    registry: Mapping[str, Callable[[], Any]],
    name: str | None,
    env: str,
) -> Any:
    wanted = str(name or env_str(env, DEFAULT_PROVIDER)).strip().lower()
    factory = registry.get(wanted)
    if factory is None:
        known = ", ".join(sorted(registry))
        raise ValueError(
            f"unknown {kind} provider {wanted!r} "
            f"(set {env}, or pass the name directly); available: {known}"
        )
    return factory()


def make_tts(provider: str | None = None):
    """Build the speech synthesis provider named by ``provider`` or the environment."""
    return _pick("TTS", TTS_PROVIDERS, provider, "ECHOTURN_TTS_PROVIDER")


def make_asr(provider: str | None = None):
    """Build the recogniser named by ``provider`` or by the environment."""
    return _pick("ASR", ASR_PROVIDERS, provider, "ECHOTURN_ASR_PROVIDER")


def make_llm(provider: str | None = None):
    """Build the text model provider named by ``provider`` or the environment."""
    return _pick("LLM", LLM_PROVIDERS, provider, "ECHOTURN_LLM_PROVIDER")
