# levanto (Python)

Thin, fully typed Python client for the Levanto Sage decision API. One client object (sync `LevantoClient` and async `AsyncLevantoClient`), five decision kinds (Yes/No, Choice, Scale, Sort, Tags), built on `httpx`.

**Docs:** [docs.levanto.ai](https://docs.levanto.ai) · Have an issue or want to leave feedback? Let us know at [team@levanto.ai](mailto:team@levanto.ai).

This README is a complete reference: every exported function and type, every default, and the behaviors that are not obvious from the signatures.

## Install

```bash
pip install levanto
```

Requires Python 3.9+. Depends on `httpx`.

## Quick start

```python
from levanto import LevantoClient, YesNo, Scale

client = LevantoClient(api_key="lv_live_...")

doc = 'Marketing email: "Risk-free, guaranteed 40% returns for accredited investors."'

# One decision -> full envelope
env = client.decide(doc, YesNo("Needs compliance review?"))
print(env["result"]["answer"])        # 'yes' | 'no'

# Shortcut -> just the result payload
r = client.yesno(doc, "Needs compliance review?")
print(r["probability"], r["confidence"], r["answer"])

# Batch: same document, many questions -> aligned list.
# Scale takes exactly 5 levels (0..4); a list of 5 strings maps to those levels by index.
severity = ["none", "low", "moderate", "high", "severe"]
items = client.decide(doc, [YesNo("Urgent?"), Scale("How severe?", severity)])
# Each item reads like a single decide, plus "ok":
if items[0]["ok"]:
    print(items[0]["result"])   # {"probability": ..., "confidence": ..., "answer": ...}
```

Async is identical, with `await` and `AsyncLevantoClient`:

```python
from levanto import AsyncLevantoClient, YesNo

async with AsyncLevantoClient(api_key="lv_live_...") as client:
    env = await client.decide("...", YesNo("Needs review?"))
```

## Exports

From `levanto`: `LevantoClient`, `AsyncLevantoClient`; the batch-grouping type `Group` and result `GroupResult`; question types `YesNo`, `Choice`, `Scale`, `Sort`, `Tags`, `Question`; sub-objects `ChoiceOption`, `ScaleLevel`, `TagSpec`, `Grounding`; errors `LevantoError`, `AuthError`, `ValidationError`, `ServiceUnavailableError`, `LevantoAPIError`; and `__version__`.
The result/envelope typed structures live in `levanto.types`: `YesNoResult`, `ChoiceProbability`, `ChoiceResult`, `ScaleResult`, `SortResult`, `TagResult`, `TagsResult`, `Result`, `Meta`, `Envelope`, `BatchItem`, `GroupResult`, `BatchResponse`, `Content`. These are `TypedDict`s: at runtime the values are plain `dict`s, so you access fields with `["key"]`.

## LevantoClient / AsyncLevantoClient

```python
LevantoClient(api_key: str, *, base_url: str = "https://sage.levanto.ai",
              timeout: float = 60.0, max_retries: int = 3, transport=None)

AsyncLevantoClient(api_key: str, *, base_url: str = "https://sage.levanto.ai",
                   timeout: float = 60.0, max_retries: int = 3, transport=None)
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `api_key` | `str` | required | Sent as `Authorization: Bearer <api_key>`. |
| `base_url` | `str` | `"https://sage.levanto.ai"` | Trailing slashes are stripped. |
| `timeout` | `float` | `60.0` | Seconds, passed to `httpx`. |
| `max_retries` | `int` | `3` | Retries on transient failures (see Behaviors). |
| `transport` | `httpx.BaseTransport` / `AsyncBaseTransport` | `None` | Transport override, mainly for tests (`httpx.MockTransport`). |

The two clients share one surface. On `AsyncLevantoClient`, every request method is a coroutine (`await`).

Lifecycle: `LevantoClient` supports `with client:` and `client.close()`; `AsyncLevantoClient` supports `async with client:` and `await client.aclose()`.

### decide

```python
decide(document, question: Question) -> Envelope
decide(document, question: Sequence[Question]) -> list[BatchItem]
```

A single question calls `POST /decide` and returns the full envelope. A list/tuple of questions calls `POST /decide/batch` as a single group (the shared document is sent once, not repeated per question) and returns a `list[BatchItem]` aligned to input order.

### decide_groups

```python
decide_groups(groups: Sequence[Group]) -> list[GroupResult]
```

Score several documents in one round-trip, each with its own questions. `Group` is a dataclass `Group(document, questions)`. Returns one `GroupResult` (`{"items": list[BatchItem]}`) per input group, in order; each group's `items` are aligned to that group's questions (same flattened shape as `decide`).

```python
from levanto import Group, YesNo, Scale

results = client.decide_groups([
    Group(post,    [YesNo("Violates policy?"), Scale("How harmful?", severity)]),
    Group(comment, [YesNo("Is this spam?")]),
])
results[0]["items"][0]["result"]   # yes/no payload for the post
```

### Shortcuts

Each shortcut builds the matching question, makes one single (non-batch) decision, and returns just the `result` payload.

```python
yesno (document, instructions: str, *, id=None, grounding=None) -> YesNoResult
choice(document, instructions: str, options, *, id=None, grounding=None) -> ChoiceResult
scale (document, instructions: str, levels, *, id=None, grounding=None) -> ScaleResult
sort  (items, instructions: str, *, id=None) -> SortResult
tags  (document, tags, *, id=None, grounding=None, instructions=None) -> TagsResult
```

`sort` takes the list to order as its first argument. `id` and `grounding` are keyword-only.

### ready

```python
ready() -> bool
```

Calls `GET /ready` with no `Authorization` header. Returns `True` on HTTP 200, `False` otherwise (503 means still loading). Never retried.

## Question types

One dataclass per kind. `id` and `grounding` are keyword-only on every constructor. The lowercase client methods (`client.yesno`) never collide with the constructors (`YesNo`).

```python
YesNo (instructions: str, *, id: str | None = None, grounding: Grounding | None = None)   # kind: "yesno"
Choice(instructions: str, options, *, id=None, grounding=None)                             # kind: "choice"
Scale (instructions: str, levels, *, id=None, grounding=None)                              # kind: "scale"
Sort  (instructions: str, *, id: str | None = None)                                        # kind: "sort"  (no grounding)
Tags  (tags, *, instructions=None, id=None, grounding=None)                                # kind: "tags"  (instructions optional)
```

Input types for the collection args:

```python
OptionInput = Union[str, ChoiceOption, dict]     # Choice.options
LevelInput  = Union[str, ScaleLevel, dict]       # Scale.levels
TagInput    = Union[str, TagSpec, dict]          # Tags.tags
```

Shorthands applied at construction:
- `Choice(instr, ["approve", "revise"])`: each bare string becomes `ChoiceOption(option=...)`.
- `Scale(instr, ["worst", "bad", "ok", "good", "best"])`: the 5 strings map to levels `0..4` by index.
- `Tags(["pii", "toxicity"])`: each bare string becomes `TagSpec(id=...)`.

Explicit dataclass instances and plain `dict`s are always accepted and passed through unchanged. Passing `grounding=` to `Sort` raises `TypeError`.

Per-kind fields:

| Field | yesno | choice | scale | sort | tags |
|---|:--:|:--:|:--:|:--:|:--:|
| `instructions` | required | required | required | required | optional |
| `options` / `levels` / `tags` | - | `options` req | `levels` req | - | `tags` req |
| `id` | opt | opt | opt | opt | opt |
| `grounding` | opt | opt | opt | no | opt |

## Sub-objects

```python
@dataclass
class ChoiceOption: option: str; description: Optional[str] = None

@dataclass
class ScaleLevel:   level: int; description: Optional[str] = None   # exactly 5 rungs, level in 0..4; description optional

@dataclass
class TagSpec:      id: str; name: Optional[str] = None; threshold: Optional[float] = None   # name optional; threshold 0..1, when set the result carries `applies`

@dataclass
class Grounding:
    trigger: Optional[str] = None            # serialized as-is
    confidence_floor: Optional[float] = None
    extra: Optional[dict] = None             # merged verbatim into the wire object
```

## Documents

`document` accepts `Content = Union[str, dict, list]`. Normalization: a bare `str` is sent as-is (the API treats it as text); a `list` is wrapped as `{"kind": "list", "value": items}`; an explicit `dict` (e.g. `{"kind": "text", "value": ...}` or `{"kind": "list", "value": [...]}`) passes through. Sort takes a list of `{"id", "content"}` items; the other kinds take text.

## Grounding

Attach a `Grounding` to any non-`sort` question (or pass it to a shortcut) to let the server augment low-confidence decisions with web search. On the wire, grounding is lifted from the question to a top-level `grounding` sibling of `content`/`question`.

Grounding is thin: only the fields you set are sent, and the server applies its defaults for anything omitted. `trigger` and `confidence_floor` are first-class fields; the remaining server knobs go through `extra`, merged verbatim.

Full grounding config (wire field, SDK access, default, range):

| Wire field | SDK | Default | Range |
|---|---|---|---|
| `trigger` | `trigger` | `"low_confidence"` | `"never"` \| `"low_confidence"` \| `"always"` |
| `confidence_floor` | `confidence_floor` | `0.80` | `0.0 .. 1.0` |
| `max_results` | `extra={"max_results": ...}` | `10` | `1 .. 20` |
| `max_context_tokens` | `extra={"max_context_tokens": ...}` | `2000` | `1 .. 8000` |
| `return_sources` | `extra={"return_sources": ...}` | `True` | bool |

```python
YesNo(
    "Is Acme currently bankrupt?",
    grounding=Grounding(trigger="low_confidence", confidence_floor=0.85,
                        extra={"max_results": 8, "return_sources": True}),
)
```

The floor is a confidence threshold, interpreted per kind: for yesno/scale/choice, search fires when the decision `confidence` is below it (yesno confidence is decisiveness `2·|p−0.5|`); for tags it is weakest-link (search fires if any tag's confidence is below the floor). This is distinct from `TagSpec.threshold`, which controls a tag's `applies` flag. When grounding runs, the envelope includes a `grounding_meta` block (`triggered`, `trigger_reason?`, `queries?`, `sources?`, `added_context_tokens?`, `search_ms?`).

## Return types (`levanto.types`)

```python
class YesNoResult(TypedDict):   probability: float; confidence: float; answer: Literal["yes", "no"]
class ChoiceProbability(TypedDict): option: str; probability: float
class ChoiceResult(TypedDict):  chosen: str; confidence: float; probabilities: list[ChoiceProbability]
class ScaleResult(TypedDict):   expectation: float; confidence: float
class SortResult(TypedDict):    sorted: list[str]; confidence: Optional[float]   # nullable per the API; never assume a number
class TagResult(TypedDict):     id: str; probability: float; confidence: float; applies: Optional[bool]  # (applies optional; bool when the tag had a threshold, else None)
class TagsResult(TypedDict):    tags: list[TagResult]

class Meta(TypedDict):          model: str; latency_ms: float
class Envelope(TypedDict):      id: str; kind: str; result: Result; meta: Meta; grounding_meta: dict  # (grounding_meta optional)
class BatchItem(TypedDict):     id: str; kind: str; ok: bool; result: Result; meta: Meta; grounding_meta: dict; error: str  # (result/meta/grounding_meta present on ok; error on failure)
class GroupResult(TypedDict):   items: list[BatchItem]   # one per decide_groups() input group, in order; items aligned to that group's questions

Result = Union[YesNoResult, ChoiceResult, ScaleResult, SortResult, TagsResult]
```

`answer` is the raw API string `"yes"` / `"no"`, not a bool. `SortResult["confidence"]` is typed nullable by the API, so never assume it is a number. `TagResult["applies"]` is a bool when that tag was created with a `threshold`, otherwise `None`.

## Errors

```python
class LevantoError(Exception):
    def __init__(self, message: str, *, status: int | None = None, detail: str | None = None): ...
    # attributes: .status, .detail

class AuthError(LevantoError): ...               # 401, 402
class ValidationError(LevantoError): ...         # 400, 422
class ServiceUnavailableError(LevantoError): ... # 503
class LevantoAPIError(LevantoError): ...         # any other non-2xx
```

Every API error carries the HTTP `status` and the server `detail` string.

## Behaviors

- **id defaulting**: if a question has no `id`, the SDK fills one. A single call defaults to the kind string (e.g. `"yesno"`); a batch assigns `q0, q1, ...` by index. A supplied `id` is kept.
- **Batch**: `decide(doc, questions)` sends one group (shared content once); `decide_groups` sends several. `BatchItem`s come back in question order, with `id`/`kind` from each request's question. On the wire the server nests a full single-decide envelope under each answer's `result`; the client flattens it so a successful item reads exactly like a single decide (`item["result"]` is the bare payload, with `item["meta"]` and, when grounding ran, `item["grounding_meta"]` alongside it). A failed item carries `error` instead.
- **Batch error modes**: a schema-invalid question (e.g. wrong scale level count) rejects the *whole* batch with a `ValidationError`. A question that is well-formed but incompatible with its group's shared content (e.g. a `sort` question over text content) is isolated: that item comes back `ok=False` with an `error`, while the others succeed.
- **Retries**: transport errors and HTTP `429, 500, 502, 503, 504` are retried up to `max_retries`, with exponential backoff plus full jitter (base 0.5s, capped at 8s). `ready()` is never retried.
- **Sync and async parity**: both clients share the same request-building, serialization, parsing, error-mapping, and retry policy; only the transport call and the sleep differ.

## Limits (enforced server-side, surfaced as `ValidationError`)

- choice: 2..120 options
- scale: exactly 5 levels, values `0..4`
- sort: 2..120 items
- tags: 1..120 tags; `threshold` in `0..1`
- The full rendered request must fit within roughly 32K tokens.

## License

MIT
