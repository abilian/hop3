# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the subprocess `ssh -L` tunnel (core/ssh_tunnel.py).

These replace the old sshtunnel/paramiko-DSSKey compatibility guard: instead of
pinning a fragile library, we assert the command hop3-cli shells out and that
every failure path is loud (ssh exit surfaced, no silent re-pick, no false
success on a busy port, clean stop). No real ssh is spawned — ``subprocess.Popen``
and the readiness probe are stubbed; ssh's stderr is simulated by writing to the
temp-file sink Popen is handed.
"""

from __future__ import annotations

import subprocess

import pytest
from hop3_cli.core import ssh_tunnel as st
from hop3_cli.core.ssh_tunnel import SshTunnel, SshTunnelError


class _FakeProc:
    """Minimal ``subprocess.Popen`` stand-in for the readiness/stop paths."""

    def __init__(
        self, *, alive: bool = True, code: int = 0, term_hangs: bool = False
    ) -> None:
        self._alive = alive
        self._code = code
        self._term_hangs = term_hangs
        self.terminated = False
        self.killed = False
        self._waits = 0

    def poll(self):
        return None if self._alive else self._code

    def terminate(self) -> None:
        self.terminated = True
        if not self._term_hangs:
            self._alive = False

    def kill(self) -> None:
        self.killed = True
        self._alive = False

    def wait(self, timeout=None):
        self._waits += 1
        if self._term_hangs and self._waits == 1:
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout or 0.0)
        return self._code


def _patch_popen(monkeypatch, proc: _FakeProc, *, stderr: bytes = b"") -> list:
    """Replace Popen with a recorder returning ``proc``; return the call log.

    Mirrors real ssh by writing ``stderr`` into the temp-file sink that
    ``start()`` hands to Popen, so ``_read_stderr`` reads it back.
    """
    calls: list = []

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        sink = kwargs.get("stderr")
        if sink is not None and stderr:
            sink.write(stderr)
            sink.flush()
        return proc

    monkeypatch.setattr(st.subprocess, "Popen", fake_popen)
    return calls


def _stub_probe(monkeypatch, *sequence: bool) -> None:
    """Stub ``_port_open`` to yield each value in turn, then repeat the last.

    start() probes the port twice: once as a pre-flight (want free → False) and
    again during readiness (want ssh's listener → True), so tests pass a
    sequence like ``(False, True)``.
    """
    values = iter(sequence)
    state = {"last": sequence[-1]}

    def probe(_port):
        state["last"] = next(values, state["last"])
        return state["last"]

    monkeypatch.setattr(st, "_port_open", probe)


def _tunnel(**kw) -> SshTunnel:
    kw.setdefault("user", "root")
    return SshTunnel("host.example.com", 8000, **kw)


# --- argv construction (the security-critical surface) --------------------


def test_build_argv_minimal() -> None:
    argv = _tunnel(local_port=55000)._build_argv("root@host.example.com", 55000)
    assert argv == [
        "ssh", "-N",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-L", "127.0.0.1:55000:127.0.0.1:8000",
        "root@host.example.com",
    ]  # fmt: skip


def test_build_argv_with_key_and_nonstandard_port() -> None:
    argv = _tunnel(ssh_port=2222, key="/home/me/id_ed25519")._build_argv(
        "root@host.example.com", 55000
    )
    assert "-i" in argv
    assert argv[argv.index("-i") + 1] == "/home/me/id_ed25519"
    assert "-p" in argv
    assert argv[argv.index("-p") + 1] == "2222"
    # The validated target is always the final argument.
    assert argv[-1] == "root@host.example.com"


def test_default_ssh_port_omits_dash_p() -> None:
    argv = _tunnel(local_port=55000)._build_argv("root@host.example.com", 55000)
    assert "-p" not in argv


def test_no_key_omits_dash_i() -> None:
    argv = _tunnel(local_port=55000)._build_argv("root@host.example.com", 55000)
    assert "-i" not in argv


# --- validation / fail-loud ----------------------------------------------


def test_unsafe_target_rejected_before_spawn(monkeypatch) -> None:
    calls = _patch_popen(monkeypatch, _FakeProc())
    # A crafted ssh:// URL could yield user "-oProxyCommand=evil" → the assembled
    # target begins with '-' and ssh would read it as an option (RCE).
    tunnel = SshTunnel("host", 8000, user="-oProxyCommand=evil")
    with pytest.raises(SshTunnelError, match="unsafe SSH target"):
        tunnel.start()
    assert calls == []  # never spawned ssh


def test_busy_local_port_fails_loud_before_spawn(monkeypatch) -> None:
    # A listener already on the pinned port (e.g. a local Postgres on 5432)
    # must abort loudly, not be greenlit by the readiness probe as our forward.
    calls = _patch_popen(monkeypatch, _FakeProc())
    _stub_probe(monkeypatch, True)  # pre-flight sees a listener
    with pytest.raises(SshTunnelError, match="already in use"):
        _tunnel(local_port=5432).start()
    assert calls == []  # never spawned ssh


@pytest.mark.parametrize("bad", [0, 70000, "not-a-number"])
def test_bad_remote_port_rejected(bad) -> None:
    with pytest.raises(SshTunnelError):
        SshTunnel("host", bad, user="root")


@pytest.mark.parametrize("bad", [0, 70000, "nope"])
def test_bad_ssh_port_rejected(bad) -> None:
    with pytest.raises(SshTunnelError):
        SshTunnel("host", 8000, user="root", ssh_port=bad)


@pytest.mark.parametrize("bad", [0, 70000, "nope"])
def test_bad_local_port_rejected(bad) -> None:
    with pytest.raises(SshTunnelError):
        SshTunnel("host", 8000, user="root", local_port=bad)


def test_start_surfaces_ssh_stderr_when_it_exits(monkeypatch) -> None:
    proc = _FakeProc(alive=False, code=255)
    _patch_popen(monkeypatch, proc, stderr=b"Permission denied (publickey).")
    _stub_probe(monkeypatch, False)  # pre-flight free; poll() catches the exit
    with pytest.raises(SshTunnelError, match="Permission denied"):
        _tunnel(local_port=55000).start()


def test_popen_failure_releases_tempfile(monkeypatch) -> None:
    def boom(*_a, **_k):
        msg = "ssh"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(st.subprocess, "Popen", boom)
    _stub_probe(monkeypatch, False)  # pre-flight free, then Popen explodes
    tunnel = _tunnel(local_port=55000)
    with pytest.raises(FileNotFoundError):
        tunnel.start()
    assert tunnel._stderr is None  # sink closed + released on spawn failure


# --- readiness / lifecycle -----------------------------------------------


def test_start_ready_when_port_opens(monkeypatch) -> None:
    proc = _FakeProc(alive=True)
    calls = _patch_popen(monkeypatch, proc)
    _stub_probe(monkeypatch, False, True)  # free pre-flight, then ssh's listener

    tunnel = _tunnel(local_port=55000)
    tunnel.start()

    assert tunnel.is_active is True
    assert tunnel.is_alive() is True
    assert tunnel.local_bind_port == 55000
    # Spawned exactly once, list-argv, no shell, own process group.
    ((argv, kwargs),) = calls
    assert argv[0] == "ssh"
    assert kwargs.get("shell", False) is False
    assert kwargs["start_new_session"] is True


def test_start_auto_picks_free_local_port(monkeypatch) -> None:
    # The RPC-client path passes no local_port; start() must pick a free one and
    # thread it into the -L forward. (This branch is otherwise unexercised.)
    monkeypatch.setattr(st, "_pick_free_port", lambda: 51000)
    proc = _FakeProc(alive=True)
    calls = _patch_popen(monkeypatch, proc)
    _stub_probe(monkeypatch, False, True)

    tunnel = _tunnel()  # no local_port
    tunnel.start()

    assert tunnel.local_bind_port == 51000
    ((argv, _kwargs),) = calls
    assert "127.0.0.1:51000:127.0.0.1:8000" in argv


def test_readiness_timeout_stops_and_fails_loud(monkeypatch) -> None:
    proc = _FakeProc(alive=True)  # stays up but never listens
    _patch_popen(monkeypatch, proc)
    _stub_probe(monkeypatch, False)  # free pre-flight, then never opens
    monkeypatch.setattr(st.time, "sleep", lambda _s: None)

    tunnel = _tunnel(local_port=55000, ready_timeout=0.05)
    with pytest.raises(SshTunnelError, match="did not become ready"):
        tunnel.start()
    assert proc.terminated is True  # stop() ran, no leaked process


def test_stop_is_idempotent_and_closes_sink(monkeypatch) -> None:
    proc = _FakeProc(alive=True)
    _patch_popen(monkeypatch, proc)
    _stub_probe(monkeypatch, False, True)

    tunnel = _tunnel(local_port=55000)
    tunnel.start()
    sink = tunnel._stderr  # grab before stop() releases it
    assert sink is not None
    tunnel.stop()
    assert proc.terminated is True
    assert sink.closed is True  # the fd is actually closed, not just dropped
    assert tunnel._stderr is None
    assert tunnel.is_active is False
    assert tunnel.is_alive() is False
    tunnel.stop()  # second call must be a harmless no-op


def test_stop_escalates_to_sigkill(monkeypatch) -> None:
    proc = _FakeProc(alive=True, term_hangs=True)  # ignores SIGTERM
    _patch_popen(monkeypatch, proc)
    _stub_probe(monkeypatch, False, True)

    tunnel = _tunnel(local_port=55000)
    tunnel.start()
    tunnel.stop()
    assert proc.terminated is True
    assert proc.killed is True


def test_local_bind_port_before_start_raises() -> None:
    with pytest.raises(SshTunnelError, match="not started"):
        _ = _tunnel().local_bind_port
