"""Shared test helpers.

The ``call`` helper runs the *same* scenario against both the sync
:class:`LevantoClient` and the async :class:`AsyncLevantoClient`, so every test
that awaits it is parametrized over ``MODES`` and exercises both code paths.

``call`` is always a coroutine: in ``sync`` mode it drives the sync client (no
internal awaits) and returns; in ``async`` mode it awaits the async client.
Tests therefore uniformly ``await call(...)``.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import httpx

from levanto import AsyncLevantoClient, LevantoClient

MODES = ["sync", "async"]

API_KEY = "test-key"


async def call(
    mode: str,
    handler: Callable[[httpx.Request], httpx.Response],
    method: str,
    *args: Any,
    client_kwargs: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Invoke ``method`` on a client wired to ``handler`` via MockTransport."""

    client_kwargs = dict(client_kwargs or {})
    transport = httpx.MockTransport(handler)
    if mode == "sync":
        client = LevantoClient(API_KEY, transport=transport, **client_kwargs)
        try:
            return getattr(client, method)(*args, **kwargs)
        finally:
            client.close()
    aclient = AsyncLevantoClient(API_KEY, transport=transport, **client_kwargs)
    try:
        return await getattr(aclient, method)(*args, **kwargs)
    finally:
        await aclient.aclose()


class Recorder:
    """A MockTransport handler that records requests and returns a canned body."""

    def __init__(self, status: int = 200, json_body: Optional[Any] = None) -> None:
        self.status = status
        self.json_body = json_body if json_body is not None else {}
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.json_body)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def body(self, index: int = -1) -> Dict[str, Any]:
        """The decoded JSON body of the recorded request at ``index``."""

        return json.loads(self.requests[index].content)


def json_error(status: int, detail: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": detail})

    return handler


# --------------------------------------------------------------------------- #
# Canned response bodies
# --------------------------------------------------------------------------- #

META = {"model": "sage-0.5", "latency_ms": 12.3}


def envelope(kind: str, result: Any, **extra: Any) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "id": extra.pop("id", kind),
        "kind": kind,
        "result": result,
        "meta": META,
    }
    env.update(extra)
    return env


YESNO_RESULT = {"probability": 0.92, "confidence": 0.81, "answer": "yes"}
CHOICE_RESULT = {
    "chosen": "approve",
    "confidence": 0.77,
    "probabilities": [
        {"option": "approve", "probability": 0.77},
        {"option": "revise", "probability": 0.23},
    ],
}
SCALE_RESULT = {"expectation": 3.4, "confidence": 0.6}
SORT_RESULT_NULL = {"sorted": ["b", "a", "c"], "confidence": None}
TAGS_RESULT = {
    "tags": [
        {"id": "pii", "probability": 0.95, "confidence": 0.9, "applies": True},
        {"id": "toxicity", "probability": 0.1, "confidence": 0.8},
    ]
}
