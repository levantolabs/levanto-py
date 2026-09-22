"""Errors, retries, timeouts, readiness, and client setup."""

from __future__ import annotations

import httpx
import pytest

from levanto import (
    AllowanceExhaustedError,
    AsyncLevantoClient,
    AuthError,
    LevantoAPIError,
    LevantoClient,
    LevantoError,
    ServiceUnavailableError,
    ValidationError,
    YesNo,
)
from tests import samples
from tests.conftest import MODES, Recorder, call


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "status, detail, error",
    [
        (400, "scale levels must be integers in 0..4", ValidationError),
        (401, "API key required. Provide a valid Levanto API key.", AuthError),
        (402, "Decision allowance exhausted for this period.", AllowanceExhaustedError),
        (422, "content: Field required", ValidationError),
        (503, "Service is still loading.", ServiceUnavailableError),
        (500, "boom", LevantoAPIError),
        (404, "Not Found", LevantoAPIError),
    ],
)
async def test_status_maps_to_error(mode, status, detail, error):
    with pytest.raises(error) as exc:
        await call(mode, Recorder((status, {"detail": detail})), "decide", "doc", YesNo("q"))
    assert exc.value.status == status
    assert exc.value.detail == detail
    assert detail in str(exc.value)


def test_error_hierarchy():
    assert issubclass(AllowanceExhaustedError, AuthError)
    for cls in (AuthError, ValidationError, ServiceUnavailableError, LevantoAPIError):
        assert issubclass(cls, LevantoError)


@pytest.mark.parametrize("mode", MODES)
async def test_non_json_error_body_becomes_detail(mode):
    with pytest.raises(LevantoAPIError) as exc:
        await call(mode, Recorder((502, "Bad Gateway")), "decide", "doc", YesNo("q"))
    assert exc.value.detail == "Bad Gateway"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_retryable_statuses_are_retried_then_succeed(mode, status):
    rec = Recorder((status, {"detail": "x"}), (status, {"detail": "x"}), (200, samples.YESNO))
    env = await call(mode, rec, "decide", "doc", YesNo("q"), client={"max_retries": 3})
    assert env == samples.YESNO and len(rec.requests) == 3


@pytest.mark.parametrize("mode", MODES)
async def test_retries_stop_at_max_retries(mode):
    rec = Recorder((503, {"detail": "loading"}))
    with pytest.raises(ServiceUnavailableError):
        await call(mode, rec, "decide", "doc", YesNo("q"), client={"max_retries": 2})
    assert len(rec.requests) == 3


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("status", [400, 401, 402, 422])
async def test_client_errors_are_not_retried(mode, status):
    rec = Recorder((status, {"detail": "no"}))
    with pytest.raises(LevantoError):
        await call(mode, rec, "decide", "doc", YesNo("q"), client={"max_retries": 3})
    assert len(rec.requests) == 1


def test_retry_after_header_is_honoured():
    from levanto._core import backoff_delay

    assert backoff_delay(0, httpx.Response(429, headers={"retry-after": "2"})) == 2.0
    assert backoff_delay(0, httpx.Response(429, headers={"retry-after": "600"})) == 30.0
    assert 0 <= backoff_delay(5, httpx.Response(429, headers={"retry-after": "soon"})) <= 8.0
    assert all(0 <= backoff_delay(a) <= 8.0 for a in range(10))


@pytest.mark.parametrize("mode", MODES)
async def test_connection_errors_are_retried_then_wrapped(mode):
    rec = Recorder(httpx.ConnectError("refused"))
    with pytest.raises(LevantoError, match="failed") as exc:
        await call(mode, rec, "decide", "doc", YesNo("q"), client={"max_retries": 2})
    assert len(rec.requests) == 3 and exc.value.status is None


@pytest.mark.parametrize("mode", MODES)
async def test_timeouts_are_not_retried(mode):
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(LevantoError, match="timed out"):
        await call(mode, rec, "decide", "doc", YesNo("q"), client={"max_retries": 3})
    assert len(rec.requests) == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("reply, expected", [((200, {}), True), ((503, {"detail": "loading"}), False), (httpx.ConnectError("x"), False)])
async def test_ready(mode, reply, expected):
    rec = Recorder(reply)
    assert await call(mode, rec, "ready", client={"max_retries": 3}) is expected
    assert len(rec.requests) == 1 and rec.requests[0].url.path == "/ready"


def test_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("LEVANTO_API_KEY", "lv_env")
    rec = Recorder((200, samples.YESNO))
    with LevantoClient(transport=httpx.MockTransport(rec)) as client:
        client.decide("doc", YesNo("q"))
    assert rec.requests[0].headers["authorization"] == "Bearer lv_env"


@pytest.mark.parametrize("cls", [LevantoClient, AsyncLevantoClient])
def test_missing_api_key(monkeypatch, cls):
    monkeypatch.delenv("LEVANTO_API_KEY", raising=False)
    with pytest.raises(LevantoError, match="API key"):
        cls()


def test_base_url_trailing_slash():
    rec = Recorder((200, samples.YESNO))
    with LevantoClient("k", base_url="https://example.test/", transport=httpx.MockTransport(rec)) as client:
        client.decide("doc", YesNo("q"))
    assert str(rec.requests[0].url) == "https://example.test/decide"
