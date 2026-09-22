"""Transport-agnostic logic shared by the sync and async clients.

Request bodies, response parsing, error mapping, and the retry policy live here
so the two clients cannot drift; each client only adds its own transport loop.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple, cast

import httpx

from ._version import __version__
from .errors import (
    AllowanceExhaustedError,
    AuthError,
    LevantoAPIError,
    LevantoError,
    ServiceUnavailableError,
    ValidationError,
)
from .questions import Image, Question
from .types import BatchItem, BatchMeta, Content, Reasoning

USER_AGENT = f"levanto-python/{__version__}"
DEFAULT_BASE_URL = "https://sage.levanto.ai"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def normalize_content(document: Content) -> Any:
    """``str`` and ``dict`` pass through; :class:`Image` and lists become their wire forms."""
    if isinstance(document, (str, dict)):
        return document
    if isinstance(document, Image):
        return document.to_wire()
    if isinstance(document, (list, tuple)):
        return {"kind": "list", "value": list(document)}
    raise TypeError(f"document must be str, list, Image, or dict; got {type(document).__name__}")


def _with_reasoning(body: Dict[str, Any], reasoning: Reasoning | None) -> Dict[str, Any]:
    if reasoning is not None:
        body["reasoning"] = reasoning
    return body


def build_single_body(document: Content, question: Question, reasoning: Reasoning | None) -> Dict[str, Any]:
    """``POST /decide``: grounding is a top-level sibling; the id defaults to the kind."""
    body: Dict[str, Any] = {"content": normalize_content(document), "question": question.to_wire(question.kind)}
    if question.grounding is not None:
        body["grounding"] = question.grounding.to_wire()
    return _with_reasoning(body, reasoning)


def _group(document: Content, questions: Sequence[Question]) -> Dict[str, Any]:
    wire_questions = []
    for i, q in enumerate(questions):
        wq = q.to_wire(f"q{i}")
        if q.grounding is not None:  # in a batch, grounding sits inside each question
            wq["grounding"] = q.grounding.to_wire()
        wire_questions.append(wq)
    return {"content": normalize_content(document), "questions": wire_questions}


def build_batch_body(
    groups: Sequence[Tuple[Content, Sequence[Question]]], reasoning: Reasoning | None
) -> Dict[str, Any]:
    """``POST /decide/batch``: one group per document; question ids default to ``q0, q1, ...``."""
    for _, questions in groups:
        if not questions:
            raise ValueError("every batch group needs at least one question")
    return _with_reasoning({"requests": [_group(doc, qs) for doc, qs in groups]}, reasoning)


def parse_group(questions: Sequence[Question], group: Dict[str, Any] | None) -> List[BatchItem]:
    """Flatten one group's answers so each item reads like a single decide."""
    answers = (group or {}).get("answers") or []
    items: List[BatchItem] = []
    for i, q in enumerate(questions):
        raw: Dict[str, Any] = answers[i] if i < len(answers) else {"ok": False, "error": "missing answer in response"}
        item: BatchItem = {"id": q.id if q.id is not None else f"q{i}", "kind": q.kind, "ok": bool(raw.get("ok"))}
        env = raw.get("result")
        if isinstance(env, dict):
            item["result"] = env.get("result")  # type: ignore[typeddict-item]
            if "meta" in env:
                item["meta"] = env["meta"]
            if env.get("grounding_meta") is not None:
                item["grounding_meta"] = env["grounding_meta"]
        if raw.get("error") is not None:
            item["error"] = raw["error"]
        items.append(item)
    return items


def parse_batch(groups: Sequence[Sequence[Question]], data: Dict[str, Any]) -> List[List[BatchItem]]:
    results = data.get("results") or []
    return [parse_group(qs, results[i] if i < len(results) else None) for i, qs in enumerate(groups)]


def batch_meta(data: Dict[str, Any]) -> BatchMeta:
    """The call-level ``meta`` of a batch response (usage and latency live here)."""
    return cast(BatchMeta, data.get("meta") or {})


def _detail(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return response.text or None
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None:
            return detail if isinstance(detail, str) else str(detail)
    return str(data) if data else None


def raise_for_status(response: httpx.Response) -> Any:
    """Return the JSON body of a 2xx response; otherwise raise the matching error."""
    if response.is_success:
        return response.json()
    status, detail = response.status_code, _detail(response)
    message = f"HTTP {status}" + (f": {detail}" if detail else "")
    cls: type[LevantoError] = {
        400: ValidationError,
        401: AuthError,
        402: AllowanceExhaustedError,
        422: ValidationError,
        503: ServiceUnavailableError,
    }.get(status, LevantoAPIError)
    raise cls(message, status=status, detail=detail)


def should_retry(status: int, attempt: int, max_retries: int) -> bool:
    return status in RETRYABLE_STATUSES and attempt < max_retries


def backoff_delay(attempt: int, response: httpx.Response | None = None) -> float:
    """Seconds before retry ``attempt`` (0-based): ``Retry-After`` if sent, else exponential with jitter."""
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                pass
    return random.uniform(0.0, min(8.0, 0.5 * 2**attempt))


def headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
