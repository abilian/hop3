# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the `hop3 tunnel <name>` local command.

These exercise the command's logic (arg parsing, URL rewriting, endpoint
fetch, SSH param derivation, hold/cleanup) without opening a real tunnel.
The transport itself is covered by ``test_tunnel.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_cli.commands.local import tunnel_cmd
from hop3_cli.commands.local.tunnel_cmd import (
    _fetch_endpoint,
    _parse_args,
    _rewrite_url,
    _ssh_params,
    handle_tunnel,
)
from hop3_cli.exit_codes import ExitCode
from jsonrpcclient import Error, Ok
from stubs import StubClient

_PG_URL = "postgresql://u:secret@127.0.0.1:5432/mydb"
_ENDPOINT = {"type": "postgres", "host": "127.0.0.1", "port": 5432, "url": _PG_URL}


# ---- _parse_args ----


def test_parse_args_name_only():
    assert _parse_args(["mydb"]) == ("mydb", None)


def test_parse_args_port_separate_token():
    assert _parse_args(["mydb", "--port", "6000"]) == ("mydb", 6000)


def test_parse_args_port_equals_form():
    assert _parse_args(["--port=6000", "mydb"]) == ("mydb", 6000)


def test_parse_args_no_name():
    assert _parse_args([])[0] is None


def test_parse_args_bad_port_exits_usage():
    with pytest.raises(SystemExit) as exc:
        _parse_args(["mydb", "--port", "notanumber"])
    assert exc.value.code == ExitCode.USAGE_ERROR


# ---- _rewrite_url ----


def test_rewrite_url_swaps_port_keeps_credentials_and_path():
    assert _rewrite_url(_PG_URL, 6543) == "postgresql://u:secret@127.0.0.1:6543/mydb"


def test_rewrite_url_without_credentials():
    assert _rewrite_url("redis://127.0.0.1:6379/0", 6000) == "redis://127.0.0.1:6000/0"


# ---- _ssh_params ----


def test_ssh_params_from_ssh_url():
    config = MagicMock()
    config.get_api_url.return_value = "ssh://root@server.example.com:2222"
    config.get.side_effect = lambda key, default=None: default
    params = _ssh_params(config)
    assert params["host"] == "server.example.com"
    assert params["user"] == "root"
    assert params["port"] == 2222


def test_ssh_params_rejects_non_ssh_url():
    config = MagicMock()
    config.get_api_url.return_value = "https://server.example.com"
    with pytest.raises(SystemExit) as exc:
        _ssh_params(config)
    assert exc.value.code == ExitCode.USAGE_ERROR


# ---- _fetch_endpoint ----


def test_fetch_endpoint_extracts_data_payload():
    response = Ok([{"t": "data", "data": _ENDPOINT}], 1)
    with patch("hop3_cli.rpc.Client", return_value=StubClient(response)):
        assert _fetch_endpoint(MagicMock(), "mydb") == _ENDPOINT


def test_fetch_endpoint_error_response_exits_resolution():
    response = Error(404, "not found", None, 1)
    with (
        patch("hop3_cli.rpc.Client", return_value=StubClient(response)),
        pytest.raises(SystemExit) as exc,
    ):
        _fetch_endpoint(MagicMock(), "mydb")
    assert exc.value.code == ExitCode.RESOLUTION_ERROR


def test_fetch_endpoint_no_data_item_exits_resolution():
    response = Ok([{"t": "text", "text": "nope"}], 1)
    with (
        patch("hop3_cli.rpc.Client", return_value=StubClient(response)),
        pytest.raises(SystemExit) as exc,
    ):
        _fetch_endpoint(MagicMock(), "mydb")
    assert exc.value.code == ExitCode.RESOLUTION_ERROR


# ---- handle_tunnel (end to end, transport mocked) ----


def test_handle_tunnel_opens_prints_and_cleans_up(capsys):
    forwarder = MagicMock()
    forwarder.local_bind_port = 5432
    config = MagicMock()

    with (
        patch.object(tunnel_cmd, "_fetch_endpoint", return_value=_ENDPOINT),
        patch.object(
            tunnel_cmd,
            "_ssh_params",
            return_value={"host": "srv", "user": "root", "port": 22, "key": None},
        ),
        patch.object(tunnel_cmd, "_start_forwarder", return_value=forwarder),
        patch.object(tunnel_cmd.time, "sleep", side_effect=KeyboardInterrupt),
    ):
        handle_tunnel(["mydb"], config, MagicMock())

    out = capsys.readouterr().out
    # The printed local URL points at the bound local port.
    assert "postgresql://u:secret@127.0.0.1:5432/mydb" in out
    assert "127.0.0.1:5432 -> srv:5432" in out
    # Tunnel is always torn down, even on Ctrl-C.
    forwarder.stop.assert_called_once()


def test_handle_tunnel_requires_name():
    with pytest.raises(SystemExit) as exc:
        handle_tunnel([], MagicMock(), MagicMock())
    assert exc.value.code == ExitCode.USAGE_ERROR


def test_handle_tunnel_dropped_connection_fails_loud(capsys):
    # If the SSH connection is down, don't pretend the tunnel is serving.
    forwarder = MagicMock()
    forwarder.local_bind_port = 5432
    forwarder.is_active = False

    with (
        patch.object(tunnel_cmd, "_fetch_endpoint", return_value=_ENDPOINT),
        patch.object(
            tunnel_cmd,
            "_ssh_params",
            return_value={"host": "srv", "user": "root", "port": 22, "key": None},
        ),
        patch.object(tunnel_cmd, "_start_forwarder", return_value=forwarder),
        pytest.raises(SystemExit) as exc,
    ):
        handle_tunnel(["mydb"], MagicMock(), MagicMock())

    assert exc.value.code == ExitCode.NETWORK_ERROR
    assert "dropped" in capsys.readouterr().err.lower()
    forwarder.stop.assert_called()
