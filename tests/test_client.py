"""Client behavior tests: parsing, errors, shortcuts, ready, retry."""

from __future__ import annotations

import httpx
import pytest

import levanto._http as _http
from helpers import (
    MODES,
    META,
    CHOICE_RESULT,
    Recorder,
    SCALE_RESULT,
    SORT_RESULT_NULL,
    TAGS_RESULT,
    YESNO_RESULT,
    call,
    envelope,
    json_error,
)
from levanto import (
    AuthError,
    Choice,
    Group,
    Grounding,
    LevantoAPIError,
    LevantoError,
    Scale,
    ServiceUnavailableError,
    Sort,
    Tags,
    ValidationError,
    YesNo,
)


# --------------------------------------------------------------------------- #
# Response parsing per kind
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_decide_returns_full_envelope(mode):
    env = envelope("yesno", YESNO_RESULT)
    rec = Recorder(json_body=env)
    result = await call(mode, rec, "decide", "doc", YesNo("ok?"))
    assert result == env
    assert result["meta"] == {"model": "sage-0.5", "latency_ms": 12.3}
    assert result["result"]["answer"] == "yes"


@pytest.mark.parametrize("mode", MODES)
async def test_parse_choice(mode):
    rec = Recorder(json_body=envelope("choice", CHOICE_RESULT))
    result = await call(mode, rec, "decide", "doc", Choice("pick", ["approve", "revise"]))
    assert result["result"]["chosen"] == "approve"
    assert result["result"]["probabilities"][0] == {"option": "approve", "probability": 0.77}


@pytest.mark.parametrize("mode", MODES)
async def test_parse_scale(mode):
    rec = Recorder(json_body=envelope("scale", SCALE_RESULT))
    result = await call(mode, rec, "decide", "doc", Scale("rate", ["a", "b", "c", "d", "e"]))
    assert result["result"] == {"expectation": 3.4, "confidence": 0.6}


@pytest.mark.parametrize("mode", MODES)
async def test_parse_sort_none_confidence(mode):
    rec = Recorder(json_body=envelope("sort", SORT_RESULT_NULL))
    result = await call(mode, rec, "decide", ["a", "b", "c"], Sort("rank"))
    assert result["result"]["sorted"] == ["b", "a", "c"]
    assert result["result"]["confidence"] is None


@pytest.mark.parametrize("mode", MODES)
async def test_parse_tags_with_optional_applies(mode):
    rec = Recorder(json_body=envelope("tags", TAGS_RESULT))
    result = await call(mode, rec, "decide", "doc", Tags(["pii", "toxicity"]))
    tags = result["result"]["tags"]
    assert tags[0]["applies"] is True
    assert "applies" not in tags[1]


@pytest.mark.parametrize("mode", MODES)
async def test_grounding_meta_passthrough(mode):
    gmeta = {"triggered": True, "queries": ["q1"], "sources": ["https://a"]}
    env = envelope("yesno", YESNO_RESULT, grounding_meta=gmeta)
    rec = Recorder(json_body=env)
    result = await call(mode, rec, "decide", "doc", YesNo("ok?"))
    assert result["grounding_meta"] == gmeta


# --------------------------------------------------------------------------- #
# Batch parsing / alignment
# --------------------------------------------------------------------------- #


def _group(*answers):
    """Wrap answer dicts into one batch group ({"answers": [...]})."""
    return {"answers": list(answers)}


@pytest.mark.parametrize("mode", MODES)
async def test_batch_items_aligned_to_input(mode):
    # v0.5 batch: one document + N questions is a single group; each answer
    # nests a full single-decide envelope, which the client flattens.
    batch_body = {
        "results": [
            _group(
                {"ok": True, "result": envelope("yesno", YESNO_RESULT, id="first")},
                {"ok": False, "error": "options too few"},
            )
        ],
        "meta": {"request_count": 1, "question_count": 2},
    }
    rec = Recorder(json_body=batch_body)
    questions = [YesNo("a", id="first"), Choice("b", ["x", "y"])]
    items = await call(mode, rec, "decide", "doc", questions)

    # request shape: single group, content sent once, questions nested
    body = rec.body()
    assert len(body["requests"]) == 1
    assert body["requests"][0]["content"] == "doc"
    assert [q["id"] for q in body["requests"][0]["questions"]] == ["first", "q1"]

    assert isinstance(items, list) and len(items) == 2
    assert items[0] == {
        "id": "first",
        "kind": "yesno",
        "ok": True,
        "result": YESNO_RESULT,
        "meta": META,
    }
    assert items[1] == {"id": "q1", "kind": "choice", "ok": False, "error": "options too few"}


