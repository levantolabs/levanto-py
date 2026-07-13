"""Shared, transport-agnostic core for both clients.

Everything that must behave identically across the sync and async clients
lives here so the two code paths cannot drift:

* request-body construction (content normalization, ``id`` defaulting,
  grounding lifting) and question serialization,
* response parsing (single envelope + batch alignment),
* HTTP status -> exception mapping,
* the retry/backoff policy.

Only the actual transport call (``httpx.Client.request`` vs
``httpx.AsyncClient.request``) differs, and each client implements its own
thin loop around :func:`should_retry` / :func:`backoff_delay`.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from .errors import (
    AuthError,
    LevantoAPIError,
    LevantoError,
    ServiceUnavailableError,
    ValidationError,
)
from .questions import (
    ChoiceOption,
    Grounding,
    ScaleLevel,
    TagSpec,
    Question,
)
from .types import BatchItem, Content, Envelope

__version__ = "0.1.0"
USER_AGENT = f"levanto-python/{__version__}"

#: Statuses the client retries (the endpoint is scale-to-zero).
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


# --------------------------------------------------------------------------- #
# Content normalization
# --------------------------------------------------------------------------- #


def normalize_content(document: Content) -> Any:
    """Turn a user ``document`` into a wire ``content`` value.

    * ``str`` is sent as-is (the API accepts a bare string as text).
    * ``dict`` (e.g. ``{"kind": "text" | "list", ...}``) passes through.
    * ``list`` is wrapped as ``{"kind": "list", "value": items}``.
    """

    if isinstance(document, str):
        return document
    if isinstance(document, dict):
        return document
    if isinstance(document, (list, tuple)):
        return {"kind": "list", "value": list(document)}
    raise TypeError(
        f"document must be str, dict, or list, got {type(document).__name__}"
    )


# --------------------------------------------------------------------------- #
# Question / sub-object serialization
# --------------------------------------------------------------------------- #


def _serialize_option(option: Any) -> Dict[str, Any]:
    if isinstance(option, ChoiceOption):
        wire: Dict[str, Any] = {"option": option.option}
        if option.description is not None:
            wire["description"] = option.description
        return wire
    if isinstance(option, dict):
        return option
    if isinstance(option, str):
        return {"option": option}
    raise TypeError(f"invalid choice option: {option!r}")


def _serialize_level(level: Any) -> Dict[str, Any]:
    if isinstance(level, ScaleLevel):
        wire: Dict[str, Any] = {"level": level.level}
        if level.description is not None:
            wire["description"] = level.description
        return wire
    if isinstance(level, dict):
        return level
    raise TypeError(f"invalid scale level: {level!r}")


def _serialize_tag(tag: Any) -> Dict[str, Any]:
    if isinstance(tag, TagSpec):
        wire: Dict[str, Any] = {"id": tag.id}
        if tag.name is not None:
            wire["name"] = tag.name
        if tag.threshold is not None:
            wire["threshold"] = tag.threshold
        return wire
    if isinstance(tag, dict):
        return tag
    if isinstance(tag, str):
        return {"id": tag}
    raise TypeError(f"invalid tag spec: {tag!r}")


def _serialize_grounding(grounding: Grounding) -> Dict[str, Any]:
    # Thin: send only the fields the caller set; the server fills defaults for
    # the rest. Keeps grounding serialization identical to the JS SDK.
    wire: Dict[str, Any] = {}
    if grounding.trigger is not None:
        wire["trigger"] = grounding.trigger
    if grounding.confidence_floor is not None:
        wire["confidence_floor"] = grounding.confidence_floor
    if grounding.extra:
        wire.update(grounding.extra)
    return wire


def _serialize_question(question: Question, *, default_id: str) -> Dict[str, Any]:
    """Build the wire ``question`` object (excluding grounding).

    ``id`` is filled with ``default_id`` when the question does not carry one;
    a user-supplied id is preserved.
    """

    kind = question.kind
    wire: Dict[str, Any] = {
        "id": question.id if question.id is not None else default_id,
        "kind": kind,
    }

    if kind == "yesno":
        wire["instructions"] = question.instructions
    elif kind == "choice":
        wire["instructions"] = question.instructions
        wire["options"] = [_serialize_option(o) for o in question.options]
    elif kind == "scale":
        wire["instructions"] = question.instructions
        wire["levels"] = [_serialize_level(level) for level in question.levels]
    elif kind == "sort":
        wire["instructions"] = question.instructions
    elif kind == "tags":
        # `instructions` is optional for tags; only emit it when set.
        if getattr(question, "instructions", None) is not None:
            wire["instructions"] = question.instructions
        wire["tags"] = [_serialize_tag(t) for t in question.tags]
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown question kind: {kind!r}")

    return wire


def _build_request_entry(
    content: Any, question: Question, *, default_id: str
) -> Dict[str, Any]:
    """One ``{content, question, grounding?}`` entry.

    Grounding is a top-level sibling of ``content``/``question`` on the wire,
    even though users attach it to the question for ergonomics. ``Sort`` never
    carries grounding.
    """

    entry: Dict[str, Any] = {
        "content": content,
        "question": _serialize_question(question, default_id=default_id),
    }
    grounding = getattr(question, "grounding", None)
    if grounding is not None:
        entry["grounding"] = _serialize_grounding(grounding)
    return entry


def build_single_body(document: Content, question: Question) -> Dict[str, Any]:
    """Body for ``POST /decide``. Single-call ids default to the kind string."""

    content = normalize_content(document)
    return _build_request_entry(content, question, default_id=question.kind)


def _serialize_batch_question(question: Question, *, default_id: str) -> Dict[str, Any]:
    """A batch question: the wire question with grounding *embedded*.

    Unlike single ``/decide`` (where grounding is a top-level sibling), the
    v0.5 batch API carries grounding inside each question object.
    """

    wire = _serialize_question(question, default_id=default_id)
    grounding = getattr(question, "grounding", None)
    if grounding is not None:
        wire["grounding"] = _serialize_grounding(grounding)
    return wire


def _build_group_entry(
    document: Content, questions: Sequence[Question]
) -> Dict[str, Any]:
    """One request group: ``{content, questions}`` (ids default ``q0, q1, ...``)."""

    return {
        "content": normalize_content(document),
        "questions": [
            _serialize_batch_question(q, default_id=f"q{i}")
            for i, q in enumerate(questions)
        ],
    }


def build_batch_body(
    document: Content, questions: Sequence[Question]
) -> Dict[str, Any]:
    """Body for ``POST /decide/batch``: one document + N questions.

    Under the v0.5 batch API this is a single group, so the shared document is
    sent once (not repeated per question). Ids default to ``q0, q1, ...``.
    """

    return {"requests": [_build_group_entry(document, list(questions))]}


def build_groups_body(
    groups: Sequence[Tuple[Content, Sequence[Question]]]
) -> Dict[str, Any]:
    """Body for ``POST /decide/batch`` with several ``(document, questions)`` groups."""

    return {"requests": [_build_group_entry(doc, list(qs)) for doc, qs in groups]}


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #


def parse_group_answers(
    questions: Sequence[Question], group: Dict[str, Any]
) -> List[BatchItem]:
    """Flatten one group's ``answers`` into ``BatchItem``s, aligned to ``questions``.

    ``id``/``kind`` come from each request's question (with the same ``q{i}``
    id defaulting used when building the request), so answers map back cleanly.
    """

    answers = (group or {}).get("answers", [])
    items: List[BatchItem] = []
    for i, question in enumerate(questions):
        raw = answers[i] if i < len(answers) else {}
        item: BatchItem = {
            "id": question.id if question.id is not None else f"q{i}",
            "kind": question.kind,
            "ok": bool(raw.get("ok", False)),
        }
        # On success the server nests a full single-decide envelope under
        # "result" ({id, kind, result, meta, grounding_meta?}); flatten it so a
        # batch item reads like a single decide (item["result"] is the bare
        # payload, with meta/grounding_meta lifted alongside it).
        envelope = raw.get("result")
        if isinstance(envelope, dict):
            if "result" in envelope:
                item["result"] = envelope["result"]
            if "meta" in envelope:
                item["meta"] = envelope["meta"]
            if envelope.get("grounding_meta") is not None:
                item["grounding_meta"] = envelope["grounding_meta"]
        if raw.get("error") is not None:
            item["error"] = raw["error"]
        items.append(item)
    return items


def parse_batch(
    questions: Sequence[Question], data: Dict[str, Any]
) -> List[BatchItem]:
    """Single-group batch response: flatten ``results[0].answers``."""

    results = data.get("results", [])
    first = results[0] if results else {}
    return parse_group_answers(questions, first)


# --------------------------------------------------------------------------- #
# Error mapping
# --------------------------------------------------------------------------- #


def _extract_detail(response: httpx.Response) -> Optional[str]:
    try:
        data = response.json()
    except Exception:
        text = response.text
        return text or None
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
        for key in ("message", "error"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        return None
    if isinstance(data, str):
        return data
    return None


def map_error(response: httpx.Response) -> LevantoError:
    """Map a non-2xx response to the appropriate exception instance."""

    status = response.status_code
    detail = _extract_detail(response)
    message = f"HTTP {status}" + (f": {detail}" if detail else "")

    if status in (401, 402):
        return AuthError(message, status=status, detail=detail)
    if status in (400, 422):
        return ValidationError(message, status=status, detail=detail)
    if status == 503:
        return ServiceUnavailableError(message, status=status, detail=detail)
    return LevantoAPIError(message, status=status, detail=detail)


def handle_response(response: httpx.Response) -> Any:
    """Return the parsed JSON body for a 2xx response, else raise."""

    if response.is_success:
        return response.json()
    raise map_error(response)


def parse_single(data: Dict[str, Any]) -> Envelope:
    """The single-decision envelope is returned as-is (already the right shape)."""

    return data  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Retry policy (shared by both transports)
# --------------------------------------------------------------------------- #


def should_retry(status: int, attempt: int, max_retries: int) -> bool:
    """Whether a response with ``status`` should be retried."""

    return status in RETRYABLE_STATUSES and attempt < max_retries


def backoff_delay(attempt: int, *, base: float = 0.5, cap: float = 8.0) -> float:
    """Exponential backoff with full jitter, in seconds.

    ``attempt`` is zero-based (0 for the delay before the first retry).
    """

    ceiling = min(cap, base * (2 ** attempt))
    return random.uniform(0.0, ceiling)


def default_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }


__all__ = [
    "normalize_content",
    "build_single_body",
    "build_batch_body",
    "build_groups_body",
    "parse_batch",
    "parse_group_answers",
    "parse_single",
    "handle_response",
    "map_error",
    "should_retry",
    "backoff_delay",
    "default_headers",
    "RETRYABLE_STATUSES",
    "USER_AGENT",
    "__version__",
]
