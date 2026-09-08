# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the shared SSH-target injection guard (core/ssh_target.py).

This is the single source of truth used by both the RPC tunnel and the
remote-exec helpers, so its accept/reject set must stay exact (it must match
``ssh_ops.validate_ssh_target``'s historical behaviour) and reject embedded
newlines outright.
"""

from __future__ import annotations

import pytest
from hop3_cli.core.ssh_target import (
    is_safe_ssh_target,
    split_ssh_target,
    ssh_options_from,
)


@pytest.mark.parametrize(
    "target",
    ["root@test.com", "host.example.com", "user@1.2.3.4", "u@h:22"],
)
def test_accepts_plain_targets(target) -> None:
    assert is_safe_ssh_target(target) is True


@pytest.mark.parametrize(
    "target",
    [
        "-oProxyCommand=evil@host",  # option injection (leading '-')
        "-lroot",
        "",  # empty
        "user@-h",  # '-'-leading host
        "a b@host",  # shell metachar (space)
        "root@evilhost\n",  # trailing newline must not slip past `\Z`
        "host\nevil",  # embedded newline
    ],
)
def test_rejects_unsafe_targets(target) -> None:
    assert is_safe_ssh_target(target) is False


# ---- user@host[:port] and the ssh_options setting ----


def test_split_target_takes_the_port_off() -> None:
    assert split_ssh_target("root@host:2222") == ("root@host", 2222)
    assert split_ssh_target("root@host") == ("root@host", None)


@pytest.mark.parametrize("target", ["root@host:abc", "root@host:0", "root@host:70000"])
def test_split_target_refuses_a_bad_port(target) -> None:
    with pytest.raises(ValueError, match="invalid SSH port"):
        split_ssh_target(target)


def test_ssh_options_split_like_a_shell_and_default_to_none() -> None:
    assert ssh_options_from("ProxyJump=bastion UserKnownHostsFile='/tmp/k h'") == [
        "ProxyJump=bastion",
        "UserKnownHostsFile=/tmp/k h",
    ]
    assert ssh_options_from("") == []
    assert ssh_options_from(None) == []
