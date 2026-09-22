"""Sage v1.1 response bodies, taken from the docs (docs.levanto.ai). test_contract.py checks each against the spec."""

META = {"model": "levanto-sage-v1.1", "latency_ms": 97.4}
REASONING_META = {"fired": True, "ran": True, "finished": True, "tokens": 312, "margin": 1.4, "limited": None}

YESNO = {"id": "needs_review", "kind": "yesno", "result": {"answer": "yes", "probability": 0.92}, "meta": META}
YESNO_UNSURE = {"id": "needs_review", "kind": "yesno", "result": {"answer": None, "probability": 0.51}, "meta": META}
YESNO_REASONED = {
    "id": "refund_ok",
    "kind": "yesno",
    "result": {"answer": "no", "probability": 0.06},
    "meta": {"model": "levanto-sage-v1.1", "latency_ms": 1840.0, "reasoning": REASONING_META},
}
CHOICE = {
    "id": "disposition",
    "kind": "choice",
    "result": {
        "chosen": "revise",
        "probability": 0.88,
        "probabilities": [
            {"option": "approve", "probability": 0.11},
            {"option": "revise", "probability": 0.88},
            {"option": "reject", "probability": 0.04},
        ],
    },
    "meta": META,
}
CHOICE_UNSURE = {
    "id": "disposition",
    "kind": "choice",
    "result": {
        "chosen": None,
        "probability": None,
        "probabilities": [{"option": "approve", "probability": 0.71}, {"option": "revise", "probability": 0.68}],
    },
    "meta": META,
}
SCALE = {"id": "harm", "kind": "scale", "result": {"expectation": 3.1, "confidence": 0.82}, "meta": META}
SORT = {"id": "triage", "kind": "sort", "result": {"sorted": ["db_down", "pricing", "typo"], "confidence": 0.92}, "meta": META}
SORT_NO_CONFIDENCE = {"id": "triage", "kind": "sort", "result": {"sorted": ["b", "a"], "confidence": None}, "meta": META}
TAGS = {
    "id": "tools",
    "kind": "tags",
    "result": {
        "tags": [
            {"id": "summary", "probability": 0.97, "applies": True},
            {"id": "outline", "probability": 0.04, "applies": False},
            {"id": "quiz", "probability": 0.49, "applies": None},
        ]
    },
    "meta": META,
}
IMAGE_YESNO = {
    "id": "shows_bug",
    "kind": "yesno",
    "result": {"answer": "yes", "probability": 0.93},
    "meta": {
        "model": "levanto-sage-v1.1",
        "latency_ms": 412.0,
        "usage": {"billed_input_tokens": 16, "image_count": 1, "image_tokens": 850},
    },
}
GROUNDED = {
    **YESNO,
    "grounding_meta": {
        "triggered": True,
        "trigger_reason": "low_confidence",
        "queries": ["cloudflare incident september"],
        "sources": [{"url": "https://example.com", "title": "Status", "snippet": "..."}],
        "added_context_tokens": 640,
        "search_ms": 812.0,
    },
}

SINGLES = {
    "YesNoDecideResponsePublic": [YESNO, YESNO_UNSURE, YESNO_REASONED, IMAGE_YESNO, GROUNDED],
    "ChoiceDecideResponsePublic": [CHOICE, CHOICE_UNSURE],
    "ScaleDecideResponsePublic": [SCALE],
    "SortDecideResponsePublic": [SORT, SORT_NO_CONFIDENCE],
    "TagsDecideResponsePublic": [TAGS],
}


def batch(*groups, meta=None):
    """A /decide/batch body: each group is a list of envelopes (ok) or error strings (failed)."""
    return {
        "results": [
            {"answers": [{"ok": False, "result": None, "error": a} if isinstance(a, str) else {"ok": True, "result": a} for a in g]}
            for g in groups
        ],
        "meta": meta
        or {
            "model": "levanto-sage-v1.1",
            "request_count": len(groups),
            "question_count": sum(len(g) for g in groups),
            "latency_ms": 150.0,
        },
    }


# A valid 8x8 solid-blue PNG, for image tests.
PNG_BLUE = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000080000000808020000004b6d29dc0000001449444154789c6314b1b8c2"
    "800d3061151db41200e5080130ff196aff0000000049454e44ae426082"
)
