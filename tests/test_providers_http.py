import httpx
import pytest

from echoturn.errors import ProviderError
from echoturn.providers import http


def transport_client(handler):
    """A client that answers from a function instead of from the network."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_shared_client_is_built_once_and_reused():
    http.close()
    first = http.shared_client()
    assert http.shared_client() is first
    http.close()


def test_closing_the_shared_client_lets_a_new_one_be_built():
    first = http.shared_client()
    http.close()
    assert http.shared_client() is not first
    http.close()


def test_the_pool_is_at_least_two_and_follows_the_environment(monkeypatch):
    monkeypatch.delenv("ECHOTURN_HTTP_POOL_SIZE", raising=False)
    assert http.pool_size() == http.DEFAULT_POOL_SIZE
    monkeypatch.setenv("ECHOTURN_HTTP_POOL_SIZE", "8")
    assert http.pool_size() == 8
    monkeypatch.setenv("ECHOTURN_HTTP_POOL_SIZE", "1")
    assert http.pool_size() == 2
    monkeypatch.setenv("ECHOTURN_HTTP_POOL_SIZE", "many")
    assert http.pool_size() == http.DEFAULT_POOL_SIZE


def test_a_successful_post_returns_the_response():
    client = transport_client(lambda request: httpx.Response(200, json={"ok": True}))
    response = http.post_json(
        "https://example.test/v1/thing",
        payload={"a": 1},
        timeout=5.0,
        what="the thing",
        client=client,
    )
    assert response.json() == {"ok": True}


def test_a_failed_post_says_which_status_and_what_the_service_said():
    client = transport_client(
        lambda request: httpx.Response(429, text="rate limit exceeded")
    )
    with pytest.raises(ProviderError) as excinfo:
        http.post_json(
            "https://example.test/v1/thing",
            payload={},
            timeout=5.0,
            what="the thing",
            client=client,
        )
    assert "the thing" in str(excinfo.value)
    assert "429" in str(excinfo.value)
    assert excinfo.value.detail == "rate limit exceeded"


def test_a_long_error_body_is_cut_down():
    client = transport_client(
        lambda request: httpx.Response(500, text="x" * 5000)
    )
    with pytest.raises(ProviderError) as excinfo:
        http.post_json(
            "https://example.test/v1/thing",
            payload={},
            timeout=5.0,
            what="the thing",
            client=client,
        )
    assert len(excinfo.value.detail) == http.DETAIL_LIMIT


def test_a_connection_that_never_answers_is_reported_as_an_error():
    def explode(request):
        raise httpx.ConnectTimeout("timed out")

    client = transport_client(explode)
    with pytest.raises(ProviderError) as excinfo:
        http.post_json(
            "https://example.test/v1/thing",
            payload={},
            timeout=5.0,
            what="the thing",
            client=client,
        )
    assert "no response" in str(excinfo.value)


def test_a_failed_response_with_no_body_still_says_something():
    client = transport_client(lambda request: httpx.Response(502))
    with pytest.raises(ProviderError) as excinfo:
        http.post_json(
            "https://example.test/v1/thing",
            payload={},
            timeout=5.0,
            what="the thing",
            client=client,
        )
    assert "502" in excinfo.value.detail
