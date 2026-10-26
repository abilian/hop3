# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
An unnamed login will not repoint the `default` context.

An unnamed login cannot tell "I replaced my server" from "I have two servers
now", and quietly answering with the first is how `hop3 apps` starts
reporting on the wrong machine. A second, different address logged in without
`--context` is refused, not taken over. The same address is a token refresh
and passes through.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local.login_cmd import (
    record_server_login,
    refuse_unnamed_retarget,
)
from hop3_cli.config import DEFAULT_CONTEXT_NAME, Config
from hop3_cli.core import credential_store as cs

A = "ssh://root@a.example.com"
B = "ssh://root@b.example.com"


def config_with_default(address: str, **cli) -> Config:
    return Config(
        data={"contexts": {DEFAULT_CONTEXT_NAME: {"server": address}}, "cli": cli}
    )


class TestUnnamedRetargetIsRefused:
    def test_a_different_address_is_refused(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            refuse_unnamed_retarget(config_with_default(A), B)
        assert excinfo.value.code != 0
        err = capsys.readouterr().err
        assert A in err, "names the address it would have replaced"
        assert B in err, "names the address being logged in"
        assert "--context" in err, "offers the naming escape"
        assert f"context remove {DEFAULT_CONTEXT_NAME}" in err, "offers the other"

    def test_the_same_address_is_a_refresh(self):
        refuse_unnamed_retarget(config_with_default(A), A)  # must not raise

    def test_a_first_login_is_never_refused(self):
        refuse_unnamed_retarget(Config(data={}), A)  # must not raise

    def test_an_explicit_context_repoints_deliberately(self):
        """`--context prod` is the operator naming it; that is not a takeover."""
        config = config_with_default(A)
        config._context_override = "prod"
        refuse_unnamed_retarget(config, B)  # must not raise

    def test_explicit_default_is_also_deliberate(self):
        """Typing `--context default` says which one you mean."""
        config = config_with_default(A)
        config._context_override = DEFAULT_CONTEXT_NAME
        refuse_unnamed_retarget(config, B)  # must not raise


class TestTheGuardIsWired:
    """
    Testing `refuse_unnamed_retarget` alone proves nothing about `record_server_login`.

    Deleting the call site left every direct test of the guard passing, so these
    drive the real writer.
    """

    def test_record_server_login_refuses_an_unnamed_retarget(self, tmp_path, capsys):
        config = Config(
            data={"contexts": {DEFAULT_CONTEXT_NAME: {"server": A}}},
            config_file=tmp_path / "config.toml",
        )
        with pytest.raises(SystemExit):
            record_server_login(config, B, "eyJtok")
        assert A in capsys.readouterr().err

    def test_nothing_is_written_when_it_refuses(self, tmp_path):
        """The guard runs before the token store, so a refusal leaves no trace."""
        config = Config(
            data={"contexts": {DEFAULT_CONTEXT_NAME: {"server": A}}},
            config_file=tmp_path / "config.toml",
        )
        with pytest.raises(SystemExit):
            record_server_login(config, B, "eyJtok")
        assert cs.get_token(B) is None
        assert config.get_context_server(DEFAULT_CONTEXT_NAME) == A

    def test_a_refresh_of_the_same_address_goes_through(self, tmp_path):
        config = Config(
            data={"contexts": {DEFAULT_CONTEXT_NAME: {"server": A}}},
            config_file=tmp_path / "config.toml",
        )
        record_server_login(config, A, "eyJfresh")
        assert cs.get_token(A) == "eyJfresh"
