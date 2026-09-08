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
    SshSettings,
    is_safe_ssh_target,
    split_ssh_target,
    ssh_base_argv,
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


# ---- SshSettings and the base argv every ssh starts from ----


class _Config:
    def __init__(self, **values: object) -> None:
        self._values = values

    def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


def test_settings_drop_a_key_that_is_not_a_string() -> None:
    assert SshSettings.from_config(_Config(ssh_key=42)).key is None
    assert SshSettings.from_config(_Config(ssh_key="/k")).key == "/k"


def test_settings_read_port_and_options() -> None:
    settings = SshSettings.from_config(_Config(ssh_port="2222", ssh_options="A=1 B=2"))
    assert settings.port == 2222
    assert settings.options == ("A=1", "B=2")


def test_base_argv_adds_dash_p_only_off_the_default_port() -> None:
    assert "-p" not in ssh_base_argv(SshSettings())
    assert ssh_base_argv(SshSettings(port=2222))[-2:] == ["-p", "2222"]
    assert "-p" not in ssh_base_argv(SshSettings(port=2222), port=22)
    assert ssh_base_argv(SshSettings(), port=2200)[-2:] == ["-p", "2200"]
