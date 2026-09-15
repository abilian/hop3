# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The deploy banner must name a way in that works, for both surfaces.

Regression: it led with the generated admin password and offered
`hop3 admin set-password` to rotate it — a command that does not exist. The
password opens neither surface on its own, and SSH access (which the operator
just deployed over) opens both, so that is what the banner teaches.
"""

from __future__ import annotations

import contextlib
import io
from types import SimpleNamespace

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


def _banner(*, created: bool = True, verbose: bool = False, **overrides) -> str:
    settings = {"host": "server.example.com", "admin_password": "s3cret", **overrides}
    deployer = Deployer(DeployConfig(**settings), backend=SimpleNamespace())  # type: ignore[arg-type]
    deployer.admin_user_created = created
    deployer.verbose = verbose

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        deployer._print_how_to_log_in()
    return buf.getvalue()


def test_gives_one_command_and_one_variation_of_it():
    """
    The dashboard is prose, not a co-equal bullet — still true. What changed:
    the named-context form now gets a line, because it is the way out when the
    operator already has a `default` pointing elsewhere, and burying it in
    prose left them assembling the command themselves.

    Both lines are the same command; the second only adds a flag. The browser
    is a third flag and gets no line of its own, since spelling it as a full
    command raised "is it `--browser` or `--browser --context …`?".
    """
    out = _banner()
    lines = [ln.strip() for ln in out.splitlines() if ln.startswith("  hop3 login")]
    assert lines == [
        "hop3 login root@server.example.com",
        "hop3 login root@server.example.com --context hop3-dev",
    ]
    assert "--browser" in out
    assert "hop3 login --browser" not in out


def test_offers_a_reset_that_exists():
    out = _banner()
    assert "hop3 user set-password admin --stdin" in out
    # The command the banner used to advertise never existed.
    assert "admin set-password" not in out


def test_password_is_all_or_nothing():
    assert "s3cret" not in _banner()
    assert "Admin password: s3cret" in _banner(verbose=True)


def test_existing_admin_gets_no_password_block():
    out = _banner(created=False)
    assert "Admin password" not in out
    assert "hop3 login root@" in out  # still tells them how to get in


def test_docker_target_has_no_ssh_target_to_name():
    assert _banner(use_docker=True, host=None) == ""
