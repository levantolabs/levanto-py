"""Question types and their sub-objects.

One dataclass per decision *kind* (:class:`YesNo`, :class:`Choice`,
:class:`Scale`, :class:`Sort`, :class:`Tags`) plus the small value objects they
compose (:class:`ChoiceOption`, :class:`ScaleLevel`, :class:`TagSpec`,
:class:`Grounding`).

Bare-value shorthands are normalized here at construction time so the rest of
the SDK only ever sees canonical objects (or raw ``dict`` pass-throughs):

* ``Choice(instr, ["approve", "revise"])`` -> each string becomes a
  :class:`ChoiceOption`.
* ``Scale(instr, ["worst", "bad", "ok", "good", "best"])`` -> the strings map
  to levels ``0..4`` by index.
* ``Tags(["pii", "toxicity"])`` -> each string becomes a :class:`TagSpec`.

Explicit dataclass instances and plain ``dict`` forms are always accepted and
passed through unchanged.

``id`` and ``grounding`` are keyword-only on every question constructor, which
is why the question dataclasses provide an explicit ``__init__``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

__all__ = [
    "ChoiceOption",
    "ScaleLevel",
    "TagSpec",
    "Grounding",
    "YesNo",
    "Choice",
    "Scale",
    "Sort",
    "Tags",
    "Question",
    "OptionInput",
    "LevelInput",
    "TagInput",
]


# --------------------------------------------------------------------------- #
# Sub-objects
# --------------------------------------------------------------------------- #


@dataclass
class ChoiceOption:
    """A single selectable option for a ``choice`` question."""

    option: str
    description: Optional[str] = None


@dataclass
class ScaleLevel:
    """One rung of a ``scale`` question. ``level`` is an int in ``0..4``.

    ``description`` is optional; the server accepts a level without one.
    """

    level: int
    description: Optional[str] = None


@dataclass
class TagSpec:
    """A tag definition for a ``tags`` question.

    When ``threshold`` (a float in ``0..1``) is set, the corresponding tag
    result carries an ``applies`` flag. ``name`` is an optional human-readable
    label.
    """

    id: str
    name: Optional[str] = None
    threshold: Optional[float] = None


@dataclass
class Grounding:
    """Controls when the server augments a decision with web search.

    Thin by design: only fields you set are sent on the wire. Omit a field and
    the server applies its default (``trigger='low_confidence'``,
    ``confidence_floor=0.80``). This keeps parity with the JS SDK.
    ``extra`` keys are merged verbatim into the serialized grounding object so
    new server-side knobs work without an SDK change.
    """

    trigger: Optional[str] = None
    confidence_floor: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Shorthand normalization helpers
# --------------------------------------------------------------------------- #

OptionInput = Union[str, ChoiceOption, Dict[str, Any]]
LevelInput = Union[str, ScaleLevel, Dict[str, Any]]
TagInput = Union[str, TagSpec, Dict[str, Any]]


def _normalize_options(options: Sequence[OptionInput]) -> List[Union[ChoiceOption, Dict[str, Any]]]:
    out: List[Union[ChoiceOption, Dict[str, Any]]] = []
    for o in options:
        if isinstance(o, str):
            out.append(ChoiceOption(option=o))
        else:
            out.append(o)
    return out


def _normalize_levels(levels: Sequence[LevelInput]) -> List[Union[ScaleLevel, Dict[str, Any]]]:
    out: List[Union[ScaleLevel, Dict[str, Any]]] = []
    for i, item in enumerate(levels):
        if isinstance(item, str):
            out.append(ScaleLevel(level=i, description=item))
        else:
            out.append(item)
    return out


def _normalize_tags(tags: Sequence[TagInput]) -> List[Union[TagSpec, Dict[str, Any]]]:
    out: List[Union[TagSpec, Dict[str, Any]]] = []
    for t in tags:
        if isinstance(t, str):
            out.append(TagSpec(id=t))
        else:
            out.append(t)
    return out


# --------------------------------------------------------------------------- #
# Question dataclasses
# --------------------------------------------------------------------------- #


@dataclass(init=False)
class YesNo:
    """A binary (yes/no) decision."""

    kind = "yesno"
    instructions: str
    id: Optional[str] = None
    grounding: Optional[Grounding] = None

    def __init__(
        self,
        instructions: str,
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> None:
        self.instructions = instructions
        self.id = id
        self.grounding = grounding


@dataclass(init=False)
class Choice:
    """A single-select decision over a set of options."""

    kind = "choice"
    instructions: str
    options: List[Union[ChoiceOption, Dict[str, Any]]] = field(default_factory=list)
    id: Optional[str] = None
    grounding: Optional[Grounding] = None

    def __init__(
        self,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> None:
        self.instructions = instructions
        self.options = _normalize_options(options)
        self.id = id
        self.grounding = grounding


@dataclass(init=False)
class Scale:
    """A graded decision over exactly five levels (``0..4``)."""

    kind = "scale"
    instructions: str
    levels: List[Union[ScaleLevel, Dict[str, Any]]] = field(default_factory=list)
    id: Optional[str] = None
    grounding: Optional[Grounding] = None

    def __init__(
        self,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> None:
        self.instructions = instructions
        self.levels = _normalize_levels(levels)
        self.id = id
        self.grounding = grounding


@dataclass(init=False)
class Sort:
    """Rank the items of a list. Carries no grounding and no options."""

    kind = "sort"
    instructions: str
    id: Optional[str] = None

    def __init__(self, instructions: str, *, id: Optional[str] = None) -> None:
        self.instructions = instructions
        self.id = id


@dataclass(init=False)
class Tags:
    """Multi-label tagging. ``instructions`` is optional."""

    kind = "tags"
    tags: List[Union[TagSpec, Dict[str, Any]]] = field(default_factory=list)
    instructions: Optional[str] = None
    id: Optional[str] = None
    grounding: Optional[Grounding] = None

    def __init__(
        self,
        tags: Sequence[TagInput],
        *,
        instructions: Optional[str] = None,
        id: Optional[str] = None,
        grounding: Optional[Grounding] = None,
    ) -> None:
        self.tags = _normalize_tags(tags)
        self.instructions = instructions
        self.id = id
        self.grounding = grounding


# Union over every question type.
Question = Union[YesNo, Choice, Scale, Sort, Tags]
