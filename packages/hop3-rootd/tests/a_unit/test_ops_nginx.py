# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nginx ops.

The exec seam is faked via ``OpContext.exec`` (a ``FakeExec``); no real
nginx/systemctl runs. Tests pin resolved paths with ``set_path`` and route
``run`` calls, then assert on the result + recorded argvs.
"""

from __future__ import annotations

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.ops.nginx import NginxBinaryNotFoundError
from hop3_rootd.protocol import Request
from hop3_rootd.state import State

from tests.a_unit._fakes import FakeExec, fail, ok


def _ctx() -> OpContext:
    return OpContext(
        state=State(),
        state_path=None,
        save_state=lambda: None,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test",
        exec=FakeExec(),
    )


def _req(op: str) -> Request:
    return Request(v=PROTOCOL_VERSION, id="r1", op=op, args={})


# --- nginx.reload --------------------------------------------------------


def test_reload_uses_systemctl_when_available():
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("systemctl", "/usr/bin/systemctl")
    ctx.exec.set_path("nginx", None)  # nginx not installed

    result = handler(_req("nginx.reload"), ctx)

    assert result == {"method": "systemctl"}
    reload_calls = [c for c in ctx.exec.calls if "reload" in c]
    assert reload_calls[0][0] == "/usr/bin/systemctl"
    assert "nginx" in reload_calls[0]


def test_reload_falls_back_to_nginx_s_reload():
    """systemctl missing or fails → try `nginx -s reload`."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("systemctl", "/usr/bin/systemctl")
    ctx.exec.set_path("nginx", "/usr/sbin/nginx")
    # systemctl reload fails; `nginx -s reload` succeeds (default ok()).
    ctx.exec.on(
        lambda argv: any("systemctl" in tok for tok in argv),
        fail("systemd not running"),
    )

    result = handler(_req("nginx.reload"), ctx)

    assert result == {"method": "nginx -s reload"}
    # Both methods were attempted.
    assert ctx.exec.calls_with("/usr/bin/systemctl")
    assert ctx.exec.calls_with("-s")  # the `nginx -s reload` fallback


def test_reload_raises_when_no_method_available():
    """No systemctl, no nginx → raise."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("systemctl", None)
    ctx.exec.set_path("nginx", None)
    with pytest.raises(NginxBinaryNotFoundError, match="no nginx-reload method"):
        handler(_req("nginx.reload"), ctx)


def test_reload_raises_when_all_methods_fail():
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("systemctl", "/usr/bin/systemctl")
    ctx.exec.set_path("nginx", "/usr/sbin/nginx")
    ctx.exec.on(lambda argv: True, fail("error"))
    with pytest.raises(
        NginxBinaryNotFoundError, match="all nginx-reload methods failed"
    ):
        handler(_req("nginx.reload"), ctx)


# --- nginx.validate_config -----------------------------------------------


def test_validate_returns_valid_true_on_success():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("nginx", "/usr/sbin/nginx")
    # rc 0 → valid. (nginx -t writes diagnostics to stderr even on success,
    # but the success path doesn't read it.)
    ctx.exec.on(lambda argv: True, ok())
    result = handler(_req("nginx.validate_config"), ctx)
    assert result == {"valid": True}


def test_validate_returns_valid_false_with_errors():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("nginx", "/usr/sbin/nginx")
    stderr = (
        "nginx: [emerg] unexpected '}' in /etc/nginx/sites-enabled/default:42\n"
        "nginx: configuration file /etc/nginx/nginx.conf test failed\n"
    )
    ctx.exec.on(lambda argv: True, fail(stderr=stderr))

    result = handler(_req("nginx.validate_config"), ctx)

    assert result["valid"] is False
    assert any("[emerg]" in line for line in result["errors"])
    assert any("test failed" in line for line in result["errors"])
    assert "raw_stderr" in result


def test_validate_filters_warnings_in_errors_list():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("nginx", "/usr/sbin/nginx")
    stderr = "Some chatter\nnginx: [warn] something weird\nnginx: [emerg] real error\n"
    ctx.exec.on(lambda argv: True, fail(stderr=stderr))

    result = handler(_req("nginx.validate_config"), ctx)
    # Both [warn] and [emerg] lines surface in errors; "Some chatter" is dropped.
    assert any("[warn]" in line for line in result["errors"])
    assert any("[emerg]" in line for line in result["errors"])
    assert not any("chatter" in line for line in result["errors"])


def test_validate_raises_when_nginx_missing():
    """nginx resolves to None (not on PATH / not allow-listed) → raise."""
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx = _ctx()
    ctx.exec.set_path("nginx", None)
    with pytest.raises(NginxBinaryNotFoundError, match="not on allow-list"):
        handler(_req("nginx.validate_config"), ctx)
    # Allow-list rejection itself is covered at the exec seam
    # (test_find_nft_binary_raises_when_not_in_allowlist); the op only owns
    # the None → raise contract.
    assert ctx.exec.calls == []
