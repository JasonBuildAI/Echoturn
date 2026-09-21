import json

import httpx
import pytest

from echoturn.errors import ProviderError
from echoturn.providers.openai_compatible import OpenAICompatibleLLM
from openai_helpers import client_answering, delta, sse


def build(handler, **kwargs):
    return OpenAICompatibleLLM(
        key="test-key", client=client_answering(handler), **kwargs
    )


def test_the_reply_arrives_piece_by_piece():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=sse(delta("Hel"), delta("lo"), delta("!")))

    assert list(build(handler).stream([{"role": "user", "content": "hi"}])) == [
        "Hel",
        "lo",
        "!",
    ]
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["stream"] is True
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_frames_without_text_are_not_empty_pieces():
    """The first frame usually carries a role and nothing else."""
    frames = (
        {"choices": [{"delta": {"role": "assistant"}}]},
        delta("one"),
        {"choices": []},
        delta(" two"),
    )
    handler = lambda request: httpx.Response(200, content=sse(*frames))  # noqa: E731
    assert list(build(handler).stream([])) == ["one", " two"]


def test_no_token_cap_is_sent_unless_one_was_asked_for():
    """A library that quietly caps replies truncates somebody's sentences."""
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=sse(delta("ok")))

    list(build(handler).stream([]))
    assert "max_tokens" not in seen
    list(build(handler, max_tokens=64).stream([]))
    assert seen["max_tokens"] == 64


def test_temperature_is_left_to_the_model():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=sse(delta("ok")))

    list(build(handler).stream([]))
    assert "temperature" not in seen


def test_a_failed_request_is_reported_with_its_status():
    handler = lambda request: httpx.Response(401, text="bad key")  # noqa: E731
    with pytest.raises(ProviderError) as excinfo:
        list(build(handler).stream([{"role": "user", "content": "hi"}]))
    assert "401" in str(excinfo.value)
    assert excinfo.value.detail == "bad key"


def test_a_stream_that_stops_being_json_is_not_silently_skipped():
    body = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: {oops\n\n'
    handler = lambda request: httpx.Response(200, content=body)  # noqa: E731
    with pytest.raises(ProviderError):
        list(build(handler).stream([]))


def test_a_missing_key_names_the_variable_that_is_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from echoturn.providers.openai_compatible import api_key

    with pytest.raises(ProviderError) as excinfo:
        api_key()
    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_the_model_and_the_root_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("ECHOTURN_LLM_MODEL", "some-model")
    monkeypatch.setenv("ECHOTURN_BASE_URL", "https://elsewhere.test/v1/")
    client = OpenAICompatibleLLM(key="k")
    assert client.model == "some-model"
    assert client.base == "https://elsewhere.test/v1"