@pytest.mark.parametrize("mode", MODES)
async def test_batch_embeds_grounding_in_question(mode):
    rec = Recorder(json_body={"results": [_group({"ok": True, "result": envelope("yesno", YESNO_RESULT)})], "meta": {}})
    q = YesNo("a", grounding=Grounding(trigger="always", confidence_floor=0.9))
    await call(mode, rec, "decide", "doc", [q])
    wire_q = rec.body()["requests"][0]["questions"][0]
    # grounding is embedded in the question (not a top-level sibling) for batch
    assert "grounding" not in rec.body()
    assert wire_q["grounding"] == {"trigger": "always", "confidence_floor": 0.9}


@pytest.mark.parametrize("mode", MODES)
async def test_batch_surfaces_grounding_meta(mode):
    gm = {"triggered": True, "queries": ["who is the ceo"]}
    batch_body = {
        "results": [_group({"ok": True, "result": envelope("yesno", YESNO_RESULT, grounding_meta=gm)})],
        "meta": {"request_count": 1, "question_count": 1},
    }
    rec = Recorder(json_body=batch_body)
    items = await call(mode, rec, "decide", "doc", [YesNo("a")])
    assert items[0]["grounding_meta"] == gm


@pytest.mark.parametrize("mode", MODES)
async def test_single_element_list_uses_batch_endpoint(mode):
    body = {"results": [_group({"ok": True, "result": envelope("yesno", YESNO_RESULT, id="q0")})], "meta": {}}
    rec = Recorder(json_body=body)
    items = await call(mode, rec, "decide", "doc", [YesNo("a")])
    assert rec.last.url.path == "/decide/batch"
    assert items == [
        {"id": "q0", "kind": "yesno", "ok": True, "result": YESNO_RESULT, "meta": META}
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_decide_groups_multi_document(mode):
    body = {
        "results": [
            _group({"ok": True, "result": envelope("yesno", YESNO_RESULT, id="q0")}),
            _group(
                {"ok": True, "result": envelope("scale", SCALE_RESULT, id="q0")},
                {"ok": False, "error": "boom"},
            ),
        ],
        "meta": {"request_count": 2, "question_count": 3},
    }
    rec = Recorder(json_body=body)
    groups = [
        Group("doc A", [YesNo("spam?")]),
        Group("doc B", [YesNo("spam?"), Choice("pick", ["x", "y"])]),
    ]
    out = await call(mode, rec, "decide_groups", groups)

    # request shape: one group per document, content per group
    reqs = rec.body()["requests"]
    assert [r["content"] for r in reqs] == ["doc A", "doc B"]
    assert [len(r["questions"]) for r in reqs] == [1, 2]

    # response: aligned GroupResult[] with flattened items
    assert len(out) == 2
    assert out[0]["items"][0]["result"] == YESNO_RESULT
    assert len(out[1]["items"]) == 2
    assert out[1]["items"][0]["result"] == SCALE_RESULT
    assert out[1]["items"][1] == {"id": "q1", "kind": "choice", "ok": False, "error": "boom"}


# --------------------------------------------------------------------------- #
# Shortcuts return only the result payload
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_yesno_shortcut_returns_result(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    result = await call(mode, rec, "yesno", "doc", "is it fine?")
    assert result == YESNO_RESULT
    assert rec.last.url.path == "/decide"


@pytest.mark.parametrize("mode", MODES)
async def test_choice_shortcut_returns_result(mode):
    rec = Recorder(json_body=envelope("choice", CHOICE_RESULT))
    result = await call(mode, rec, "choice", "doc", "pick", ["approve", "revise"])
    assert result == CHOICE_RESULT


@pytest.mark.parametrize("mode", MODES)
async def test_scale_shortcut_returns_result(mode):
    rec = Recorder(json_body=envelope("scale", SCALE_RESULT))
    result = await call(mode, rec, "scale", "doc", "rate", ["a", "b", "c", "d", "e"])
    assert result == SCALE_RESULT


@pytest.mark.parametrize("mode", MODES)
async def test_sort_shortcut_takes_items_first(mode):
    rec = Recorder(json_body=envelope("sort", SORT_RESULT_NULL))
    result = await call(mode, rec, "sort", ["a", "b", "c"], "rank them")
    assert result == SORT_RESULT_NULL
    body = rec.body()
    assert body["content"] == {"kind": "list", "value": ["a", "b", "c"]}
    assert "grounding" not in body


@pytest.mark.parametrize("mode", MODES)
async def test_tags_shortcut_returns_result(mode):
    rec = Recorder(json_body=envelope("tags", TAGS_RESULT))
    result = await call(mode, rec, "tags", "doc", ["pii", "toxicity"])
    assert result == TAGS_RESULT


@pytest.mark.parametrize("mode", MODES)
async def test_shortcut_passes_grounding(mode):
    from levanto import Grounding

    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    await call(mode, rec, "yesno", "doc", "ok?", grounding=Grounding(confidence_floor=0.4))
    assert rec.body()["grounding"]["confidence_floor"] == 0.4


# --------------------------------------------------------------------------- #
# Error mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "status,exc",
    [
        (400, ValidationError),
        (422, ValidationError),
        (401, AuthError),
        (402, AuthError),
        (503, ServiceUnavailableError),
        (418, LevantoAPIError),
    ],
)
async def test_error_mapping(mode, status, exc):
    handler = json_error(status, f"boom-{status}")
    with pytest.raises(exc) as info:
        await call(mode, handler, "decide", "doc", YesNo("ok?"))
    err = info.value
    assert err.status == status
    assert err.detail == f"boom-{status}"
    assert f"boom-{status}" in str(err)


# --------------------------------------------------------------------------- #
# ready()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_ready_true_on_200(mode):
    def handler(request):
        assert request.url.path == "/ready"
        return httpx.Response(200, json={"status": "ok"})

    assert await call(mode, handler, "ready") is True


@pytest.mark.parametrize("mode", MODES)
async def test_ready_false_on_503(mode):
    def handler(_request):
        return httpx.Response(503, json={"detail": "loading"})

    assert await call(mode, handler, "ready") is False


@pytest.mark.parametrize("mode", MODES)
async def test_ready_does_not_retry_503(mode):
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(503)

    assert await call(mode, handler, "ready") is False
    assert calls["n"] == 1  # 503 on /ready is a valid answer, not retried


# --------------------------------------------------------------------------- #
# Retry / backoff
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_retry_on_503_then_succeeds(mode, monkeypatch):
    # No real sleeping in tests.
    monkeypatch.setattr(_http, "backoff_delay", lambda *a, **k: 0.0)
    calls = {"n": 0}
    env = envelope("yesno", YESNO_RESULT)

    def handler(_request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"detail": "cold"})
        return httpx.Response(200, json=env)

    result = await call(mode, handler, "decide", "doc", YesNo("ok?"))
    assert result == env
    assert calls["n"] == 3  # two 503s retried, third succeeds


