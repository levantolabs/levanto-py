"""Custom transport: inject your own httpx transport (proxy, mTLS, logging).

The `transport=` param is passed straight to httpx.Client. Any
httpx.BaseTransport works; here we subclass HTTPTransport to log each request.

Run:  LEVANTO_API_KEY=lv_live_... python examples/06_custom_transport.py
"""

import os
import sys
import time

import httpx

from levanto import LevantoClient

api_key = os.environ.get("LEVANTO_API_KEY")
if not api_key:
    sys.exit("Set LEVANTO_API_KEY to run this example.")


class LoggingTransport(httpx.HTTPTransport):
    """A drop-in transport that logs status and latency for each request."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        started = time.monotonic()
        response = super().handle_request(request)
        ms = (time.monotonic() - started) * 1000
        print(f"[levanto] {response.status_code} {request.url} {ms:.0f}ms")
        return response


client = LevantoClient(api_key=api_key, transport=LoggingTransport())

r = client.yesno("Wire $10M offshore today, no invoice.", "Is this suspicious?")
print("answer:", r["answer"])

client.close()

# For a proxy / custom TLS, build an httpx.HTTPTransport directly:
#
#   transport = httpx.HTTPTransport(proxy="http://proxy.internal:8080", retries=1)
#   client = LevantoClient(api_key=api_key, transport=transport)
#
# The async client (AsyncLevantoClient) takes an httpx.AsyncBaseTransport,
# e.g. httpx.AsyncHTTPTransport.
