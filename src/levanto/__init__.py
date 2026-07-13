"""Levanto: a thin, typed Python client for the Levanto Sage decision API.

Public surface:

* :class:`LevantoClient` / :class:`AsyncLevantoClient` -- the clients.
* Question types: :class:`YesNo`, :class:`Choice`, :class:`Scale`,
  :class:`Sort`, :class:`Tags`.
* Sub-objects: :class:`ChoiceOption`, :class:`ScaleLevel`, :class:`TagSpec`,
  :class:`Grounding`.
* Errors: :class:`LevantoError` and its subclasses.
"""

from __future__ import annotations

from ._http import __version__
from .client import AsyncLevantoClient, Group, LevantoClient
from .errors import (
    AuthError,
    LevantoAPIError,
    LevantoError,
    ServiceUnavailableError,
    ValidationError,
)
from .types import GroupResult
from .questions import (
    Choice,
    ChoiceOption,
    Grounding,
    Question,
    Scale,
    ScaleLevel,
    Sort,
    Tags,
    TagSpec,
    YesNo,
)

__all__ = [
    "__version__",
    # clients
    "LevantoClient",
    "AsyncLevantoClient",
    # batch grouping
    "Group",
    "GroupResult",
    # questions
    "YesNo",
    "Choice",
    "Scale",
    "Sort",
    "Tags",
    "Question",
    # sub-objects
    "ChoiceOption",
    "ScaleLevel",
    "TagSpec",
    "Grounding",
    # errors
    "LevantoError",
    "AuthError",
    "ValidationError",
    "ServiceUnavailableError",
    "LevantoAPIError",
]
