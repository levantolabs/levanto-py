"""The sync :class:`LevantoClient` and async :class:`AsyncLevantoClient`.

Both expose the same methods; everything except the transport loop is shared
through :mod:`levanto._core`.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, overload

import httpx

from . import _core
from .errors import LevantoError
from .questions import Choice, Grounding, LevelInput, OptionInput, Question, Scale, Sort, Tags, TagInput, YesNo
from .types import (
    BatchResult,
    ChoiceResult,
    Content,
    Envelope,
    GroupResult,
    GroupsResult,
    Reasoning,
    ScaleResult,
    SortResult,
    TagsResult,
    YesNoResult,
)

__all__ = ["LevantoClient", "AsyncLevantoClient", "Group"]

_UNSET: Any = object()


@dataclass
class Group:
    """One document plus the questions to ask about it, for :meth:`LevantoClient.decide_groups`."""

    document: Content
    questions: Sequence[Question] = field(default_factory=list)


def _api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("LEVANTO_API_KEY")
    if not key:
        raise LevantoError("No API key: pass api_key= or set LEVANTO_API_KEY.")
    return key


class _Base:
    _reasoning: Reasoning | None

    def _pick(self, reasoning: Any) -> Reasoning | None:
        return self._reasoning if reasoning is _UNSET else reasoning


class LevantoClient(_Base):
    """Client for the Levanto Sage decision API.

    ``reasoning`` sets the default for every call (``"auto"``, ``"off"``, or
    ``"on"``); leave it ``None`` for the server default (``"auto"``). Each
    method also takes ``reasoning=`` to override it for one call.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
        reasoning: Reasoning | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._reasoning = reasoning
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=_core.headers(_api_key(api_key)),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LevantoClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _send(self, method: str, path: str, body: Any = None, *, retry: bool = True) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = self._http.request(method, path, json=body)
            except httpx.TimeoutException as exc:
                raise LevantoError(f"{method} {path} timed out: {exc}") from exc
            except httpx.TransportError as exc:
                if retry and attempt < self._max_retries:
                    time.sleep(_core.backoff_delay(attempt))
                    attempt += 1
                    continue
                raise LevantoError(f"{method} {path} failed: {exc}") from exc
            if retry and _core.should_retry(response.status_code, attempt, self._max_retries):
                time.sleep(_core.backoff_delay(attempt, response))
                attempt += 1
                continue
            return response

    def _post(self, path: str, body: Dict[str, Any]) -> Any:
        return _core.raise_for_status(self._send("POST", path, body))

    @overload
    def decide(self, document: Content, question: Question, *, reasoning: Reasoning | None = ...) -> Envelope: ...
    @overload
    def decide(
        self, document: Content, question: Sequence[Question], *, reasoning: Reasoning | None = ...
    ) -> BatchResult: ...
    def decide(self, document: Content, question: Any, *, reasoning: Any = _UNSET) -> Any:
        """One question: ``POST /decide``, returns the :class:`Envelope`.

        A list of questions about the same document: one ``POST /decide/batch``
        call (the document is sent once), returns a :class:`BatchResult`: one
        :class:`BatchItem` per question, in order, plus the call's ``.meta``
        (usage and latency are reported there, not per item).
        """
        if isinstance(question, (list, tuple)):
            data = self._post("/decide/batch", _core.build_batch_body([(document, question)], self._pick(reasoning)))
            return BatchResult(_core.parse_batch([question], data)[0], _core.batch_meta(data))
        return self._post("/decide", _core.build_single_body(document, question, self._pick(reasoning)))

    def decide_groups(self, groups: Sequence[Group], *, reasoning: Reasoning | None = _UNSET) -> GroupsResult:
        """Several documents, each with its own questions, in one ``POST /decide/batch`` call.

        Returns one :class:`GroupResult` per group, in order, plus the call's ``.meta``.
        """
        groups = list(groups)
        body = _core.build_batch_body([(g.document, g.questions) for g in groups], self._pick(reasoning))
        data = self._post("/decide/batch", body)
        parsed = _core.parse_batch([g.questions for g in groups], data)
        return GroupsResult([{"items": items} for items in parsed], _core.batch_meta(data))

    def ready(self) -> bool:
        """``GET /ready``: ``True`` when Sage is serving. Never retried; network errors return ``False``."""
        try:
            return self._send("GET", "/ready", retry=False).status_code == 200
        except LevantoError:
            return False

    # Shortcuts: one question, returns only its ``result``.

    def yesno(
        self,
        document: Content,
        instructions: str,
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> YesNoResult:
        return self.decide(document, YesNo(instructions, id=id, grounding=grounding), reasoning=reasoning)["result"]  # type: ignore[return-value]

    def choice(
        self,
        document: Content,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> ChoiceResult:
        q = Choice(instructions, options, id=id, grounding=grounding)
        return self.decide(document, q, reasoning=reasoning)["result"]  # type: ignore[return-value]

    def scale(
        self,
        document: Content,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> ScaleResult:
        q = Scale(instructions, levels, id=id, grounding=grounding)
        return self.decide(document, q, reasoning=reasoning)["result"]  # type: ignore[return-value]

    def sort(
        self, items: Content, instructions: str, *, id: str | None = None, reasoning: Reasoning | None = _UNSET
    ) -> SortResult:
        return self.decide(items, Sort(instructions, id=id), reasoning=reasoning)["result"]  # type: ignore[return-value]

    def tags(
        self,
        document: Content,
        tags: Sequence[TagInput],
        *,
        instructions: str | None = None,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> TagsResult:
        q = Tags(tags, instructions=instructions, id=id, grounding=grounding)
        return self.decide(document, q, reasoning=reasoning)["result"]  # type: ignore[return-value]


class AsyncLevantoClient(_Base):
    """Async version of :class:`LevantoClient`: same methods, awaited."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
        reasoning: Reasoning | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._reasoning = reasoning
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=_core.headers(_api_key(api_key)),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncLevantoClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _send(self, method: str, path: str, body: Any = None, *, retry: bool = True) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._http.request(method, path, json=body)
            except httpx.TimeoutException as exc:
                raise LevantoError(f"{method} {path} timed out: {exc}") from exc
            except httpx.TransportError as exc:
                if retry and attempt < self._max_retries:
                    await asyncio.sleep(_core.backoff_delay(attempt))
                    attempt += 1
                    continue
                raise LevantoError(f"{method} {path} failed: {exc}") from exc
            if retry and _core.should_retry(response.status_code, attempt, self._max_retries):
                await asyncio.sleep(_core.backoff_delay(attempt, response))
                attempt += 1
                continue
            return response

    async def _post(self, path: str, body: Dict[str, Any]) -> Any:
        return _core.raise_for_status(await self._send("POST", path, body))

    @overload
    async def decide(self, document: Content, question: Question, *, reasoning: Reasoning | None = ...) -> Envelope: ...
    @overload
    async def decide(
        self, document: Content, question: Sequence[Question], *, reasoning: Reasoning | None = ...
    ) -> BatchResult: ...
    async def decide(self, document: Content, question: Any, *, reasoning: Any = _UNSET) -> Any:
        """See :meth:`LevantoClient.decide`."""
        if isinstance(question, (list, tuple)):
            data = await self._post("/decide/batch", _core.build_batch_body([(document, question)], self._pick(reasoning)))
            return BatchResult(_core.parse_batch([question], data)[0], _core.batch_meta(data))
        return await self._post("/decide", _core.build_single_body(document, question, self._pick(reasoning)))

    async def decide_groups(
        self, groups: Sequence[Group], *, reasoning: Reasoning | None = _UNSET
    ) -> GroupsResult:
        """See :meth:`LevantoClient.decide_groups`."""
        groups = list(groups)
        body = _core.build_batch_body([(g.document, g.questions) for g in groups], self._pick(reasoning))
        data = await self._post("/decide/batch", body)
        parsed = _core.parse_batch([g.questions for g in groups], data)
        return GroupsResult([{"items": items} for items in parsed], _core.batch_meta(data))

    async def ready(self) -> bool:
        """See :meth:`LevantoClient.ready`."""
        try:
            return (await self._send("GET", "/ready", retry=False)).status_code == 200
        except LevantoError:
            return False

    async def yesno(
        self,
        document: Content,
        instructions: str,
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> YesNoResult:
        q = YesNo(instructions, id=id, grounding=grounding)
        return (await self.decide(document, q, reasoning=reasoning))["result"]  # type: ignore[return-value]

    async def choice(
        self,
        document: Content,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> ChoiceResult:
        q = Choice(instructions, options, id=id, grounding=grounding)
        return (await self.decide(document, q, reasoning=reasoning))["result"]  # type: ignore[return-value]

    async def scale(
        self,
        document: Content,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> ScaleResult:
        q = Scale(instructions, levels, id=id, grounding=grounding)
        return (await self.decide(document, q, reasoning=reasoning))["result"]  # type: ignore[return-value]

    async def sort(
        self, items: Content, instructions: str, *, id: str | None = None, reasoning: Reasoning | None = _UNSET
    ) -> SortResult:
        return (await self.decide(items, Sort(instructions, id=id), reasoning=reasoning))["result"]  # type: ignore[return-value]

    async def tags(
        self,
        document: Content,
        tags: Sequence[TagInput],
        *,
        instructions: str | None = None,
        id: str | None = None,
        grounding: Grounding | None = None,
        reasoning: Reasoning | None = _UNSET,
    ) -> TagsResult:
        q = Tags(tags, instructions=instructions, id=id, grounding=grounding)
        return (await self.decide(document, q, reasoning=reasoning))["result"]  # type: ignore[return-value]
