# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The closing banner is the first thing an operator reads, and it was wrong.

It told them to run `hop3 login root@<host>` after the deploy had itself
written the `default` context — so the CLI refused the command the banner had
just given. Fixing that by announcing "already signed in" replaced one problem
with several: it advertised `http://<host>:8000`, the API port in clear; it
offered `default` on one line and asked for `--context <name>` on the next
without saying they were the same command; and it never said that `--context`
names a context the operator invents. Reported line by line from a real run
against hop3-dev.abilian.com.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import MagicMock

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

HOST = "hop3-dev.example.com"


def _banner(*, docker: bool = False, admin_created: bool = True) -> str:
    d = Deployer(DeployConfig(host=HOST, use_docker=docker), MagicMock())
    d.quiet = True
    d.admin_user_created = admin_created
    out = io.StringIO()
    with redirect_stdout(out):
        d._print_how_to_log_in()
    return out.getvalue()


def _completion() -> str:
    d = Deployer(DeployConfig(host=HOST, use_docker=False), MagicMock())
    d.quiet = False
    d.backend.get_server_url = lambda: "http://hop3-dev.example.com:8000"
    out = io.StringIO()
    with redirect_stdout(out):
        d._print_completion_message()
    return out.getvalue()


class TestTheApiPortIsNeverAdvertised:
    """
    `hop3-server` binds 0.0.0.0:8000 in clear. Printing it as the server's
    URL invites reaching it from off the box, with a bearer token following.
    """

    def test_the_banner_does_not_name_it(self):
        assert ":8000" not in _banner()

    def test_the_completion_message_gives_the_https_url(self):
        assert "Server URL: https://hop3-dev.example.com" in _completion()

    def test_the_completion_message_does_not_name_the_api_port(self):
        assert ":8000" not in _completion()


class TestOneCommandWithVariations:
    """
    Three shapes for one operation left the reader assembling it themselves:
    a bare login, then `--context <name>` on its own, then a third spelling
    for the browser.
    """

    def test_the_login_is_given_in_full(self):
        assert f"hop3 login root@{HOST}" in _banner()

    def test_the_named_variant_is_the_same_command_plus_a_flag(self):
        assert f"hop3 login root@{HOST} --context " in _banner()

    def test_the_browser_variant_is_described_as_a_flag_on_those(self):
        banner = _banner()
        assert "--browser" in banner
        assert "either command" in banner


class TestItSaysWhatAContextIs:
    def test_it_names_the_context_the_plain_login_writes(self):
        assert "'default'" in _banner()

    def test_it_says_hop3_refuses_rather_than_moving_an_existing_default(self):
        """The operator's own 'default' is not silently repointed."""
        assert "says so rather" in _banner()

    def test_it_says_the_name_is_the_operators_to_choose(self):
        assert "name of your choosing" in _banner()


class TestThePasswordNote:
    def test_it_says_what_to_re_run(self):
        """'re-run with --verbose' never said re-run *what*."""
        assert "re-run this deploy with --verbose" in _banner()

    def test_it_says_the_password_is_not_needed_to_sign_in(self):
        assert "do not need it to sign in" in _banner()

    def test_it_still_gives_the_way_to_set_one(self):
        assert "hop3 user set-password admin --stdin" in _banner()

    def test_nothing_about_a_password_when_none_was_created(self):
        assert "Admin password" not in _banner(admin_created=False)


def test_a_docker_target_gets_no_login_block():
    """Its CLI was configured in place; there is no SSH target to name."""
    assert _banner(docker=True) == ""
