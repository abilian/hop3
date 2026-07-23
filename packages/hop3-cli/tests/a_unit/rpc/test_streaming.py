# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the SSE deployment-log streaming client.

Regression focus: a stream endpoint that answers with a 3xx redirect
(auth failure → /auth/login) must surface a clear "stream authentication
failed" error, NOT be silently followed to the login page and reported
as the useless "Stream ended unexpectedly". See the bookwyrm cloud-test
incident where a redis-provisioning failure was masked this way.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from hop3_cli.config import Config
from hop3_cli.exceptions import DeploymentError
from hop3_cli.rpc.responses import _handle_streaming_response
from hop3_cli.rpc.streaming import stream_deployment_logs
from hop3_cli.ui.rich_printer import RichPrinter


class _FakeResponse:
    """Minimal stand-in for a streaming requests.Response."""

    def __init__(
        self,
        status_code: int,
        *,
        lines: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._lines = lines or []
        self.headers = headers or {}

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}

    def iter_lines(self, decode_unicode: bool = False):
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@contextmanager
def _patched_get(response: _FakeResponse):
    """Patch requests.get to return ``response`` and capture call kwargs."""
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return response

    with patch("hop3_cli.rpc.streaming.requests.get", side_effect=fake_get):
        yield captured


def _printer() -> RichPrinter:
    return RichPrinter(quiet=True)


# ---- the redirect regression --------------------------------------------


def test_stream_redirect_raises_auth_error_not_followed() -> None:
    """A 302 to /auth/login must raise a clear auth error, not be followed."""
    resp = _FakeResponse(302, headers={"Location": "/auth/login"})
    with _patched_get(resp) as captured, pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="abc123",
            printer=_printer(),
            token="tok",
        )
    # Error names the redirect + location, so the operator knows it's auth.
    assert "authentication failed" in str(exc.value).lower()
    assert "/auth/login" in str(exc.value)
    # And we did NOT follow the redirect.
    assert captured["kwargs"]["allow_redirects"] is False


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_all_redirect_codes_treated_as_auth_failure(code: int) -> None:
    resp = _FakeResponse(code, headers={"Location": "/auth/login"})
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=_printer(),
            token="tok",
        )
    assert "authentication failed" in str(exc.value).lower()


def test_redirect_without_location_header_still_errors() -> None:
    """Missing Location shouldn't crash — fall back to '(unknown)'."""
    resp = _FakeResponse(302)
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=_printer(),
            token="tok",
        )
    assert "authentication failed" in str(exc.value).lower()


# ---- other status codes still behave -----------------------------------


def test_404_reports_stream_not_found() -> None:
    resp = _FakeResponse(404)
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="missing",
            printer=_printer(),
            token="tok",
        )
    assert "not found" in str(exc.value).lower()


def test_500_reports_http_failure() -> None:
    resp = _FakeResponse(500)
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=_printer(),
            token="tok",
        )
    assert "http 500" in str(exc.value).lower()


# ---- happy path: a complete event with an error is surfaced -------------


def test_complete_event_with_error_is_raised() -> None:
    """
    When the stream DOES connect (200), a failed `complete` event must
    surface the server's actual error message — the path that was masked.
    """
    lines = [
        "event: complete",
        'data: {"success": false, "error": "redis addon: redis-cli not found"}',
        "",
    ]
    resp = _FakeResponse(200, lines=lines)
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=_printer(),
            token="tok",
        )
    assert "redis-cli not found" in str(exc.value)


def test_stream_ends_without_complete_event_still_reported() -> None:
    """
    A genuine 200 stream that ends with no `complete` event keeps the
    original 'ended unexpectedly' message (a real, distinct condition).
    """
    resp = _FakeResponse(200, lines=["event: log", 'data: {"msg": "building"}', ""])
    with _patched_get(resp), pytest.raises(DeploymentError) as exc:
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=_printer(),
            token="tok",
        )
    assert "ended unexpectedly" in str(exc.value).lower()


def test_complete_event_success_prints_deployed_successfully(capsys) -> None:
    """
    A successful deploy must print the 'deployed successfully' phrase to
    stdout — the phrase the non-streaming path and every tutorial's `output
    contains` block assert on. (Was 'completed successfully', which silently
    failed all 21 tutorial deploy checks.)
    """
    lines = [
        "event: complete",
        'data: {"success": true, "duration": 9.5}',
        "",
    ]
    resp = _FakeResponse(200, lines=lines)
    with _patched_get(resp):
        stream_deployment_logs(
            base_url="http://server:8000",
            stream_id="x",
            printer=RichPrinter(quiet=False),
            token="tok",
        )
    assert "deployed successfully" in capsys.readouterr().out


# ---- _handle_streaming_response resolves api_url from the context --------


def _ctx_config(api_url: str) -> Config:
    """
    A Config whose api_url lives in a [contexts.*] block (ADR 042 shape),
    NOT in the flat top-level key — the shape `hop3 init`/`login` now writes.
    """
    return Config(
        data={
            "current_context": "prod",
            "contexts": {"prod": {"api_url": api_url, "api_token": "tok"}},
        }
    )


def test_streaming_uses_context_api_url_not_flat_key() -> None:
    """
    Regression: a context-configured CLI (no flat `api_url`) must stream.

    Previously _handle_streaming_response read ``config.get("api_url", "")`` —
    empty for context configs — and aborted with "No API URL configured" even
    though the RPC had just connected via that same context. It must resolve
    the URL through get_api_url(), matching how Client connects.
    """
    config = _ctx_config("http://localhost:8000")
    # The flat lookup the old code used is indeed empty for this config.
    assert config.get("api_url", "") == ""

    result = [{"t": "stream", "stream_id": "abc123"}]
    with patch("hop3_cli.rpc.streaming.stream_deployment_logs") as mock_stream:
        _handle_streaming_response(result, config, _printer())

    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["base_url"] == "http://localhost:8000"
    assert mock_stream.call_args.kwargs["stream_id"] == "abc123"


def test_streaming_tunnel_mode_with_ssh_context_url() -> None:
    """
    The demo path: api_url is ssh:// inside a context, connection tunneled.

    base_url must become the local tunnel endpoint, and the ssh:// URL must
    not trip the "No API URL configured" guard.
    """
    config = _ctx_config("ssh://root@localhost")
    result = [{"t": "stream", "stream_id": "z"}]
    with patch("hop3_cli.rpc.streaming.stream_deployment_logs") as mock_stream:
        _handle_streaming_response(result, config, _printer(), tunnel_port=12345)

    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["base_url"] == "http://localhost:12345"
