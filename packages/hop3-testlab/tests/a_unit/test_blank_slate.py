# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Blank-slate rebuild: full-suite runs reinstall the Hetzner OS first.

Reproducibility: every run starts from an identical, known state instead of
inheriting leaked apps/addons/disk. The rebuild re-injects an SSH key (explicit
ssh_key_name, or auto-derived from [ssh] key_path); if none can be resolved it
aborts loudly rather than silently running against a dirty server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hop3_testlab import worker
from hop3_testlab.cloud_config import CloudConfig


def _cfg(
    ssh_key_name: str | None = None, ssh_key_path: str | None = None
) -> CloudConfig:
    return CloudConfig(
        hetzner_token="tok",
        hetzner_server_id=42,
        hetzner_image="ubuntu-24.04",
        ssh_key_path=ssh_key_path,
        hetzner_ssh_key_name=ssh_key_name,
    )


def test_run_blockers_surfaces_resolver_failure(monkeypatch):
    # The web trigger uses this to refuse up-front (with the real reason) instead
    # of spawning a run that aborts unseen. Whatever the SSH-key resolver raises
    # — a missing/unregistered key — is surfaced as the blocker.
    monkeypatch.setattr(worker, "load_cloud_config", _cfg)

    def _boom(cfg):
        msg = "key 'x' is not registered in your Hetzner project"
        raise RuntimeError(msg)

    monkeypatch.setattr(worker, "_resolve_hetzner_ssh_key", _boom)
    blocker = worker.run_blockers("hetzner", None)
    assert blocker is not None
    assert "not registered" in blocker


def test_run_blockers_clear_when_key_resolves(monkeypatch):
    monkeypatch.setattr(worker, "load_cloud_config", _cfg)
    monkeypatch.setattr(worker, "_resolve_hetzner_ssh_key", lambda cfg: None)
    assert worker.run_blockers("hetzner", None) is None


def test_run_blockers_skip_resolver_for_per_app_and_docker(monkeypatch):
    # per-app + docker never blank-slate, so the resolver is never consulted.
    def _fail(cfg):
        pytest.fail("resolver must not be called")

    monkeypatch.setattr(worker, "_resolve_hetzner_ssh_key", _fail)
    assert worker.run_blockers("hetzner", ["apps/x"]) is None  # per-app: live server
    assert worker.run_blockers("docker", None) is None  # docker: fresh container


def test_rebuild_purges_host_key_and_waits_for_ssh_command():
    manager = MagicMock()
    manager.wait_for_ssh_ready.return_value = True
    with (
        patch("hop3_testing.system_tests.hetzner.HetznerManager", return_value=manager),
        patch.object(worker, "_purge_known_host") as purge,
        patch.object(worker, "_wait_ssh_command_ready", return_value=True) as ready,
    ):
        worker._rebuild_blank_slate(_cfg("hop3-ci"), "203.0.113.7")
    manager.rebuild_server.assert_called_once()
    # The rebuild changed the box's host key -> drop the stale known_hosts entry,
    # then confirm the ssh binary (what the deploy uses) actually answers.
    purge.assert_called_once_with("203.0.113.7")
    ready.assert_called_once()


def test_rebuild_raises_if_ssh_command_never_ready():
    manager = MagicMock()
    manager.wait_for_ssh_ready.return_value = True  # paramiko ok...
    with (
        patch("hop3_testing.system_tests.hetzner.HetznerManager", return_value=manager),
        patch.object(worker, "_purge_known_host"),
        patch.object(worker, "_wait_ssh_command_ready", return_value=False),  # ...but ssh isn't
        pytest.raises(RuntimeError, match="never answered"),
    ):
        worker._rebuild_blank_slate(_cfg("hop3-ci"), "203.0.113.7")


def test_configure_ssh_identity_writes_idempotent_host_block(tmp_path, monkeypatch):
    # The deploy's ssh passes no -i; an ~/.ssh/config IdentityFile makes it use the
    # credential key for the host (else 'Permission denied (publickey)' on a server
    # whose runtime user has no default key).
    monkeypatch.setenv("HOME", str(tmp_path))  # Path.home() -> tmp
    worker._configure_ssh_identity("203.0.113.7", "/data/keys/k.key")
    config = tmp_path / ".ssh" / "config"
    text = config.read_text()
    assert "Host 203.0.113.7" in text
    assert "IdentityFile /data/keys/k.key" in text
    assert oct(config.stat().st_mode)[-3:] == "600"

    # Rewritten each run: a second call replaces the block, never duplicates it.
    worker._configure_ssh_identity("203.0.113.7", "/data/keys/k2.key")
    text2 = config.read_text()
    assert text2.count("Host 203.0.113.7") == 1
    assert "k2.key" in text2
    assert "k.key" not in text2


def test_purge_known_host_runs_ssh_keygen_remove():
    with patch("hop3_testlab.worker.subprocess.run") as run:
        worker._purge_known_host("203.0.113.7")
    run.assert_called_once()
    assert run.call_args[0][0] == ["ssh-keygen", "-R", "203.0.113.7"]


