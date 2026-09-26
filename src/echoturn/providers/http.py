"""One HTTP client per process, and one place that reports HTTP failures.

A turn makes several requests - recognise, generate, synthesise - and they are
partly sequential, so the cost of a connection is paid on the critical path.
Building a client per request means a new TCP connection each time, and over TLS
that handshake is tens of milliseconds nobody budgeted for. It also fails in a
confusing way: nothing looks wrong locally, and the symptom is that every user's
first sound gets slower as more users arrive.

The pool is sized above the expected concurrency for the same reason. The
request that arrives when the pool is full is the one that opens a connection
instead of waiting for one, and it is always the least convenient request.

An idle connection is kept for longer than httpx's own five seconds. A turn is
not a burst of requests: a reply is generated, spoken and listened to, and the
next request can be thirty seconds later. Expiring the connection in between
means the next request pays for a TCP and TLS handshake on the critical path,
which is the same cost the shared client exists to avoid - paid at the worst
possible moment.

Errors become :class:`~echoturn.errors.ProviderError` here, once, rather than at
each call site. What a host can act on is the status and what the service said,
and the body of a failed response is exactly the thing that gets swallowed when
each provider does its own error handling.
"""
from __future__ import annotations

import atexit
from contextlib import suppress
from typing import Any

import httpx

from ..config import env_float, env_int
from ..errors import ProviderError

# Connections held open for reuse. Comfortably above the concurrency a single
# process is expected to serve; below it, requests queue for an idle connection.
DEFAULT_POOL_SIZE = 32
# How long an idle connection stays in the pool. Comfortably longer than the
# quiet gaps a conversation has, and the number to lower if a host would rather
# not hold sockets open that long. Read now, so a host can retune it.
DEFAULT_KEEPALIVE_EXPIRY = 60.0
# A failed response can carry a whole HTML error page. Enough to recognise it,
# not enough to fill a log line.
DETAIL_LIMIT = 400

_CLIENT: httpx.Client | None = None


def pool_size() -> int:
    """How many connections to keep, read now so a host can retune it."""
    return max(2, env_int("ECHOTURN_HTTP_POOL_SIZE", DEFAULT_POOL_SIZE))


def keepalive_expiry() -> float:
    """How long an idle connection stays open, read now for the same reason."""
    return max(
        0.0,
        env_float("ECHOTURN_HTTP_KEEPALIVE_EXPIRY", DEFAULT_KEEPALIVE_EXPIRY),
    )


def pool_limits(size: int) -> httpx.Limits:
    """One place that builds the limits, so none of them is set in half."""
    return httpx.Limits(
        max_connections=size,
        max_keepalive_connections=size,
        keepalive_expiry=keepalive_expiry(),
    )


def make_client(*, pool_size_override: int | None = None) -> httpx.Client:
    """Build a client. Used for the shared one, and by callers who want their own."""
    size = pool_size_override or pool_size()
    # No global timeout: every request here passes its own. A single default would
    # have to be short enough for recognition and long enough for synthesis, and
    # it would be wrong for one of them.
    return httpx.Client(
        limits=pool_limits(size), timeout=None, follow_redirects=False
    )


def shared_client() -> httpx.Client:
    """The process-wide client, built on first use."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = make_client()
    return _CLIENT


def close() -> None:
    """Drop the shared client. Called at exit, and by tests that replace it."""
    global _CLIENT
    if _CLIENT is not None:
        with suppress(Exception):  # closing must never raise on the way out
            _CLIENT.close()
        _CLIENT = None


def detail_of(response: httpx.Response) -> str:
    """The service's own words about a failure, cut down to a usable length."""
    try:
        body = response.text
    except Exception:  # noqa: BLE001 - a body that cannot be read is not the story
        body = ""
    body = " ".join(body.split())
    return body[:DETAIL_LIMIT] or f"HTTP {response.status_code}"


def raise_for_status(response: httpx.Response, what: str) -> None:
    """Turn a failed response into a provider error naming what was attempted."""
    if response.status_code < 400:
        return
    raise ProviderError(
        f"{what} failed (HTTP {response.status_code})", detail=detail_of(response)
    )


def post_json(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float,
    what: str,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """POST JSON and return the response, or raise a readable provider error."""
    sender = client or shared_client()
    try:
        response = sender.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{what} failed (no response)", detail=str(exc)) from exc
    raise_for_status(response, what)
    return response


atexit.register(close)
