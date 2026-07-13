"""Grounding: let the server augment a low-confidence decision with web search.

Run:  LEVANTO_API_KEY=lv_live_... python examples/04_grounding.py
"""

import os
import sys

from levanto import Grounding, LevantoClient, YesNo

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")

client = LevantoClient(api_key=api_key)

# Grounding is attached to the question; on the wire it is lifted to a
# top-level sibling. `trigger` and `confidence_floor` are first-class; any other
# server knob (e.g. max_results) goes through `extra`, merged verbatim.
env = client.decide(
    "Acme Corp is a mid-size logistics firm founded in 2011.",
    YesNo(
        "Is Acme Corp currently in bankruptcy proceedings?",
        grounding=Grounding(trigger="always", confidence_floor=0.85, extra={"max_results": 5}),
    ),
)

print("answer :", env["result"]["answer"], f"(conf {env['result']['confidence']})")

gm = env.get("grounding_meta")
if gm:
    print("grounded  :", gm.get("triggered"))
    print("reason    :", gm.get("trigger_reason"))
    print("queries   :", gm.get("queries"))
    print("n_sources :", len(gm.get("sources") or []))
else:
    print("grounding did not run for this decision.")

client.close()
