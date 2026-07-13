"""Error handling: readiness check and typed errors.

Run:  LEVANTO_API_KEY=lv_live_... python examples/05_error_handling.py
"""

import os
import sys

from levanto import AuthError, LevantoClient, LevantoError, ValidationError

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")

client = LevantoClient(api_key=api_key)

# ready() never raises: True once the (scale-to-zero) endpoint is warm, False
# while it is still spinning up. Useful as a pre-flight or health probe.
print("ready:", client.ready())

try:
    # scale requires exactly 5 levels; three levels is rejected server-side.
    client.scale("some document", "rate it", ["only", "three", "levels"])
except ValidationError as err:
    print("ValidationError:", err.status, "-", err.detail)
except AuthError as err:
    print("AuthError (bad/expired key):", err.status)
except LevantoError as err:
    # Base class: also covers timeouts and exhausted transport retries.
    print("LevantoError:", err)

client.close()
