"""Questions, their sub-objects, grounding, and image content.

One class per decision kind: :class:`YesNo`, :class:`Choice`, :class:`Scale`,
:class:`Sort`, :class:`Tags`. Bare strings are accepted as shorthands:

* ``Choice(instr, ["approve", "revise"])``: each string is an option.
* ``Scale(instr, ["none", "low", "medium", "high", "severe"])``: five strings
  become levels ``0..4`` in order.
* ``Tags(["spam", "promotion"])``: each string is a tag id.

Explicit sub-objects and plain ``dict`` forms pass through unchanged.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Sequence, Union

__all__ = [
    "ChoiceOption",
    "ScaleLevel",
    "TagSpec",
    "Grounding",
    "Image",
    "YesNo",
    "Choice",
    "Scale",
    "Sort",
    "Tags",
    "Question",
]

Trigger = Literal["never", "low_confidence", "always"]


@dataclass(frozen=True)
class ChoiceOption:
    """One option of a :class:`Choice`. ``description`` says when it applies."""

    option: str
    description: str | None = None


@dataclass(frozen=True)
class ScaleLevel:
    """One level of a :class:`Scale`: ``level`` is ``0..4``."""

    level: int
    description: str | None = None


@dataclass(frozen=True)
class TagSpec:
    """One tag of a :class:`Tags` question.

    ``name`` is what Sage reads (``"<id>: <what it is, and is not>"`` works
    best); you get ``id`` back. Without a ``name``, Sage reads the ``id``.
    """

    id: str
    name: str | None = None


@dataclass(frozen=True)
class Grounding:
    """Optional web search before deciding. Unset fields use the server defaults."""

    trigger: Trigger | None = None  # server default: "low_confidence"
    confidence_floor: float | None = None  # 0..1, default 0.80
    max_results: int | None = None  # 1..20, default 10
    max_context_tokens: int | None = None  # 1..8000, default 2000
    return_sources: bool | None = None  # default True

    def to_wire(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")


def _sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class Image:
    """Image content (beta) for Yes/No, Choice, Scale, and Tags.

    ``media`` is a base64 ``data:`` URI (PNG, JPEG, or WebP). ``text`` is
    optional context judged together with the image. Build one from a file or
    bytes with :meth:`from_path` / :meth:`from_bytes`.
    """

    media: str
    text: str | None = None

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str | None = None, *, text: str | None = None) -> "Image":
        mime = mime_type or _sniff_image_type(data)
        if mime not in _IMAGE_TYPES:
            raise ValueError(f"image must be PNG, JPEG, or WebP; got {mime or 'an unknown format'}")
        return cls(f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", text)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str], *, text: str | None = None) -> "Image":
        with open(path, "rb") as f:
            data = f.read()
        guessed = mimetypes.guess_type(os.fspath(path))[0]
        return cls.from_bytes(data, _sniff_image_type(data) or guessed, text=text)

    def to_wire(self) -> Dict[str, Any]:
        wire: Dict[str, Any] = {"kind": "image", "media": self.media}
        if self.text is not None:
            wire["text"] = self.text
        return wire


OptionInput = Union[str, ChoiceOption, Dict[str, Any]]
LevelInput = Union[str, ScaleLevel, Dict[str, Any]]
TagInput = Union[str, TagSpec, Dict[str, Any]]


def _option(o: OptionInput) -> Dict[str, Any]:
    if isinstance(o, str):
        return {"option": o}
    if isinstance(o, ChoiceOption):
        return {"option": o.option, **({"description": o.description} if o.description is not None else {})}
    return dict(o)


def _level(i: int, lv: LevelInput) -> Dict[str, Any]:
    if isinstance(lv, str):
        return {"level": i, "description": lv}
    if isinstance(lv, ScaleLevel):
        return {"level": lv.level, **({"description": lv.description} if lv.description is not None else {})}
    return dict(lv)


def _tag(t: TagInput) -> Dict[str, Any]:
    if isinstance(t, str):
        return {"id": t}
    if isinstance(t, TagSpec):
        return {"id": t.id, **({"name": t.name} if t.name is not None else {})}
    return dict(t)


class _Question:
    kind: str
    id: str | None
    grounding: Grounding | None = None

    def _fields(self) -> Dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def to_wire(self, default_id: str) -> Dict[str, Any]:
        """The wire ``question`` object, without grounding."""
        return {"id": self.id if self.id is not None else default_id, "kind": self.kind, **self._fields()}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.to_wire(self.id or self.kind)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Question) or type(other) is not type(self):
            return NotImplemented
        return self.to_wire("") == other.to_wire("") and self.grounding == other.grounding

    __hash__ = None  # type: ignore[assignment]  # mutable, so unhashable


class YesNo(_Question):
    """Yes/No: ``answer`` is ``"yes"``, ``"no"``, or ``None`` when Sage isn't sure."""

    kind = "yesno"

    def __init__(self, instructions: str, *, id: str | None = None, grounding: Grounding | None = None) -> None:
        self.instructions, self.id, self.grounding = instructions, id, grounding

    def _fields(self) -> Dict[str, Any]:
        return {"instructions": self.instructions}


class Choice(_Question):
    """Pick one of 2-120 options (at most 20 with image content)."""

    kind = "choice"

    def __init__(
        self,
        instructions: str,
        options: Sequence[OptionInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
    ) -> None:
        self.instructions, self.id, self.grounding = instructions, id, grounding
        self.options: List[Dict[str, Any]] = [_option(o) for o in options]

    def _fields(self) -> Dict[str, Any]:
        return {"instructions": self.instructions, "options": self.options}


class Scale(_Question):
    """Score against exactly five levels, ``0..4``."""

    kind = "scale"

    def __init__(
        self,
        instructions: str,
        levels: Sequence[LevelInput],
        *,
        id: str | None = None,
        grounding: Grounding | None = None,
    ) -> None:
        self.instructions, self.id, self.grounding = instructions, id, grounding
        self.levels: List[Dict[str, Any]] = [_level(i, lv) for i, lv in enumerate(levels)]

    def _fields(self) -> Dict[str, Any]:
        return {"instructions": self.instructions, "levels": self.levels}


class Sort(_Question):
    """Rank a list of 2-120 ``{"id", "content"}`` items. No grounding, no images."""

    kind = "sort"

    def __init__(self, instructions: str, *, id: str | None = None) -> None:
        self.instructions, self.id = instructions, id

    def _fields(self) -> Dict[str, Any]:
        return {"instructions": self.instructions}


class Tags(_Question):
    """Decide which of 1-120 tags apply. ``instructions`` is the rule for when a tag applies."""

    kind = "tags"

    def __init__(
        self,
        tags: Sequence[TagInput],
        *,
        instructions: str | None = None,
        id: str | None = None,
        grounding: Grounding | None = None,
    ) -> None:
        self.instructions, self.id, self.grounding = instructions, id, grounding
        self.tags: List[Dict[str, Any]] = [_tag(t) for t in tags]

    def _fields(self) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"tags": self.tags}
        if self.instructions is not None:
            fields["instructions"] = self.instructions
        return fields


Question = Union[YesNo, Choice, Scale, Sort, Tags]
