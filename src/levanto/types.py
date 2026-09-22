"""Response types. At runtime every value is a plain ``dict`` (JSON as the API sends it).

Keys that the API may omit are declared on a ``total=False`` subclass.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict, Union

__all__ = [
    "Reasoning",
    "Content",
    "YesNoResult",
    "ChoiceProbability",
    "ChoiceResult",
    "ScaleResult",
    "SortResult",
    "TagResult",
    "TagsResult",
    "Result",
    "Usage",
    "ReasoningMeta",
    "Meta",
    "Source",
    "GroundingMeta",
    "Envelope",
    "BatchItem",
    "GroupResult",
]

Reasoning = Literal["auto", "off", "on"]

# What a ``document`` can be: text, a list of ``{"id", "content"}`` items (Sort),
# an :class:`~levanto.Image`, or a raw wire ``content`` dict.
Content = Union[str, List[Dict[str, Any]], Dict[str, Any], Any]


class YesNoResult(TypedDict):
    answer: Literal["yes", "no"] | None  # None: Sage isn't sure
    probability: float  # calibrated P(yes)


class ChoiceProbability(TypedDict):
    option: str
    probability: float


class ChoiceResult(TypedDict):
    chosen: str | None  # None: the top options are too close to call
    probability: float | None  # P(chosen is correct); None when chosen is None
    probabilities: List[ChoiceProbability]  # every option, request order; independent, don't sum to 1


class ScaleResult(TypedDict):
    expectation: float  # 0..4
    confidence: float


class SortResult(TypedDict):
    sorted: List[str]  # item ids, in order
    confidence: float | None


class TagResult(TypedDict):
    id: str
    probability: float  # calibrated P(tag applies)
    applies: bool | None  # None: too close to call


class TagsResult(TypedDict):
    tags: List[TagResult]


Result = Union[YesNoResult, ChoiceResult, ScaleResult, SortResult, TagsResult]


class _UsageBase(TypedDict):
    billed_input_tokens: int


class Usage(_UsageBase, total=False):
    rendered_tokens: int | None
    image_count: int
    image_tokens: int


class _ReasoningMetaBase(TypedDict):
    fired: bool  # the first pass signalled the question needs reasoning
    ran: bool  # the reasoning pass executed


class ReasoningMeta(_ReasoningMetaBase, total=False):
    finished: bool | None  # False: the first-pass answer was returned; None: didn't run
    tokens: int | None
    margin: float | None
    limited: Literal["cap", "timeout", "budget"] | None


class _MetaBase(TypedDict):
    model: str


class Meta(_MetaBase, total=False):
    latency_ms: float | None
    question_count: int | None
    compute_mode: str | None
    usage: Usage | None
    reasoning: ReasoningMeta | None  # omitted on kinds without a reasoning pass


class Source(TypedDict, total=False):
    url: str | None
    title: str | None
    snippet: str | None


class _GroundingMetaBase(TypedDict):
    triggered: bool


class GroundingMeta(_GroundingMetaBase, total=False):
    trigger_reason: str | None
    queries: List[str]
    sources: List[Source]
    added_context_tokens: int | None
    search_ms: float | None


class _EnvelopeBase(TypedDict):
    id: str
    kind: Literal["yesno", "choice", "scale", "sort", "tags"]
    result: Result
    meta: Meta


class Envelope(_EnvelopeBase, total=False):
    """A ``/decide`` response. ``grounding_meta`` is present when grounding was requested."""

    grounding_meta: GroundingMeta | None


class _BatchItemBase(TypedDict):
    id: str
    kind: str
    ok: bool


class BatchItem(_BatchItemBase, total=False):
    """One batch answer, in question order.

    ``ok=True``: reads like a single decide (``result``, ``meta``,
    ``grounding_meta``). ``ok=False``: ``error`` says why.
    """

    result: Result
    meta: Meta
    grounding_meta: GroundingMeta | None
    error: str


class GroupResult(TypedDict):
    items: List[BatchItem]