def test_wait_ssh_command_ready_retries_then_succeeds(monkeypatch):
    from types import SimpleNamespace

    results = [SimpleNamespace(returncode=255), SimpleNamespace(returncode=0)]
    with patch("hop3_testlab.worker.subprocess.run", side_effect=results) as run:
        ok = worker._wait_ssh_command_ready("203.0.113.7", "/k", attempts=3, delay=0)
    assert ok is True
    assert run.call_count == 2
    cmd = run.call_args[0][0]
    assert cmd[0] == "ssh"
    assert cmd[cmd.index("-i") + 1] == "/k"  # uses the credential's key
    assert cmd[-2] == "root@203.0.113.7"  # connects as the deploy does


def test_wait_ssh_command_ready_gives_up():
    fail = type("R", (), {"returncode": 255})()
    with patch("hop3_testlab.worker.subprocess.run", return_value=fail):
        assert worker._wait_ssh_command_ready("h", None, attempts=2, delay=0) is False


def test_rebuild_raises_if_ssh_never_ready():
    manager = MagicMock()
    manager.wait_for_ssh_ready.return_value = False
    with (
        patch("hop3_testing.system_tests.hetzner.HetznerManager", return_value=manager),
        pytest.raises(RuntimeError),
    ):
        worker._rebuild_blank_slate(_cfg("hop3-ci"), "203.0.113.7")


def _wire(monkeypatch, calls):
    monkeypatch.setattr(worker, "_resolve_run_target", lambda t: ("1.2.3.4", None, {}))
    monkeypatch.setattr(worker, "load_cloud_config", lambda: _cfg("hop3-ci"))
    monkeypatch.setattr(
        worker, "_rebuild_blank_slate", lambda cfg, host: calls.append("rebuild")
    )
    monkeypatch.setattr(worker, "_run_engine", lambda *a, **k: calls.append("engine"))


def test_blank_slate_hetzner_run_rebuilds_first(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor("hetzner", "nightly", apps=None, blank_slate=True)
    assert calls == ["rebuild", "engine"]  # blank slate, then run


def test_dispatched_profile_build_rebuilds_even_with_apps(monkeypatch):
    # Review #2/#7 regression: a dispatched/nightly profile build resolves a
    # NON-empty apps list AND is a clean run (blank_slate=True), so it must STILL
    # rebuild. The old `not apps` gate silently skipped the rebuild here.
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor(
        "hetzner", "nightly", apps=["apps/real-apps-nix/x"], blank_slate=True
    )
    assert calls == ["rebuild", "engine"]


def test_per_app_rerun_skips_rebuild(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor(
        "hetzner", "nightly", apps=["apps/real-apps-docker/x"], blank_slate=False
    )
    assert calls == ["engine"]  # ad-hoc re-run against the live server


def test_ssh_run_passes_credential_key_to_engine(monkeypatch):
    # The engine's paramiko connect needs the key as --ssh-key (else 'No
    # authentication methods' for a server user with no default key/agent).
    captured: dict = {}
    monkeypatch.setattr(
        worker, "_resolve_run_target", lambda t: ("1.2.3.4", "/data/keys/k.key", {})
    )
    monkeypatch.setattr(worker, "load_cloud_config", lambda: _cfg("hop3-ci"))
    monkeypatch.setattr(worker, "_configure_ssh_identity", lambda host, key: None)
    monkeypatch.setattr(
        worker, "_run_engine", lambda target, cmd, env, cwd: captured.update(cmd=cmd)
    )
    worker._default_executor("hetzner", "nightly", apps=["apps/x"], blank_slate=False)
    cmd = captured["cmd"]
    assert cmd[cmd.index("--ssh-key") + 1] == "/data/keys/k.key"


def test_engine_env_carries_a_git_identity(monkeypatch):
    # The engine `git commit`s each test app; without an identity it exits 128 on a
    # server user that has none.
    captured: dict = {}
    monkeypatch.setattr(worker, "_resolve_run_target", lambda t: ("1.2.3.4", None, {}))
    monkeypatch.setattr(worker, "load_cloud_config", lambda: _cfg("hop3-ci"))
    monkeypatch.setattr(
        worker, "_run_engine", lambda target, cmd, env, cwd: captured.update(env=env)
    )
    worker._default_executor("hetzner", "nightly", apps=["apps/x"], blank_slate=False)
    env = captured["env"]
    assert env["GIT_AUTHOR_EMAIL"]
    assert env["GIT_COMMITTER_NAME"]


def test_other_ssh_host_does_not_rebuild(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor("box.example.com", "nightly", apps=None, blank_slate=True)
    assert calls == ["engine"]  # only the managed "hetzner" target is rebuilt


def test_docker_target_does_not_rebuild(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        worker, "_rebuild_blank_slate", lambda cfg, host: calls.append("rebuild")
    )
    monkeypatch.setattr(worker, "_run_engine", lambda *a, **k: calls.append("engine"))
    worker._default_executor("docker", "nightly", apps=None, blank_slate=True)
    assert "rebuild" not in calls
