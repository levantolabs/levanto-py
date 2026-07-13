"""Request-serialization tests (content, ids, grounding, batch, shorthands)."""

from __future__ import annotations

import pytest

from helpers import MODES, Recorder, call, envelope, YESNO_RESULT
from levanto import (
    Choice,
    ChoiceOption,
    Grounding,
    Scale,
    ScaleLevel,
    Sort,
    TagSpec,
    Tags,
    YesNo,
)


# --------------------------------------------------------------------------- #
# Content normalization
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_string_content_sent_as_is(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    await call(mode, rec, "decide", "just a string", YesNo("ok?"))
    assert rec.body()["content"] == "just a string"


@pytest.mark.parametrize("mode", MODES)
async def test_list_content_wrapped(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    items = [{"id": "1", "content": "a"}, {"id": "2", "content": "b"}]
    await call(mode, rec, "decide", items, YesNo("ok?"))
    assert rec.body()["content"] == {"kind": "list", "value": items}


@pytest.mark.parametrize("mode", MODES)
async def test_dict_content_passes_through(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    content = {"kind": "text", "value": "hello"}
    await call(mode, rec, "decide", content, YesNo("ok?"))
    assert rec.body()["content"] == content


# --------------------------------------------------------------------------- #
# id defaulting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_single_id_defaults_to_kind(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    await call(mode, rec, "decide", "doc", YesNo("ok?"))
    assert rec.body()["question"]["id"] == "yesno"


@pytest.mark.parametrize("mode", MODES)
async def test_single_user_id_preserved(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    await call(mode, rec, "decide", "doc", YesNo("ok?", id="my-id"))
    assert rec.body()["question"]["id"] == "my-id"


@pytest.mark.parametrize("mode", MODES)
async def test_batch_ids_default_by_index(mode):
    rec = Recorder(json_body={"results": [{"answers": []}], "meta": {"request_count": 1, "question_count": 3}})
    questions = [YesNo("a"), Choice("b", ["x", "y"]), YesNo("c", id="kept")]
    await call(mode, rec, "decide", "doc", questions)
    body = rec.body()
    # single group: one content, questions nested with q0,q1,... id defaulting
    assert len(body["requests"]) == 1
    ids = [q["id"] for q in body["requests"][0]["questions"]]
    assert ids == ["q0", "q1", "kept"]


# --------------------------------------------------------------------------- #
# Grounding lifting / serialization
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_grounding_lifted_to_request_level(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    q = YesNo("ok?", grounding=Grounding(trigger="low_confidence", confidence_floor=0.80))
    await call(mode, rec, "decide", "doc", q)
    body = rec.body()
    # grounding is a top-level sibling, not nested in the question
    assert "grounding" in body
    assert "grounding" not in body["question"]
    assert body["grounding"]["trigger"] == "low_confidence"
    assert body["grounding"]["confidence_floor"] == 0.80


@pytest.mark.parametrize("mode", MODES)
async def test_grounding_is_thin_only_sends_set_fields(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    # An empty Grounding sends an empty object; the server applies its defaults.
    # (Identical behavior to the JS SDK.)
    await call(mode, rec, "decide", "doc", YesNo("ok?", grounding=Grounding()))
    assert rec.body()["grounding"] == {}


@pytest.mark.parametrize("mode", MODES)
async def test_grounding_confidence_floor_serialization(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    q = YesNo("ok?", grounding=Grounding(trigger="always", confidence_floor=0.55))
    await call(mode, rec, "decide", "doc", q)
    grounding = rec.body()["grounding"]
    assert grounding == {"trigger": "always", "confidence_floor": 0.55}
    # never the camelCase form
    assert "confidenceFloor" not in grounding


@pytest.mark.parametrize("mode", MODES)
async def test_grounding_extra_passthrough(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    g = Grounding(extra={"max_sources": 5, "allowed_domains": ["example.com"]})
    await call(mode, rec, "decide", "doc", YesNo("ok?", grounding=g))
    grounding = rec.body()["grounding"]
    assert grounding["max_sources"] == 5
    assert grounding["allowed_domains"] == ["example.com"]
    # thin: confidence_floor was not set, so it is not on the wire
    assert "confidence_floor" not in grounding


@pytest.mark.parametrize("mode", MODES)
async def test_sort_has_no_grounding_and_no_options(mode):
    rec = Recorder(json_body=envelope("sort", {"sorted": ["a"], "confidence": 0.5}))
    await call(mode, rec, "decide", ["a", "b"], Sort("rank them"))
    body = rec.body()
    assert "grounding" not in body
    question = body["question"]
    assert question["kind"] == "sort"
    assert "options" not in question
    assert "grounding" not in question
    # Sort constructor rejects a grounding kwarg entirely
    with pytest.raises(TypeError):
        Sort("rank", grounding=Grounding())  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# Batch order + same document fanned across questions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_batch_same_document_and_order(mode):
    rec = Recorder(json_body={"results": [{"answers": []}], "meta": {"request_count": 1, "question_count": 3}})
    questions = [YesNo("a"), Scale("b", ["w", "x", "y", "z", "!"]), Tags(["pii"])]
    await call(mode, rec, "decide", "shared doc", questions)
    requests = rec.body()["requests"]
    # single group: content sent once, questions preserve input order
    assert len(requests) == 1
    assert requests[0]["content"] == "shared doc"
    assert [q["kind"] for q in requests[0]["questions"]] == ["yesno", "scale", "tags"]


# --------------------------------------------------------------------------- #
# Bare-value shorthands + explicit forms
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", MODES)
async def test_choice_bare_string_shorthand(mode):
    rec = Recorder(json_body=envelope("choice", {"chosen": "approve"}))
    await call(mode, rec, "decide", "doc", Choice("pick", ["approve", "revise"]))
    options = rec.body()["question"]["options"]
    assert options == [{"option": "approve"}, {"option": "revise"}]


@pytest.mark.parametrize("mode", MODES)
async def test_choice_explicit_option_with_description(mode):
    rec = Recorder(json_body=envelope("choice", {"chosen": "a"}))
    opts = [ChoiceOption("a", "the A option"), {"option": "b", "description": "raw"}]
    await call(mode, rec, "decide", "doc", Choice("pick", opts))
    options = rec.body()["question"]["options"]
    assert options == [
        {"option": "a", "description": "the A option"},
        {"option": "b", "description": "raw"},
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_scale_bare_string_shorthand_maps_levels(mode):
    rec = Recorder(json_body=envelope("scale", {"expectation": 2.0, "confidence": 0.5}))
    labels = ["worst", "bad", "ok", "good", "best"]
    await call(mode, rec, "decide", "doc", Scale("rate", labels))
    levels = rec.body()["question"]["levels"]
    assert levels == [
        {"level": 0, "description": "worst"},
        {"level": 1, "description": "bad"},
        {"level": 2, "description": "ok"},
        {"level": 3, "description": "good"},
        {"level": 4, "description": "best"},
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_scale_explicit_levels(mode):
    rec = Recorder(json_body=envelope("scale", {"expectation": 2.0, "confidence": 0.5}))
    levels = [ScaleLevel(i, f"level {i}") for i in range(5)]
    await call(mode, rec, "decide", "doc", Scale("rate", levels))
    wire = rec.body()["question"]["levels"]
    assert wire[0] == {"level": 0, "description": "level 0"}
    assert wire[4] == {"level": 4, "description": "level 4"}


@pytest.mark.parametrize("mode", MODES)
async def test_tags_shorthand_and_threshold(mode):
    rec = Recorder(json_body=envelope("tags", {"tags": []}))
    tag_specs = ["toxicity", TagSpec("pii", threshold=0.6)]
    await call(mode, rec, "decide", "doc", Tags(tag_specs))
    question = rec.body()["question"]
    assert "instructions" not in question  # omitted when not set
    assert question["tags"] == [
        {"id": "toxicity"},
        {"id": "pii", "threshold": 0.6},
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_scale_level_without_description(mode):
    # `description` is optional; when omitted it must not appear on the wire.
    rec = Recorder(json_body=envelope("scale", {"expectation": 2.0, "confidence": 0.5}))
    levels = [ScaleLevel(i) for i in range(5)]
    await call(mode, rec, "decide", "doc", Scale("rate", levels))
    wire = rec.body()["question"]["levels"]
    assert wire[0] == {"level": 0}
    assert all("description" not in level_ for level_ in wire)


@pytest.mark.parametrize("mode", MODES)
async def test_tags_optional_name_and_instructions(mode):
    rec = Recorder(json_body=envelope("tags", {"tags": []}))
    await call(
        mode, rec, "decide", "doc",
        Tags([TagSpec("pii", name="Personal data", threshold=0.5)], instructions="label strictly"),
    )
    question = rec.body()["question"]
    assert question["instructions"] == "label strictly"
    assert question["tags"] == [{"id": "pii", "name": "Personal data", "threshold": 0.5}]
