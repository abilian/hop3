# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The ssh line behind `hop3 login --ssh` and the other bootstrap helpers.

It used to be a bare ``ssh user@host cmd``: a server on a non-standard SSH port
was reachable through the ``ssh://user@host:port`` tunnel and not through the
login that sets that tunnel up, and neither the key nor the extra options the
tunnel honours applied to it.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local.ssh_ops import BootstrapError, ssh_command_argv


def test_port_in_the_target_becomes_dash_p() -> None:
    argv = ssh_command_argv("root@host:2222", "echo ok")
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[-2:] == ["root@host", "echo ok"]


def test_key_and_options_come_from_the_settings(monkeypatch) -> None:
    monkeypatch.setenv("HOP3_SSH_KEY", "/keys/e2e")
    monkeypatch.setenv("HOP3_SSH_OPTIONS", "UserKnownHostsFile=/tmp/kh ProxyJump=b")
    argv = ssh_command_argv("root@host", "echo ok")
    assert argv[argv.index("-i") + 1] == "/keys/e2e"
    assert "UserKnownHostsFile=/tmp/kh" in argv
    assert "ProxyJump=b" in argv
    assert argv[-2:] == ["root@host", "echo ok"]
    assert "-p" not in argv


def test_new_host_keys_are_accepted_like_the_tunnel_does() -> None:
    argv = ssh_command_argv("root@host", "echo ok")
    assert argv[argv.index("-o") + 1] == "StrictHostKeyChecking=accept-new"


def test_target_is_still_validated_first() -> None:
    with pytest.raises(BootstrapError):
        ssh_command_argv("-oProxyCommand=evil@host", "echo ok")
