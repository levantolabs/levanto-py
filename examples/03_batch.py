"""Batch: one document, many questions, in a single round-trip.

Run:  LEVANTO_API_KEY=lv_live_... python examples/03_batch.py
"""

import json
import os
import sys

from levanto import Group, LevantoClient, Scale, Tags, YesNo

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")

client = LevantoClient(api_key=api_key)

doc = 'Marketing email: "Risk-free, guaranteed 40% returns for accredited investors."'
severity = ["none", "low", "moderate", "high", "severe"]

# Passing a list of questions fans the same document across all of them and
# returns a list of BatchItem aligned to input order.
items = client.decide(
    doc,
    [
        YesNo("Needs compliance review?"),
        Scale("How severe?", severity),
        Tags(["financial", {"id": "pii", "threshold": 0.5}]),
    ],
)

for item in items:
    if item["ok"]:
        # A successful item reads exactly like a single decide: result + meta.
        print(f"{item['id']} ({item['kind']}) ->", json.dumps(item["result"]), f"[{item['meta']['latency_ms']}ms]")
    else:
        print(f"{item['id']} ({item['kind']}) FAILED:", item["error"])

# Score several *different* documents in one round-trip, each with its own
# questions, via decide_groups. Returns one GroupResult per input group.
groups = client.decide_groups([
    Group(doc, [YesNo("Needs compliance review?")]),
    Group(
        "The quarterly report looks solid and on-budget.",
        [YesNo("Needs compliance review?"), Scale("How severe?", severity)],
    ),
])
for gi, g in enumerate(groups):
    print(f"group {gi}:", [f"{i['kind']}={'ok' if i['ok'] else i['error']}" for i in g["items"]])

client.close()
