"""Headers, auth, versioning, and public-surface sanity."""

from __future__ import annotations

import pytest

import levanto
from helpers import MODES, Recorder, call, envelope, YESNO_RESULT
from levanto import YesNo


@pytest.mark.parametrize("mode", MODES)
async def test_auth_and_user_agent_headers(mode):
    rec = Recorder(json_body=envelope("yesno", YESNO_RESULT))
    await call(mode, rec, "decide", "doc", YesNo("ok?"))
    headers = rec.last.headers
    assert headers["authorization"] == "Bearer test-key"
    assert headers["user-agent"] == f"levanto-python/{levanto.__version__}"
    assert headers["content-type"] == "application/json"


def test_version_is_semver_string():
    assert levanto.__version__ == "0.1.0"


def test_public_exports_present():
    for name in [
        "LevantoClient",
        "AsyncLevantoClient",
        "YesNo",
        "Choice",
        "Scale",
        "Sort",
        "Tags",
        "ChoiceOption",
        "ScaleLevel",
        "TagSpec",
        "Grounding",
        "LevantoError",
        "AuthError",
        "ValidationError",
        "ServiceUnavailableError",
        "LevantoAPIError",
    ]:
        assert hasattr(levanto, name), name


def test_base_url_override_strips_trailing_slash():
    client = levanto.LevantoClient("k", base_url="http://localhost:8000/")
    try:
        assert str(client._client.base_url) == "http://localhost:8000"
    finally:
        client.close()
