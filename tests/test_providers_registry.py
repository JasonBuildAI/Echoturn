import pytest

from echoturn.protocols import ASRClient, LLMClient, TTSClient
from echoturn.providers import registry
from echoturn.providers.mock import MockASR, MockLLM, MockTTS


def test_the_default_is_a_provider_that_needs_no_key_and_no_network():
    assert isinstance(registry.make_tts(), MockTTS)
    assert isinstance(registry.make_asr(), MockASR)
    assert isinstance(registry.make_llm(), MockLLM)


def test_the_environment_names_the_provider(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TTS_PROVIDER", "mock")
    monkeypatch.setenv("ECHOTURN_ASR_PROVIDER", "mock")
    monkeypatch.setenv("ECHOTURN_LLM_PROVIDER", "mock")
    assert isinstance(registry.make_tts(), MockTTS)
    assert isinstance(registry.make_asr(), MockASR)
    assert isinstance(registry.make_llm(), MockLLM)


def test_a_name_given_directly_beats_the_environment(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TTS_PROVIDER", "not-a-provider")
    assert isinstance(registry.make_tts("mock"), MockTTS)


def test_a_name_from_a_config_file_may_arrive_messy(monkeypatch):
    monkeypatch.setenv("ECHOTURN_LLM_PROVIDER", "  Mock  ")
    assert isinstance(registry.make_llm(), MockLLM)


def test_a_blank_name_falls_back_to_the_default(monkeypatch):
    """`KEY=` in a config file means "leave it alone", not "provider called ''"."""
    monkeypatch.setenv("ECHOTURN_ASR_PROVIDER", "")
    assert isinstance(registry.make_asr(), MockASR)


@pytest.mark.parametrize(
    "factory", [registry.make_tts, registry.make_asr, registry.make_llm]
)
def test_an_unknown_name_is_refused_with_the_names_that_exist(factory):
    """Silently substituting the mock would hide a typo in a config file."""
    with pytest.raises(ValueError) as excinfo:
        factory("whisper-large")
    message = str(excinfo.value)
    assert "whisper-large" in message
    assert "mock" in message


def test_every_registered_provider_builds_into_something_of_the_right_shape():
    assert isinstance(registry.TTS_PROVIDERS["mock"](), TTSClient)
    assert isinstance(registry.ASR_PROVIDERS["mock"](), ASRClient)
    assert isinstance(registry.LLM_PROVIDERS["mock"](), LLMClient)
