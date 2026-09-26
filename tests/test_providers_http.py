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


def test_an_idle_connection_outlives_the_gaps_in_a_call(monkeypatch):
    """httpx's own five seconds expires between one turn and the next.

    A turn is not a burst: the reply is generated, spoken and listened to, and
    the next request can be half a minute later. A connection that expired in
    between is a TCP and TLS handshake paid on the critical path of the next
    first sound, which is exactly what the shared client exists to avoid.
    """
    monkeypatch.delenv("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", raising=False)
    assert http.keepalive_expiry() == http.DEFAULT_KEEPALIVE_EXPIRY
    assert http.DEFAULT_KEEPALIVE_EXPIRY > 5.0, "no better than the httpx default"
    monkeypatch.setenv("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", "12.5")
    assert http.keepalive_expiry() == 12.5
    monkeypatch.setenv("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", "-3")
    assert http.keepalive_expiry() == 0.0, "a negative expiry is not a pool"
    monkeypatch.setenv("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", "soon")
    assert http.keepalive_expiry() == http.DEFAULT_KEEPALIVE_EXPIRY


def test_the_limits_carry_the_pool_size_and_the_keepalive(monkeypatch):
    monkeypatch.setenv("ECHOTURN_HTTP_POOL_SIZE", "8")
    monkeypatch.setenv("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", "45")
    limits = http.pool_limits(http.pool_size())
    assert limits.max_connections == 8
    assert limits.max_keepalive_connections == 8
    assert limits.keepalive_expiry == 45.0


def test_the_client_is_built_from_those_limits(monkeypatch):
    """The helper is only worth having if the client is built from it."""
    seen = []
    real = http.pool_limits

    def spy(size):
        seen.append(size)
        return real(size)

    monkeypatch.setattr(http, "pool_limits", spy)
    monkeypatch.setenv("ECHOTURN_HTTP_POOL_SIZE", "6")
    client = http.make_client()
    client.close()
    assert seen == [6]


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
