# levanto

Python client for the [Levanto Sage](https://docs.levanto.ai) decision API (v1.1). Sync and async, fully typed, one dependency (`httpx`).

```bash
pip install levanto
```

Requires Python 3.10+.

## Quick start

```python
from levanto import LevantoClient

client = LevantoClient()  # reads LEVANTO_API_KEY, or pass api_key="lv_live_..."

r = client.yesno("Marketing email: 'Guaranteed 40% returns, risk-free.'", "Needs compliance review?")

if r["answer"] is None:        # Sage isn't sure
    send_to_human()
elif r["answer"] == "yes":
    send_to_compliance()
```

Results are plain dicts, exactly as the API returns them. `None` answers are real answers ("not sure"), not errors: route them to a person.

## Decision kinds

| Shortcut | Returns |
|---|---|
| `client.yesno(doc, instructions)` | `{"answer": "yes" \| "no" \| None, "probability"}` (P(yes)) |
| `client.choice(doc, instructions, ["a", "b"])` | `{"chosen": str \| None, "probability": float \| None, "probabilities": [{"option", "probability"}]}` |
| `client.scale(doc, instructions, [5 level descriptions])` | `{"expectation": 0..4, "confidence"}` |
| `client.sort([{"id", "content"}, ...], instructions)` | `{"sorted": [ids], "confidence": float \| None}` |
| `client.tags(doc, ["spam", TagSpec("scam", "scam: fraud or phishing")], instructions=...)` | `{"tags": [{"id", "probability", "applies": bool \| None}]}` |

Every shortcut also takes `id=`, `reasoning=`, and (except `sort`) `grounding=`.

For the full response (`id`, `kind`, `result`, `meta`, `grounding_meta`), use `decide` with a question object:

```python
from levanto import YesNo, Choice, Scale, Sort, Tags, ChoiceOption, TagSpec

env = client.decide(doc, Choice("How should legal handle this?", [
    ChoiceOption("approve", "Standard terms, no red flags"),
    ChoiceOption("escalate", "Unusual or high-risk terms"),
]))
env["result"]["chosen"], env["meta"]["latency_ms"]
```

## Batch

A list of questions about one document is a single call; the document is sent once. You get one item per question, in order:

```python
items = client.decide(doc, [YesNo("Violates policy?"), Scale("How harmful?", levels)])
for item in items:
    print(item["result"] if item["ok"] else item["error"])
```

Several documents in one call:

```python
from levanto import Group

groups = client.decide_groups([Group(post, [YesNo("Spam?")]), Group(comment, [YesNo("Spam?"), Tags(["abuse"])])])
groups[1]["items"][0]["result"]
```

A question that fails comes back with `ok=False` and `error`; the others still succeed. Unset ids default to `q0, q1, ...`.

Both return a list with a `.meta` attribute: usage and latency for the whole call (`items.meta["usage"]`). They are reported there, not per item.

## Reasoning

Sage v1.1 can think a hard question through before answering. `"auto"` (the server default) reasons only when the question needs it; `"off"` never does; `"on"` always does. Reasoning is not billed.

```python
client = LevantoClient(reasoning="off")                    # default for every call
client.decide(doc, YesNo("Refund allowed?"), reasoning="on")  # override one call
env["meta"]["reasoning"]  # {"fired", "ran", "finished", "tokens", "margin", "limited"}
```

A reasoning pass has a 6 s budget; keep `timeout` above that (the default is 60 s).

## Images (beta)

Yes/No, Choice (at most 20 options), Scale, and Tags accept an image. PNG, JPEG, or WebP, up to 4 MiB:

```python
from levanto import Image

client.yesno(Image.from_path("screenshot.png", text="Ticket: checkout button missing"),
             "Does the screenshot show the reported problem?")
```

`Image.from_bytes(data)` works too. Images can't be used with `sort`, inside list items, or with grounding.

## Grounding

Optional web search before deciding, for recency- or fact-heavy questions:

```python
from levanto import Grounding

client.yesno(doc, "Is Acme currently bankrupt?", grounding=Grounding(trigger="low_confidence", confidence_floor=0.8))
```

Fields: `trigger` (`"never"`, `"low_confidence"`, `"always"`), `confidence_floor`, `max_results`, `max_context_tokens`, `return_sources`. Unset fields use the server defaults. When grounding was requested, the response has `grounding_meta`.

## Async

`AsyncLevantoClient` has the same methods, awaited:

```python
from levanto import AsyncLevantoClient

async with AsyncLevantoClient() as client:
    r = await client.yesno(doc, "Needs review?")
```

## Client options

```python
LevantoClient(api_key=None, *, base_url="https://sage.levanto.ai", timeout=60.0, max_retries=3, reasoning=None, transport=None)
```

Use it as a context manager, or call `close()` (`aclose()` for async). `client.ready()` returns `True` when Sage is serving.

## Errors

All errors are `LevantoError`, with `.status` and the server's `.detail`.

| Error | When |
|---|---|
| `ValidationError` | 400/422: invalid request or a [limit](https://docs.levanto.ai/decision-model/limits) broken |
| `AuthError` | 401: missing or invalid API key |
| `AllowanceExhaustedError` | 402: this period's decisions are used up (subclass of `AuthError`) |
| `ServiceUnavailableError` | 503 after retries |
| `LevantoAPIError` | any other status |
| `LevantoError` | network failure or timeout (`.status` is `None`) |

Network errors and 429/500/502/503/504 are retried up to `max_retries` times with exponential backoff (honouring `Retry-After`). Timeouts are not retried, so a slow call is never billed twice.

## Upgrading from 0.1

- Yes/No and Choice no longer return `confidence`. Route on `answer` / `chosen` (`None` means not sure), or on `probability`.
- `answer`, `chosen`, and a tag's `applies` can be `None`.
- `TagSpec` takes `id` and `name`; `threshold` is gone (the API ignores it). `applies` is Sage's own verdict.
- `Grounding(extra=...)` is replaced by explicit fields.
- New: `reasoning`, `Image`, `AllowanceExhaustedError`, full `meta` (`usage`, `reasoning`). Python 3.10+.

## Development

```bash
uv run --extra test pytest                                        # unit + contract tests (no network)
LEVANTO_API_KEY=lv_live_... uv run --extra test pytest -m live    # live tests (about 15 decisions)
```

Requests and responses are validated against the API spec in `tests/data/openapi.json`; the live suite also fails if the published spec changes.

## License

MIT
