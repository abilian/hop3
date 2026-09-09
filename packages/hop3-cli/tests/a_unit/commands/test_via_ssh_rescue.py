# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`--via-ssh` forces one invocation through the context's SSH route.

Once everyday traffic goes over HTTPS, the cases where it breaks — an expired
certificate, a proxy that is down, DNS pointing elsewhere — are exactly the
ones where the ordinary route is no use. The SSH route is still there; this
reaches for it deliberately, for one command.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.flags import parse_flags
from hop3_cli.config import Config
from hop3_cli.main import _force_bootstrap_route

SSH_TARGET = "root@prod.example.com"
PUBLIC = "https://prod.example.com"


class TestTheFlag:
    def test_is_parsed(self):
        flags, rest = parse_flags(["apps", "--via-ssh"])
        assert flags.via_ssh is True
        assert rest == ["apps"]

    def test_defaults_off(self):
        assert parse_flags(["apps"])[0].via_ssh is False

    def test_stops_at_a_run_program(self):
        """After `run <program>` the flags are the program's, not ours."""
        flags, rest = parse_flags(["run", "mycli", "--via-ssh"])
        assert flags.via_ssh is False
        assert rest == ["run", "mycli", "--via-ssh"]


class TestForcingTheRoute:
    def test_retargets_at_the_bootstrap_route(self):
        config = Config(data={})
        config.set_active_server(PUBLIC)
        config.set_active_bootstrap(f"ssh://{SSH_TARGET}")

        _force_bootstrap_route(config)

        assert config.get_api_url() == f"ssh://{SSH_TARGET}"

    def test_keeps_a_non_standard_port(self):
        config = Config(data={})
        config.set_active_server(PUBLIC)
        config.set_active_bootstrap("ssh://root@prod.example.com:2222")

        _force_bootstrap_route(config)

        assert config.get_api_url() == "ssh://root@prod.example.com:2222"

    def test_an_ssh_target_is_already_its_own_route(self):
        config = Config(data={})
        config.set_active_server(f"ssh://{SSH_TARGET}")

        _force_bootstrap_route(config)

        assert config.get_api_url() == f"ssh://{SSH_TARGET}"

    def test_refuses_when_there_is_no_route(self, capsys):
        """
        Loudly, not by falling back.

        Quietly using the ordinary route would look like the flag did nothing —
        on the one command the operator reached for it because nothing else
        worked.
        """
        config = Config(data={})
        config.set_active_server(PUBLIC)

        with pytest.raises(SystemExit) as excinfo:
            _force_bootstrap_route(config)

        assert excinfo.value.code != 0
        err = capsys.readouterr().err
        assert "no SSH bootstrap route" in err
        assert "hop3 login" in err, "names how to record one"
