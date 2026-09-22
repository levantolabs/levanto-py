"""Shared test helpers.

* ``call`` runs one scenario against both the sync and the async client, so
  tests parametrized over ``MODES`` cover both code paths.
* ``Recorder`` is a MockTransport handler that records requests.
* ``assert_request`` / ``assert_response`` validate bodies against the Sage
  v1.1 OpenAPI spec in ``tests/data/openapi.json``. Request validation is
  strict: object schemas are closed, so a field the API doesn't define fails.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from levanto import AsyncLevantoClient, LevantoClient

MODES = ["sync", "async"]
API_KEY = "lv_test_key"
SPEC_PATH = Path(__file__).parent / "data" / "openapi.json"
SPEC: Dict[str, Any] = json.loads(SPEC_PATH.read_text())


def _closed(node: Any) -> Any:
    if isinstance(node, dict):
        node = {k: _closed(v) for k, v in node.items()}
        if node.get("type") == "object" and "properties" in node and "additionalProperties" not in node:
            node["additionalProperties"] = False
        return node
    if isinstance(node, list):
        return [_closed(v) for v in node]
    return node


def _validator(spec: Dict[str, Any], schema: str) -> jsonschema.protocols.Validator:
    registry = Registry().with_resource("urn:sage", Resource.from_contents(spec, default_specification=DRAFT202012))
    return jsonschema.Draft202012Validator({"$ref": f"urn:sage#/components/schemas/{schema}"}, registry=registry)


_STRICT = _closed(copy.deepcopy(SPEC))


def assert_request(body: Any, schema: str) -> None:
    """``body`` must be a valid, closed-world instance of the spec's ``schema``."""
    errors = sorted(_validator(_STRICT, schema).iter_errors(body), key=str)
    assert not errors, "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)


def assert_response(body: Any, schema: str) -> None:
    """``body`` must be a valid instance of the spec's response ``schema`` (open world)."""
    errors = sorted(_validator(SPEC, schema).iter_errors(body), key=str)
    assert not errors, "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)


class Recorder:
    """MockTransport handler: records requests and replies from a queue of (status, json, headers)."""

    def __init__(self, *replies: Any) -> None:
        self.replies: List[Any] = list(replies) or [(200, {})]
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        status, body, *rest = reply
        headers = rest[0] if rest else {}
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body, headers=headers)
        return httpx.Response(status, text=body or "", headers=headers)

    @property
    def body(self) -> Any:
        return json.loads(self.requests[-1].content)


async def call(
    mode: str, handler: Callable[[httpx.Request], httpx.Response], method: str, *args: Any, client: Dict[str, Any] | None = None, **kwargs: Any
) -> Any:
    opts = {"api_key": API_KEY, "max_retries": 0, **(client or {})}
    if mode == "sync":
        with LevantoClient(transport=httpx.MockTransport(handler), **opts) as c:
            return getattr(c, method)(*args, **kwargs)
    async with AsyncLevantoClient(transport=httpx.MockTransport(handler), **opts) as ac:
        return await getattr(ac, method)(*args, **kwargs)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries back off instantly in tests."""
    import asyncio
    import time

    async def _asleep(_: float) -> None:
        return None

    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(asyncio, "sleep", _asleep)
