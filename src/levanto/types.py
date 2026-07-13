"""Typed structures for the shapes the Sage API returns.

These are :class:`typing.TypedDict` definitions: at runtime the values are
plain ``dict`` objects, but the annotations let type checkers understand the
result payloads, response envelopes and batch items the client hands back.

Optional keys are modelled with the base-class + ``total=False`` inheritance
pattern so the SDK stays compatible with Python 3.9 (which lacks
``typing.NotRequired``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from typing import TypedDict

__all__ = [
    "Content",
    "Meta",
    "YesNoResult",
    "ChoiceProbability",
    "ChoiceResult",
    "ScaleResult",
    "SortResult",
    "TagResult",
    "TagsResult",
    "Result",
    "Envelope",
    "BatchItem",
    "BatchResponse",
    "GroupResult",
]

# A document/content value accepted by the client before normalization.
Content = Union[str, Dict[str, Any], List[Any]]


class Meta(TypedDict):
    """Per-response metadata block."""

    model: str
    latency_ms: float


class YesNoResult(TypedDict):
    """Result payload for a ``yesno`` question."""

    probability: float
    confidence: float
    answer: Literal["yes", "no"]


class ChoiceProbability(TypedDict):
    """One option/probability pair inside a ``choice`` result."""

    option: str
    probability: float


class ChoiceResult(TypedDict):
    """Result payload for a ``choice`` question."""

    chosen: str
    confidence: float
    probabilities: List[ChoiceProbability]


class ScaleResult(TypedDict):
    """Result payload for a ``scale`` question."""

    expectation: float
    confidence: float


class SortResult(TypedDict):
    """Result payload for a ``sort`` question.

    The API types ``confidence`` as nullable, so it must never be assumed to be
    a number.
    """

    sorted: List[str]
    confidence: Optional[float]


class _TagResultBase(TypedDict):
    id: str
    probability: float
    confidence: float


class TagResult(_TagResultBase, total=False):
    """One entry inside a ``tags`` result.

    ``applies`` is a ``bool`` when the corresponding
    :class:`~levanto.questions.TagSpec` carried a ``threshold``, otherwise
    ``None``.
    """

    applies: Optional[bool]


class TagsResult(TypedDict):
    """Result payload for a ``tags`` question."""

    tags: List[TagResult]


# Union over every result payload shape.
Result = Union[
    YesNoResult,
    ChoiceResult,
    ScaleResult,
    SortResult,
    TagsResult,
]


class _EnvelopeBase(TypedDict):
    id: str
    kind: str
    result: Result
    meta: Meta


class Envelope(_EnvelopeBase, total=False):
    """Full response envelope for a single decision.

    ``grounding_meta`` is present only when grounding (web search) ran.
    """

    grounding_meta: Dict[str, Any]


class _BatchItemBase(TypedDict):
    id: str
    kind: str
    ok: bool


class BatchItem(_BatchItemBase, total=False):
    """One item of a batch decision, aligned to the input question order.

    A successful item (``ok is True``) reads exactly like a single decide:
    ``result`` is the bare payload (same shape as ``Envelope["result"]``), with
    ``meta`` and, when grounding ran, ``grounding_meta`` alongside it. A failed
    item (``ok is False``) carries ``error`` instead. On the wire the server
    nests a full envelope under each item's ``result``; the client flattens it
    so access matches a single decide.
    """

    result: Result
    meta: Meta
    grounding_meta: Dict[str, Any]
    error: str


class BatchResponse(TypedDict):
    """Wire shape of the ``POST /decide/batch`` response body."""

    results: List[Dict[str, Any]]
    meta: Dict[str, Any]


class GroupResult(TypedDict):
    """One group of a grouped batch (:meth:`LevantoClient.decide_groups`).

    ``items`` are the flattened :class:`BatchItem`s for that group's questions,
    in order, aligned to the input groups.
    """

    items: List[BatchItem]
