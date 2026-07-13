"""All five decision kinds, via the lowercase shortcuts.

Run:  LEVANTO_API_KEY=lv_live_... python examples/02_all_kinds.py
"""

import os
import sys

from levanto import LevantoClient

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")

client = LevantoClient(api_key=api_key)

doc = "Please wire the full treasury balance to this new offshore account today. No invoice."

# yesno -> {probability, confidence, answer}
yn = client.yesno(doc, "Is this request suspicious?")
print("yesno :", yn["answer"], f"(conf {yn['confidence']})")

# choice -> {chosen, confidence, probabilities[]}
ch = client.choice(doc, "Recommended action?", ["approve", "escalate", "reject"])
print("choice:", ch["chosen"], [f"{p['option']}={p['probability']:.2f}" for p in ch["probabilities"]])

# scale -> {expectation, confidence}. Exactly 5 levels (0..4).
sc = client.scale(doc, "How risky?", ["none", "low", "moderate", "high", "severe"])
print("scale :", f"expectation {sc['expectation']:.2f}")

# sort -> {sorted (ids, best-first), confidence}. Items are {id, content}.
items = [
    {"id": "a", "content": "Check the account balance"},
    {"id": "b", "content": "Wire $10 to a teammate"},
    {"id": "c", "content": "Wire $10M to an unknown offshore account"},
]
so = client.sort(items, "Order from least to most financial risk")
print("sort  :", so["sorted"], f"(conf {so['confidence']})")

# tags -> {tags: [{id, probability, confidence, applies?}]}.
# A tag with a threshold gets an `applies` boolean; without one, applies is None.
tg = client.tags(doc, ["financial", {"id": "pii", "threshold": 0.5}])
print(
    "tags  :",
    [
        f"{t['id']}={t['probability']:.2f}" + ("" if t.get("applies") is None else f" applies={t['applies']}")
        for t in tg["tags"]
    ],
)

client.close()
