"""Live tests against the real Sage API. Opt-in: ``LEVANTO_API_KEY=lv_live_... pytest -m live``.

Every raw response is validated against the spec, and the SDK's view of it is
checked too. About 15 decisions per run (reasoning is not billed).
"""

from __future__ import annotations

import json
import os
from typing import Any, List

import httpx
import pytest

from levanto import (
    AuthError,
    Choice,
    Group,
    Image,
    LevantoClient,
    Scale,
    Sort,
    Tags,
    TagSpec,
    ValidationError,
    YesNo,
)
from tests import samples
from tests.conftest import SPEC, assert_response

pytestmark = pytest.mark.live
KEY = os.environ.get("LEVANTO_API_KEY")
BASE_URL = os.environ.get("LEVANTO_BASE_URL", "https://sage.levanto.ai")
needs_key = pytest.mark.skipif(not KEY, reason="set LEVANTO_API_KEY to run live tests")

LEVELS = ["no urgency", "low", "medium", "high", "critical: drop everything"]
TICKET = "Checkout returns a 500 for about 10% of EU customers since the deploy 20 minutes ago. Revenue-impacting."
INCIDENTS = [
    {"id": "typo", "content": "Spelling mistake on the FAQ page."},
    {"id": "db_down", "content": "Primary production database is unreachable."},
    {"id": "pricing", "content": "Prospect asking about Enterprise pricing."},
]


class Capture(httpx.BaseTransport):
    """Real transport that keeps every response body, to validate the raw wire format."""

    def __init__(self) -> None:
        self.inner = httpx.HTTPTransport()
        self.bodies: List[Any] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.inner.handle_request(request)
        response.read()
        self.bodies.append(json.loads(response.content) if response.content else None)
        return response


@pytest.fixture
def live():
    capture = Capture()
    with LevantoClient(KEY, base_url=BASE_URL, transport=capture, timeout=90) as client:
        yield client, capture


def test_spec_has_not_drifted():
    live_spec = httpx.get(f"{BASE_URL}/openapi.json", timeout=30).json()
    assert live_spec["info"]["version"] == SPEC["info"]["version"]
    assert live_spec["components"]["schemas"] == SPEC["components"]["schemas"], (
        "The live API spec changed: update tests/data/openapi.json and the SDK."
    )


def test_ready():
    with LevantoClient("unused", base_url=BASE_URL) as client:
        assert client.ready() is True


@needs_key
@pytest.mark.parametrize(
    "document, question, schema",
    [
        (TICKET, YesNo("Is this ticket revenue-impacting?"), "YesNoDecideResponsePublic"),
        (TICKET, Choice("Which team owns this first?", ["billing", "engineering", "sales"]), "ChoiceDecideResponsePublic"),
        (TICKET, Scale("How urgent is this ticket?", LEVELS), "ScaleDecideResponsePublic"),
        (INCIDENTS, Sort("Most urgent first"), "SortDecideResponsePublic"),
        (TICKET, Tags([TagSpec("outage", "outage: something is down or failing"), "billing"], instructions="Tag what the ticket reports."), "TagsDecideResponsePublic"),
    ],
    ids=["yesno", "choice", "scale", "sort", "tags"],
)
def test_every_kind(live, document, question, schema):
    client, capture = live
    env = client.decide(document, question)
    assert_response(capture.bodies[-1], schema)
    assert env == capture.bodies[-1]
    assert env["kind"] == question.kind and env["meta"]["model"].startswith("levanto-sage")


@needs_key
def test_answers_are_sensible(live):
    client, _ = live
    assert client.yesno(TICKET, "Is this ticket revenue-impacting?")["answer"] == "yes"
    assert client.sort(INCIDENTS, "Most urgent first")["sorted"][0] == "db_down"
    assert client.scale(TICKET, "How urgent is this ticket?", LEVELS)["expectation"] > 2.5


@needs_key
def test_reasoning_off_and_on(live):
    client, _ = live
    off = client.decide(TICKET, YesNo("Is this ticket revenue-impacting?"), reasoning="off")
    assert off["meta"]["reasoning"]["ran"] is False
    on = client.decide(TICKET, YesNo("Is this ticket revenue-impacting?"), reasoning="on")
    assert on["meta"]["reasoning"]["ran"] is True


@needs_key
def test_batch_groups_with_image_and_sort(live):
    client, capture = live
    out = client.decide_groups(
        [
            Group(TICKET, [YesNo("Revenue-impacting?"), Scale("How urgent?", LEVELS, id="urgency")]),
            Group(INCIDENTS, [Sort("Most urgent first")]),
            Group(Image.from_bytes(samples.PNG_BLUE, text="Is this image mostly blue?"), [YesNo("Is the image mostly blue?")]),
        ],
        reasoning="off",
    )
    assert_response(capture.bodies[-1], "BatchDecideResponsePublic")
    items = [item for group in out for item in group["items"]]
    assert all(item["ok"] for item in items), items
    assert [item["id"] for item in items] == ["q0", "urgency", "q0", "q0"]
    assert out[2]["items"][0]["meta"]["usage"]["image_count"] == 1


@needs_key
def test_batch_isolates_a_failing_question(live):
    client, capture = live
    items = client.decide(TICKET, [YesNo("Revenue-impacting?"), Sort("Rank")])
    assert_response(capture.bodies[-1], "BatchDecideResponsePublic")
    assert items[0]["ok"] is True
    assert items[1]["ok"] is False and items[1]["error"]


@needs_key
def test_invalid_request_is_a_validation_error(live):
    client, _ = live
    with pytest.raises(ValidationError) as exc:
        client.decide(TICKET, Scale("How urgent?", LEVELS[:4]))
    assert exc.value.status == 400 and exc.value.detail


def test_bad_key_is_an_auth_error():
    with LevantoClient("lv_live_not_a_real_key", base_url=BASE_URL) as client:
        with pytest.raises(AuthError) as exc:
            client.yesno("text", "Is this a test?")
    assert exc.value.status == 401
