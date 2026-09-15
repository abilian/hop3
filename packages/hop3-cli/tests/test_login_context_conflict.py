# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The refusal to repoint `default` has to be readable by the person who hit it.

Every deploy ends by writing `default` -> `http://<host>:8000` and then, until
this was fixed, telling the operator to run `hop3 login root@<host>` — which
that very context makes the CLI refuse. The refusal listed two addresses and
two remedies and never said the addresses were the same machine, so the first
reading is "I have two servers and Hop3 is confused", which is wrong.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local.login_cmd import _hostname, refuse_unnamed_retarget


class _Config:
    def __init__(self, current: str | None, override: str | None = None) -> None:
        self._current = current
        self._override = override

    def get_context_override(self) -> str | None:
        return self._override

    def get_context_server(self, _name: str) -> str | None:
        return self._current


def _refusal(current: str, incoming: str, capsys) -> str:
    with pytest.raises(SystemExit):
        refuse_unnamed_retarget(_Config(current), incoming)
    return capsys.readouterr().err


class TestOneServerReachedTwoWays:
    """The deployer's own doing, and the case an operator actually meets."""

    DEPLOYED = "http://hop3-dev.example.com:8000"
    OVER_SSH = "ssh://root@hop3-dev.example.com"

    def test_it_says_both_reach_the_same_host(self, capsys):
        assert "Both reach hop3-dev.example.com" in _refusal(
            self.DEPLOYED, self.OVER_SSH, capsys
        )

    def test_it_says_where_the_old_one_came_from(self, capsys):
        """Otherwise the reader has no idea who wrote a context they never made."""
        assert "written when the server was deployed" in _refusal(
            self.DEPLOYED, self.OVER_SSH, capsys
        )

    def test_both_remedies_survive(self, capsys):
        err = _refusal(self.DEPLOYED, self.OVER_SSH, capsys)
        assert "--context <name>" in err
        assert "hop3 context remove default" in err


class TestGenuinelyDifferentServers:
    def test_no_same_host_claim(self, capsys):
        err = _refusal("https://a.example.com", "ssh://root@b.example.com", capsys)
        assert "Both reach" not in err
        assert "--context <name>" in err


class TestWhatPassesThrough:
    def test_a_named_context_is_the_operators_choice(self):
        refuse_unnamed_retarget(_Config("http://a:8000", override="prod"), "ssh://b")

    def test_re_logging_the_same_address_is_a_token_refresh(self):
        refuse_unnamed_retarget(_Config("ssh://root@a"), "ssh://root@a")

    def test_nothing_to_conflict_with(self):
        refuse_unnamed_retarget(_Config(None), "ssh://root@a")


class TestHostname:
    @pytest.mark.parametrize(
        ("url", "host"),
        [
            ("http://h.example.com:8000", "h.example.com"),
            ("ssh://root@h.example.com", "h.example.com"),
            ("h.example.com:8000", "h.example.com"),
            ("", ""),
        ],
    )
    def test_the_host_is_found_however_the_address_is_spelled(self, url, host):
        assert _hostname(url) == host
