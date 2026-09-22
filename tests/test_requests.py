"""What the SDK sends: every body is checked against the v1.1 spec (closed-world)."""

from __future__ import annotations

import base64

import pytest

from levanto import (
    Choice,
    ChoiceOption,
    Grounding,
    Group,
    Image,
    Scale,
    ScaleLevel,
    Sort,
    Tags,
    TagSpec,
    YesNo,
)
from levanto._core import build_batch_body, build_single_body
from tests import samples
from tests.conftest import MODES, Recorder, assert_request, call

LEVELS = ["none", "low", "medium", "high", "severe"]
ITEMS = [{"id": "a", "content": "first"}, {"id": "b", "content": "second"}]


# --- every kind, single and batch, is valid against the spec ---------------

QUESTIONS = [
    YesNo("Needs review?"),
    YesNo("Needs review?", id="needs_review", grounding=Grounding(trigger="always")),
    Choice("Route?", ["billing", "support"]),
    Choice("Route?", [ChoiceOption("billing", "Invoices"), {"option": "support", "description": "Bugs"}]),
    Scale("How urgent?", LEVELS),
    Scale("How urgent?", [ScaleLevel(i, d) for i, d in enumerate(LEVELS)]),
    Scale("How urgent?", [ScaleLevel(i) for i in range(5)]),
    Tags(["spam", TagSpec("scam", "scam: fraud or phishing"), {"id": "safe"}]),
    Tags(["spam"], instructions="Tag only what the post is.", grounding=Grounding(confidence_floor=0.9)),
]


@pytest.mark.parametrize("question", QUESTIONS, ids=repr)
@pytest.mark.parametrize("reasoning", [None, "auto", "off", "on"])
def test_single_body_matches_spec(question, reasoning):
    assert_request(build_single_body("some text", question, reasoning), "DecideRequestPublic")


def test_sort_single_body_matches_spec():
    assert_request(build_single_body(ITEMS, Sort("Most urgent first"), "off"), "DecideRequestPublic")


@pytest.mark.parametrize("reasoning", [None, "on"])
def test_batch_body_matches_spec(reasoning):
    body = build_batch_body([("text", QUESTIONS), (ITEMS, [Sort("Rank")])], reasoning)
    assert_request(body, "BatchDecideRequestPublic")


# --- exact wire shapes ------------------------------------------------------


def test_single_body_shape():
    q = YesNo("Needs review?", grounding=Grounding(trigger="low_confidence", confidence_floor=0.85, max_results=5))
    assert build_single_body("doc", q, None) == {
        "content": "doc",
        "question": {"id": "yesno", "kind": "yesno", "instructions": "Needs review?"},
        "grounding": {"trigger": "low_confidence", "confidence_floor": 0.85, "max_results": 5},
    }


def test_single_id_defaults_to_kind_and_keeps_explicit_id():
    assert build_single_body("d", Scale("x", LEVELS), None)["question"]["id"] == "scale"
    assert build_single_body("d", Scale("x", LEVELS, id="sev"), None)["question"]["id"] == "sev"


def test_shorthands():
    assert Choice("x", ["a", "b"]).options == [{"option": "a"}, {"option": "b"}]
    assert Scale("x", LEVELS).levels == [{"level": i, "description": d} for i, d in enumerate(LEVELS)]
    assert Tags(["a", TagSpec("b", "b: bee")]).tags == [{"id": "a"}, {"id": "b", "name": "b: bee"}]


def test_tags_instructions_only_when_set():
    assert "instructions" not in Tags(["a"]).to_wire("t")
    assert Tags(["a"], instructions="rule").to_wire("t")["instructions"] == "rule"


def test_tagspec_has_no_threshold():
    with pytest.raises(TypeError):
        TagSpec("a", threshold=0.5)  # type: ignore[call-arg]


def test_sort_takes_no_grounding():
    with pytest.raises(TypeError):
        Sort("x", grounding=Grounding())  # type: ignore[call-arg]


def test_grounding_sends_only_set_fields():
    assert Grounding().to_wire() == {}
    assert Grounding(return_sources=False, max_context_tokens=500).to_wire() == {
        "max_context_tokens": 500,
        "return_sources": False,
    }


def test_reasoning_is_omitted_unless_set():
    assert "reasoning" not in build_single_body("d", YesNo("q"), None)
    assert build_single_body("d", YesNo("q"), "off")["reasoning"] == "off"
    assert build_batch_body([("d", [YesNo("q")])], "on")["reasoning"] == "on"
    assert "reasoning" not in build_batch_body([("d", [YesNo("q")])], None)


def test_batch_shape_grounding_inside_questions_and_ids():
    body = build_batch_body(
        [("doc", [YesNo("a?", grounding=Grounding(trigger="always")), Scale("b?", LEVELS, id="sev")])], None
    )
    assert body == {
        "requests": [
            {
                "content": "doc",
                "questions": [
                    {"id": "q0", "kind": "yesno", "instructions": "a?", "grounding": {"trigger": "always"}},
                    {"id": "sev", "kind": "scale", "instructions": "b?", "levels": Scale("b?", LEVELS).levels},
                ],
            }
        ]
    }
    assert "latency_mode" not in body


def test_empty_batch_group_is_rejected_before_sending():
    with pytest.raises(ValueError):
        build_batch_body([("doc", [])], None)


# --- content ----------------------------------------------------------------


def test_list_content_is_wrapped():
    assert build_single_body(ITEMS, Sort("x"), None)["content"] == {"kind": "list", "value": ITEMS}


