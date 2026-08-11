# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for known_hosts maintenance.

`add_host_key` used to build a shell command string with the host and port
interpolated into it and `>> known_hosts 2>/dev/null` appended, so a host with a
shell character in it did something other than what was intended and a failing
scan reported only False.
"""

from __future__ import annotations

import subprocess

import pytest
from hop3_testing.util.ssh import SSHKeyManager


@pytest.fixture
def manager(tmp_path):
    return SSHKeyManager(known_hosts_path=tmp_path / ".ssh" / "known_hosts")


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_the_scanned_key_is_appended(manager, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: _completed(stdout="host ssh-ed25519 AAA\n")
    )

    assert manager.add_host_key("example.com") is True
    assert manager.known_hosts_path.read_text() == "host ssh-ed25519 AAA\n"


def test_the_host_is_an_argument_not_a_command(manager, monkeypatch):
    """The value reaches ssh-keyscan whole, whatever is in it."""
    seen: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        seen.append(cmd)
        return _completed(stdout="k\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager.add_host_key("evil; rm -rf /", port=2222)

    assert seen == [
        ["ssh-keyscan", "-p", "2222", "-t", "ed25519,rsa", "evil; rm -rf /"]
    ]
    assert all(isinstance(part, str) for part in seen[0])


def test_a_failed_scan_says_why(manager, monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _completed(stderr="Connection timed out", returncode=1),
    )

    assert manager.add_host_key("unreachable.example") is False
    assert "Connection timed out" in capsys.readouterr().out
    # Nothing half-written: a failed scan must not leave an entry.
    assert not manager.known_hosts_path.exists()


def test_an_empty_scan_is_a_failure_not_an_empty_entry(manager, monkeypatch):
    """rc=0 with no key on stdout used to append nothing and report success."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(stdout="\n"))

    assert manager.add_host_key("silent.example") is False


def test_a_key_without_a_trailing_newline_does_not_join_the_next_line(
    manager, monkeypatch
):
    manager.known_hosts_path.parent.mkdir(parents=True)
    manager.known_hosts_path.write_text("existing ssh-rsa BBB\n")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: _completed(stdout="new ssh-ed25519 AAA")
    )

    manager.add_host_key("example.com")

    assert manager.known_hosts_path.read_text().splitlines() == [
        "existing ssh-rsa BBB",
        "new ssh-ed25519 AAA",
    ]
