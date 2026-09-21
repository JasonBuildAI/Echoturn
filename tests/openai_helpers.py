"""Small helpers shared by the OpenAI-compatible adapter tests. Not a test module."""
from __future__ import annotations

import json

import httpx


def client_answering(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def sse(*frames: dict) -> bytes:
    """A server-sent-event body, framed the way a chat completion endpoint frames it."""
    body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
    return (body + "data: [DONE]\n\n").encode("utf-8")


def delta(text: str) -> dict:
    return {"choices": [{"delta": {"content": text}}]}