@pytest.mark.parametrize("mode", MODES)
async def test_retry_exhausted_raises(mode, monkeypatch):
    monkeypatch.setattr(_http, "backoff_delay", lambda *a, **k: 0.0)
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(503, json={"detail": "still cold"})

    with pytest.raises(ServiceUnavailableError):
        await call(
            mode, handler, "decide", "doc", YesNo("ok?"),
            client_kwargs={"max_retries": 2},
        )
    assert calls["n"] == 3  # initial + 2 retries


@pytest.mark.parametrize("mode", MODES)
async def test_transport_error_wrapped_in_levanto_error(mode, monkeypatch):
    # A transport failure that survives retries must surface as LevantoError,
    # not a raw httpx exception (parity with the JS client).
    monkeypatch.setattr(_http, "backoff_delay", lambda *a, **k: 0.0)
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LevantoError) as excinfo:
        await call(
            mode, handler, "decide", "doc", YesNo("ok?"),
            client_kwargs={"max_retries": 2},
        )
    assert calls["n"] == 3  # initial + 2 retries
    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)


def test_backoff_delay_bounds():
    # Zero-based attempts: base*2**attempt, capped, jittered into [0, ceiling].
    for attempt in range(6):
        delay = _http.backoff_delay(attempt, base=0.5, cap=8.0)
        ceiling = min(8.0, 0.5 * (2 ** attempt))
        assert 0.0 <= delay <= ceiling
