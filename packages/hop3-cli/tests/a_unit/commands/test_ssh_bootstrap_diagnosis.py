# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A failed SSH bootstrap must be diagnosed by Hop3, not by `su`.

Every bootstrap operation wraps its remote call in `su - hop3 -c '…'`, which
only root can do. Connecting as an ordinary admin account — the normal way to
administer a server — therefore failed with `su`'s own words:

    Failed to get SSH token: su: Authentication failure

which names neither the command that ran nor the requirement it broke. The
error now states the input, the command, its output, and the way forward.
"""

from __future__ import annotations

import subprocess

import pytest
from hop3_cli.commands.local import ssh_ops
from hop3_cli.commands.local.ssh_ops import BootstrapError


def completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["ssh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def su_fails(monkeypatch):
    """Every SSH call answers the way `su` does for a non-root caller."""
    calls: list[tuple[str, str]] = []

    def fake(ssh_target, remote_cmd, *, input=None):
        calls.append((ssh_target, remote_cmd))
        return completed(1, stderr="su: Authentication failure")

    monkeypatch.setattr(ssh_ops, "_run_ssh", fake)
    return calls


def test_non_root_failure_names_command_output_and_requirement(su_fails):
    with pytest.raises(BootstrapError) as excinfo:
        ssh_ops.get_ssh_token("john@prod.example.com")
    message = str(excinfo.value)

    assert "john" in message  # the input
    assert "prod.example.com" in message
    assert "admin:ssh-token" in message  # the command that ran
    assert "su: Authentication failure" in message  # its output
    assert "needs" in message  # the requirement
    assert "root" in message
    assert "hop3 login --ssh root@prod.example.com" in message  # the way forward


def test_root_failure_does_not_advise_connecting_as_root(su_fails):
    """Already root: repeating the advice would be noise, and wrong."""
    with pytest.raises(BootstrapError) as excinfo:
        ssh_ops.get_ssh_token("root@prod.example.com")
    message = str(excinfo.value)
    assert "su: Authentication failure" in message
    assert "hop3 login --ssh root@" not in message


def test_a_bare_host_is_reported_as_root(su_fails):
    """`_build_ssh_url` substitutes root for a bare host, so the error must agree."""
    with pytest.raises(BootstrapError) as excinfo:
        ssh_ops.get_ssh_token("prod.example.com")
    assert "'root'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("operation", "args"),
    [
        (ssh_ops.get_ssh_token, ()),
        (ssh_ops.get_token_via_ssh, ("admin",)),
        (ssh_ops.get_magic_link_via_ssh, ("admin",)),
        (ssh_ops.create_admin_via_ssh, ("admin", "a@b.c", "pw")),
    ],
)
def test_every_bootstrap_operation_is_diagnosed(su_fails, operation, args):
    """All four shared one copied error path; all four must carry the diagnosis."""
    with pytest.raises(BootstrapError) as excinfo:
        operation("john@prod.example.com", *args)
    message = str(excinfo.value)
    assert "  ran:  ssh john@prod.example.com" in message
    assert "  got:  su: Authentication failure" in message


class TestHop3AccountIsRefused:
    """`hop3@host` cannot work: its key's forced command prepends hop3-server."""

    def test_refused_before_any_ssh_call(self, monkeypatch):
        connected = []

        def record(*a, **k):
            connected.append(a)
            return completed(0, stdout="eyJ.a.b")

        monkeypatch.setattr(ssh_ops, "_run_ssh", record)
        with pytest.raises(BootstrapError) as excinfo:
            ssh_ops.get_ssh_token("hop3@prod.example.com")
        message = str(excinfo.value)
        assert connected == [], "must be refused before any SSH call"
        assert "deploy key" in message
        assert "hop3 login --ssh root@prod.example.com" in message

    def test_root_is_not_refused(self, su_fails):
        # Reaches the SSH call (and fails there), rather than being refused.
        with pytest.raises(BootstrapError):
            ssh_ops.get_ssh_token("root@prod.example.com")
        assert su_fails, "root should have reached the SSH call"
