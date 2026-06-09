# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nginx ops (mocked exec)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.exec import CommandResult
from hop3_rootd.ops import get_handler, nginx as nginx_ops
from hop3_rootd.ops._base import OpContext
from hop3_rootd.ops.nginx import NginxBinaryNotFoundError
from hop3_rootd.protocol import Request
from hop3_rootd.state import State


def _ctx() -> OpContext:
    return OpContext(
        state=State(),
        state_path=None,
        save_state=lambda: None,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test",
    )


def _ok(stderr: str = "") -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout="", stderr=stderr)


def _fail(stderr: str, returncode: int = 1) -> CommandResult:
    return CommandResult(argv=[], returncode=returncode, stdout="", stderr=stderr)


def _req(op: str) -> Request:
    return Request(v=PROTOCOL_VERSION, id="r1", op=op, args={})


# --- nginx.reload --------------------------------------------------------


def test_reload_uses_systemctl_when_available():
    handler = get_handler("nginx.reload")
    assert handler is not None
    with (
        patch("shutil.which") as mock_which,
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):
        # systemctl found and on allow-list; nginx not installed
        def which_side(cmd):
            return "/usr/bin/systemctl" if cmd == "systemctl" else None

        mock_which.side_effect = which_side
        mock_exec.return_value = _ok()
        result = handler(_req("nginx.reload"), _ctx())

    assert result == {"method": "systemctl"}
    args, _ = mock_exec.call_args
    assert args[0][0] == "/usr/bin/systemctl"
    assert "reload" in args[0]
    assert "nginx" in args[0]


def test_reload_falls_back_to_nginx_s_reload():
    """systemctl missing or fails → try `nginx -s reload`."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    with (
        patch("shutil.which") as mock_which,
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):

        def which_side(cmd):
            return {
                "systemctl": "/usr/bin/systemctl",
                "nginx": "/usr/sbin/nginx",
            }.get(cmd)

        mock_which.side_effect = which_side
        mock_exec.side_effect = [_fail("systemd not running"), _ok()]
        result = handler(_req("nginx.reload"), _ctx())

    assert result == {"method": "nginx -s reload"}
    assert mock_exec.call_count == 2


def test_reload_raises_when_no_method_available():
    """No systemctl, no nginx → raise."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(NginxBinaryNotFoundError, match="no nginx-reload method"),
    ):
        handler(_req("nginx.reload"), _ctx())


def test_reload_raises_when_all_methods_fail():
    handler = get_handler("nginx.reload")
    assert handler is not None
    with (
        patch("shutil.which") as mock_which,
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):

        def which_side(cmd):
            return {
                "systemctl": "/usr/bin/systemctl",
                "nginx": "/usr/sbin/nginx",
            }.get(cmd)

        mock_which.side_effect = which_side
        mock_exec.return_value = _fail("error")
        with pytest.raises(
            NginxBinaryNotFoundError, match="all nginx-reload methods failed"
        ):
            handler(_req("nginx.reload"), _ctx())


# --- nginx.validate_config -----------------------------------------------


def test_validate_returns_valid_true_on_success():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    with (
        patch("shutil.which", return_value="/usr/sbin/nginx"),
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):
        mock_exec.return_value = _ok(stderr="syntax is ok\n... test is successful")
        result = handler(_req("nginx.validate_config"), _ctx())
    assert result == {"valid": True}


def test_validate_returns_valid_false_with_errors():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    stderr = (
        "nginx: [emerg] unexpected '}' in /etc/nginx/sites-enabled/default:42\n"
        "nginx: configuration file /etc/nginx/nginx.conf test failed\n"
    )
    with (
        patch("shutil.which", return_value="/usr/sbin/nginx"),
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):
        mock_exec.return_value = _fail(stderr=stderr)
        result = handler(_req("nginx.validate_config"), _ctx())

    assert result["valid"] is False
    # Parsed errors include the [emerg] line and the verdict.
    assert any("[emerg]" in line for line in result["errors"])
    assert any("test failed" in line for line in result["errors"])
    assert "raw_stderr" in result


def test_validate_filters_warnings_in_errors_list():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    stderr = "Some chatter\nnginx: [warn] something weird\nnginx: [emerg] real error\n"
    with (
        patch("shutil.which", return_value="/usr/sbin/nginx"),
        patch.object(nginx_ops, "exec_run") as mock_exec,
    ):
        mock_exec.return_value = _fail(stderr=stderr)
        result = handler(_req("nginx.validate_config"), _ctx())
    # Both [warn] and [emerg] lines surface in errors; "Some chatter" is dropped.
    assert any("[warn]" in line for line in result["errors"])
    assert any("[emerg]" in line for line in result["errors"])
    assert not any("chatter" in line for line in result["errors"])


def test_validate_raises_when_nginx_missing():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(NginxBinaryNotFoundError, match="not on allow-list"),
    ):
        handler(_req("nginx.validate_config"), _ctx())


def test_validate_raises_when_nginx_not_in_allowlist():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    with (
        patch("shutil.which", return_value="/opt/sketchy/nginx"),
        pytest.raises(NginxBinaryNotFoundError, match="not on allow-list"),
    ):
        handler(_req("nginx.validate_config"), _ctx())