def test_dict_content_passes_through():
    content = {"kind": "text", "value": "hello"}
    assert build_single_body(content, YesNo("x"), None)["content"] is content


def test_bad_content_type():
    with pytest.raises(TypeError):
        build_single_body(42, YesNo("x"), None)  # type: ignore[arg-type]


def test_image_from_bytes_sniffs_type_and_matches_spec():
    img = Image.from_bytes(samples.PNG_BLUE, text="Ticket: button missing")
    assert img.media == "data:image/png;base64," + base64.b64encode(samples.PNG_BLUE).decode()
    body = build_single_body(img, YesNo("Shows the bug?"), None)
    assert body["content"] == {"kind": "image", "media": img.media, "text": "Ticket: button missing"}
    assert_request(body, "DecideRequestPublic")


@pytest.mark.parametrize(
    "data, mime",
    [(b"\xff\xd8\xff\xe0rest", "image/jpeg"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp")],
)
def test_image_sniffs_jpeg_and_webp(data, mime):
    assert Image.from_bytes(data).media.startswith(f"data:{mime};base64,")


def test_image_rejects_unsupported_formats():
    with pytest.raises(ValueError):
        Image.from_bytes(b"GIF89a....")
    with pytest.raises(ValueError):
        Image.from_bytes(samples.PNG_BLUE, "image/gif")


def test_image_from_path(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(samples.PNG_BLUE)
    assert Image.from_path(path) == Image.from_bytes(samples.PNG_BLUE)
    assert "text" not in Image.from_path(path).to_wire()


def test_image_in_batch_group_matches_spec():
    body = build_batch_body([(Image.from_bytes(samples.PNG_BLUE), [YesNo("Bug?"), Tags(["ui", "crash"])])], None)
    assert_request(body, "BatchDecideRequestPublic")


# --- the client sends what the builders build -------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_client_posts_single_to_decide(mode):
    rec = Recorder((200, samples.YESNO))
    await call(mode, rec, "decide", "doc", YesNo("Needs review?"))
    request = rec.requests[0]
    assert (request.method, request.url.path) == ("POST", "/decide")
    assert request.headers["authorization"] == "Bearer lv_test_key"
    assert request.headers["user-agent"].startswith("levanto-python/1.1.0")
    assert rec.body == build_single_body("doc", YesNo("Needs review?"), None)


@pytest.mark.parametrize("mode", MODES)
async def test_client_reasoning_default_and_override(mode):
    rec = Recorder((200, samples.YESNO))
    await call(mode, rec, "decide", "doc", YesNo("q"), client={"reasoning": "off"})
    assert rec.body["reasoning"] == "off"
    await call(mode, rec, "decide", "doc", YesNo("q"), client={"reasoning": "off"}, reasoning="on")
    assert rec.body["reasoning"] == "on"
    await call(mode, rec, "decide", "doc", YesNo("q"), client={"reasoning": "off"}, reasoning=None)
    assert "reasoning" not in rec.body
    await call(mode, rec, "yesno", "doc", "q", reasoning="on")
    assert rec.body["reasoning"] == "on"


@pytest.mark.parametrize("mode", MODES)
async def test_client_batch_and_groups(mode):
    rec = Recorder((200, samples.batch([samples.YESNO, samples.SCALE])))
    await call(mode, rec, "decide", "doc", [YesNo("a"), Scale("b", LEVELS)], reasoning="off")
    assert rec.requests[0].url.path == "/decide/batch"
    assert rec.body == build_batch_body([("doc", [YesNo("a"), Scale("b", LEVELS)])], "off")

    rec = Recorder((200, samples.batch([samples.YESNO], [samples.SORT])))
    await call(mode, rec, "decide_groups", [Group("doc", [YesNo("a")]), Group(ITEMS, [Sort("rank")])])
    assert rec.body == build_batch_body([("doc", [YesNo("a")]), (ITEMS, [Sort("rank")])], None)
    assert_request(rec.body, "BatchDecideRequestPublic")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "method, args, kwargs, question",
    [
        ("yesno", ("q",), {"id": "x"}, YesNo("q", id="x")),
        ("choice", ("q", ["a", "b"]), {}, Choice("q", ["a", "b"])),
        ("scale", ("q", LEVELS), {"grounding": Grounding(trigger="never")}, Scale("q", LEVELS, grounding=Grounding(trigger="never"))),
        ("sort", ("q",), {}, Sort("q")),
        ("tags", (["a"],), {"instructions": "rule"}, Tags(["a"], instructions="rule")),
    ],
)
async def test_shortcuts_send_the_matching_question(mode, method, args, kwargs, question):
    rec = Recorder((200, samples.YESNO))
    document = ITEMS if method == "sort" else "doc"
    await call(mode, rec, method, document, *args, **kwargs)
    assert rec.body == build_single_body(document, question, None)


# --- the contract check itself must be able to fail -------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"content": "x", "question": {"id": "a", "kind": "yesno", "instructions": "q", "confidence": 1}},
        {"content": "x", "question": {"id": "a", "kind": "scale", "instructions": "q", "levels": [{"level": 0}] * 4}},
        {"content": "x", "question": {"id": "a", "kind": "yesno", "instructions": "q"}, "reasoning": "maybe"},
        {"content": {"kind": "image", "url": "https://x/y.png"}, "question": {"id": "a", "kind": "yesno", "instructions": "q"}},
        {"question": {"id": "a", "kind": "yesno", "instructions": "q"}},
    ],
)
def test_contract_check_rejects_invalid_bodies(body):
    with pytest.raises(AssertionError):
        assert_request(body, "DecideRequestPublic")
