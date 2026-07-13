"""The synchronous :class:`LevantoClient` and asynchronous
:class:`AsyncLevantoClient`.

Both share an identical public surface and delegate all request building,
serialization, parsing, error mapping and retry policy to :mod:`levanto._http`;
only the transport call and the sleep primitive differ between them.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Union, overload

import httpx

from . import _http
from .errors import LevantoError
from .questions import (
    Choice,
    Grounding,
    OptionInput,
    Question,
    LevelInput,
    Scale,
    Sort,
    Tags,
    TagInput,
    YesNo,
)
from .types import (
    BatchItem,
    ChoiceResult,
    Content,
    Envelope,
    GroupResult,
    ScaleResult,
    SortResult,
    TagsResult,
    YesNoResult,
)

__all__ = ["LevantoClient", "AsyncLevantoClient", "Group"]

DEFAULT_BASE_URL = "https://sage.levanto.ai"


@dataclass
class Group:
    """A shared document plus the questions to ask about it (one batch group).

    Pass a list of these to :meth:`LevantoClient.decide_groups` to score
    several documents, each with their own questions, in one round-trip.
    """

    document: Content
    questions: Sequence[Question] = field(default_factory=list)


def _is_batch(question: Union[Question, Sequence[Question]]) -> bool:
    return isinstance(question, (list, tuple))


class LevantoClient:
    """Synchronous client for the Levanto Sage decision API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=_http.default_headers(api_key),
            transport=transport,
        )

    # -- lifecycle -------------------------------------------------------- #

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LevantoClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- transport -------------------------------------------------------- #

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        retry_statuses: bool = True,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = self._client.request(method, url, json=json)
            except httpx.TransportError as exc:
                if attempt < self._max_retries:
                    time.sleep(_http.backoff_delay(attempt))
                    attempt += 1
                    continue
                # Wrap the raw httpx error so callers only ever see LevantoError
                # (mirrors the JS client, which wraps transport failures too).
                raise LevantoError(f"Request to {url} failed: {exc}") from exc
            if retry_statuses and _http.should_retry(
                response.status_code, attempt, self._max_retries
            ):
                time.sleep(_http.backoff_delay(attempt))
                attempt += 1
                continue
            return response

    # -- core ------------------------------------------------------------- #

    @overload
    def decide(self, document: Content, question: Question) -> Envelope: ...

    @overload
    def decide(
        self, document: Content, question: Sequence[Question]
    ) -> List[BatchItem]: ...

    def decide(
        self, document: Content, question: Union[Question, Sequence[Question]]
    ) -> Union[Envelope, List[BatchItem]]:
        """Make one decision, or a batch of decisions over the same document.

        A single :class:`~levanto.questions.Question` returns the full
        :class:`~levanto.types.Envelope`; a list/tuple of questions calls
        ``/decide/batch`` and returns a list of
        :class:`~levanto.types.BatchItem` aligned to input order.
        """

        if _is_batch(question):
            questions = list(question)  # type: ignore[arg-type]
            body = _http.build_batch_body(document, questions)
            response = self._request("POST", "/decide/batch", json=body)
            data = _http.handle_response(response)
            return _http.parse_batch(questions, data)

        body = _http.build_single_body(document, question)  # type: ignore[arg-type]
        response = self._request("POST", "/decide", json=body)
        data = _http.handle_response(response)
        return _http.parse_single(data)

    def decide_groups(self, groups: Sequence[Group]) -> List[GroupResult]:
        """Score several documents in one round-trip, each with its own questions.

        Returns one :class:`~levanto.types.GroupResult` per input group, in
        order; each group's ``items`` are the flattened
        :class:`~levanto.types.BatchItem`s for that group's questions (the same
        shape :meth:`decide` returns for a list of questions).
        """

        glist = list(groups)
        body = _http.build_groups_body([(g.document, g.questions) for g in glist])
        response = self._request("POST", "/decide/batch", json=body)
        data = _http.handle_response(response)
        results = data.get("results", [])
        out: List[GroupResult] = []
        for i, g in enumerate(glist):
            grp = results[i] if i < len(results) else {}
            out.append({"items": _http.parse_group_answers(list(g.questions), grp)})
        return out

    def ready(self) -> bool:
        """``GET /ready``: ``True`` on 200, ``False`` otherwise (503 = loading)."""

        response = self._request("GET", "/ready", retry_statuses=False)
        return response.status_code == 200

    # -- shortcuts (single only; return just the result payload) ---------- #

    def yesno(
        self,
        document: Content,
        instructions: str,
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> YesNoResult:
        env = self.decide(document, YesNo(instructions, id=id, grounding=grounding))
        return env["result"]  # type: ignore[return-value]

    def choice(
        self,
        document: Content,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> ChoiceResult:
        env = self.decide(
            document, Choice(instructions, options, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]

    def scale(
        self,
        document: Content,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> ScaleResult:
        env = self.decide(
            document, Scale(instructions, levels, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]

    def sort(
        self,
        items: Content,
        instructions: str,
        *,
        id: Optional[str] = None,
    ) -> SortResult:
        env = self.decide(items, Sort(instructions, id=id))
        return env["result"]  # type: ignore[return-value]

    def tags(
        self,
        document: Content,
        tags: Sequence[TagInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
        instructions: Optional[str] = None,
    ) -> TagsResult:
        env = self.decide(
            document, Tags(tags, instructions=instructions, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]


class AsyncLevantoClient:
    """Asynchronous client for the Levanto Sage decision API.

    Identical surface to :class:`LevantoClient`; every request method is a
    coroutine.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=_http.default_headers(api_key),
            transport=transport,
        )

    # -- lifecycle -------------------------------------------------------- #

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncLevantoClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # -- transport -------------------------------------------------------- #

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        retry_statuses: bool = True,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, url, json=json)
            except httpx.TransportError as exc:
                if attempt < self._max_retries:
                    await asyncio.sleep(_http.backoff_delay(attempt))
                    attempt += 1
                    continue
                # Wrap the raw httpx error so callers only ever see LevantoError
                # (mirrors the JS client, which wraps transport failures too).
                raise LevantoError(f"Request to {url} failed: {exc}") from exc
            if retry_statuses and _http.should_retry(
                response.status_code, attempt, self._max_retries
            ):
                await asyncio.sleep(_http.backoff_delay(attempt))
                attempt += 1
                continue
            return response

    # -- core ------------------------------------------------------------- #

    @overload
    async def decide(self, document: Content, question: Question) -> Envelope: ...

    @overload
    async def decide(
        self, document: Content, question: Sequence[Question]
    ) -> List[BatchItem]: ...

    async def decide(
        self, document: Content, question: Union[Question, Sequence[Question]]
    ) -> Union[Envelope, List[BatchItem]]:
        """See :meth:`LevantoClient.decide`."""

        if _is_batch(question):
            questions = list(question)  # type: ignore[arg-type]
            body = _http.build_batch_body(document, questions)
            response = await self._request("POST", "/decide/batch", json=body)
            data = _http.handle_response(response)
            return _http.parse_batch(questions, data)

        body = _http.build_single_body(document, question)  # type: ignore[arg-type]
        response = await self._request("POST", "/decide", json=body)
        data = _http.handle_response(response)
        return _http.parse_single(data)

    async def decide_groups(self, groups: Sequence[Group]) -> List[GroupResult]:
        """See :meth:`LevantoClient.decide_groups`."""

        glist = list(groups)
        body = _http.build_groups_body([(g.document, g.questions) for g in glist])
        response = await self._request("POST", "/decide/batch", json=body)
        data = _http.handle_response(response)
        results = data.get("results", [])
        out: List[GroupResult] = []
        for i, g in enumerate(glist):
            grp = results[i] if i < len(results) else {}
            out.append({"items": _http.parse_group_answers(list(g.questions), grp)})
        return out

    async def ready(self) -> bool:
        """See :meth:`LevantoClient.ready`."""

        response = await self._request("GET", "/ready", retry_statuses=False)
        return response.status_code == 200

    # -- shortcuts -------------------------------------------------------- #

    async def yesno(
        self,
        document: Content,
        instructions: str,
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> YesNoResult:
        env = await self.decide(
            document, YesNo(instructions, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]

    async def choice(
        self,
        document: Content,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> ChoiceResult:
        env = await self.decide(
            document, Choice(instructions, options, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]

    async def scale(
        self,
        document: Content,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> ScaleResult:
        env = await self.decide(
            document, Scale(instructions, levels, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]

    async def sort(
        self,
        items: Content,
        instructions: str,
        *,
        id: Optional[str] = None,
    ) -> SortResult:
        env = await self.decide(items, Sort(instructions, id=id))
        return env["result"]  # type: ignore[return-value]

    async def tags(
        self,
        document: Content,
        tags: Sequence[TagInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
        instructions: Optional[str] = None,
    ) -> TagsResult:
        env = await self.decide(
            document, Tags(tags, instructions=instructions, id=id, grounding=grounding)
        )
        return env["result"]  # type: ignore[return-value]
