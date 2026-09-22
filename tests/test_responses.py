"""What the SDK returns: envelopes as sent, batch answers flattened and aligned."""

from __future__ import annotations

import pytest

from levanto import Choice, Group, Scale, Sort, Tags, YesNo
from tests import samples
from tests.conftest import MODES, Recorder, assert_response, call

LEVELS = ["none", "low", "medium", "high", "severe"]


@pytest.mark.parametrize("schema, bodies", samples.SINGLES.items())
def test_samples_match_the_spec(schema, bodies):
    for body in bodies:
        assert_response(body, schema)


def test_batch_samples_match_the_spec():
    assert_response(samples.batch([samples.YESNO, "bad question"], [samples.SORT]), "BatchDecideResponsePublic")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("body", [b for bodies in samples.SINGLES.values() for b in bodies], ids=lambda b: b["id"])
async def test_decide_returns_the_envelope_unchanged(mode, body):
    env = await call(mode, Recorder((200, body)), "decide", "doc", YesNo("q"))
    assert env == body


@pytest.mark.parametrize("mode", MODES)
async def test_null_answers_come_through(mode):
    yn = await call(mode, Recorder((200, samples.YESNO_UNSURE)), "yesno", "doc", "q")
    assert yn == {"answer": None, "probability": 0.51}
    ch = await call(mode, Recorder((200, samples.CHOICE_UNSURE)), "choice", "doc", "q", ["approve", "revise"])
    assert ch["chosen"] is None and ch["probability"] is None and len(ch["probabilities"]) == 2
    tg = await call(mode, Recorder((200, samples.TAGS)), "tags", "doc", ["summary", "outline", "quiz"])
    assert [t["applies"] for t in tg["tags"]] == [True, False, None]
    so = await call(mode, Recorder((200, samples.SORT_NO_CONFIDENCE)), "sort", [{"id": "a", "content": "x"}], "q")
    assert so["confidence"] is None


@pytest.mark.parametrize("mode", MODES)
async def test_reasoning_and_usage_meta_come_through(mode):
    env = await call(mode, Recorder((200, samples.YESNO_REASONED)), "decide", "doc", YesNo("q"), reasoning="on")
    assert env["meta"]["reasoning"] == samples.REASONING_META
    env = await call(mode, Recorder((200, samples.IMAGE_YESNO)), "decide", "doc", YesNo("q"))
    assert env["meta"]["usage"]["image_count"] == 1


@pytest.mark.parametrize("mode", MODES)
async def test_batch_items_read_like_single_decides(mode):
    body = samples.batch([samples.YESNO_REASONED, samples.SCALE, samples.GROUNDED])
    items = await call(mode, Recorder((200, body)), "decide", "doc", [YesNo("a"), Scale("b", LEVELS, id="sev"), YesNo("c")])
    assert [(i["id"], i["kind"], i["ok"]) for i in items] == [("q0", "yesno", True), ("sev", "scale", True), ("q2", "yesno", True)]
    assert items[0]["result"] == samples.YESNO_REASONED["result"]
    assert items[0]["meta"]["reasoning"]["tokens"] == 312
    assert "grounding_meta" not in items[1]
    assert items[2]["grounding_meta"]["triggered"] is True


@pytest.mark.parametrize("mode", MODES)
async def test_batch_failed_answer_is_isolated(mode):
    body = samples.batch([samples.YESNO, "sort needs list content"])
    items = await call(mode, Recorder((200, body)), "decide", "doc", [YesNo("a"), Sort("b")])
    assert items[0]["ok"] is True
    assert items[1] == {"id": "q1", "kind": "sort", "ok": False, "error": "sort needs list content"}


@pytest.mark.parametrize("mode", MODES)
async def test_batch_missing_answer_is_reported_not_dropped(mode):
    body = samples.batch([samples.YESNO])
    items = await call(mode, Recorder((200, body)), "decide", "doc", [YesNo("a"), YesNo("b")])
    assert len(items) == 2
    assert items[1]["ok"] is False and "missing" in items[1]["error"]


@pytest.mark.parametrize("mode", MODES)
async def test_groups_align_to_input(mode):
    body = samples.batch([samples.YESNO], [samples.CHOICE, samples.TAGS])
    groups = [Group("doc a", [YesNo("a")]), Group("doc b", [Choice("b", ["x", "y"]), Tags(["t"], id="tg")])]
    out = await call(mode, Recorder((200, body)), "decide_groups", groups)
    assert [[(i["id"], i["kind"]) for i in g["items"]] for g in out] == [[("q0", "yesno")], [("q0", "choice"), ("tg", "tags")]]
    assert out[1]["items"][1]["result"] == samples.TAGS["result"]
