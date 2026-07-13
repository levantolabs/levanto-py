"""Quick start: create a client, make one decision, use a shortcut.

Run:  LEVANTO_API_KEY=lv_live_... python examples/01_quickstart.py
"""

import asyncio
import os
import sys

from levanto import AsyncLevantoClient, LevantoClient, YesNo

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")

client = LevantoClient(api_key=api_key)

doc = 'Marketing email: "Risk-free, guaranteed 40% returns for accredited investors."'

# decide() returns the full envelope: {id, kind, result, meta, grounding_meta?}
env = client.decide(doc, YesNo("Does this need compliance review?"))
print("answer     :", env["result"]["answer"])  # 'yes' | 'no'
print("probability:", env["result"]["probability"])
print("confidence :", env["result"]["confidence"])
print("latency_ms :", env["meta"]["latency_ms"])

# Shortcuts (client.yesno / choice / scale / sort / tags) return the result payload.
r = client.yesno(doc, "Does this need compliance review?")
print("shortcut   :", r["answer"], r["probability"])

client.close()


# --- Python-only: the same call with the async client -----------------------
async def main_async() -> None:
    async with AsyncLevantoClient(api_key=api_key) as aclient:
        env = await aclient.decide(doc, YesNo("Does this need compliance review?"))
        print("async      :", env["result"]["answer"])


asyncio.run(main_async())
