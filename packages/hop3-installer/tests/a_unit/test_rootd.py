# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for hop3-rootd installation (systemd unit generation).

Regression focus:
- The unit once crash-looped ~1620 times with ``status=203/EXEC`` because its
  ExecStart pointed at a non-existent binary; _resolve_daemon_command now fails
  loudly instead of writing a phantom ExecStart.
- The heavy sandbox (ProtectHome/ProtectSystem/CapabilityBoundingSet/seccomp)
  was incompatible with rootd's nft+nginx+systemctl executor role and is
  deferred to v0.6 (see notes/security/rootd-hardening.md); these tests pin the
  current minimal-functional unit so the breaking directives don't silently
  creep back before that redesign.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

import pytest
from hop3_installer.common import ServiceStartError
from hop3_installer.server_installer import rootd

if TYPE_CHECKING:
    from pathlib import Path

# ---- _resolve_daemon_command ---------------------------------------------


def test_resolve_daemon_command_returns_the_root_owned_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "opt" / "bin" / "hop3-rootd"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setattr(rootd, "ROOTD_BIN", binary)

    assert rootd._resolve_daemon_command() == str(binary)


def test_resolve_daemon_command_never_falls_back_to_the_server_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    No binary in the root-owned venv -> raise, never a phantom path (the
    203/EXEC crash loop) and never the server venv's copy, which hop3 can write.
    """
    monkeypatch.setattr(rootd, "ROOTD_BIN", tmp_path / "opt" / "bin" / "hop3-rootd")
    old = tmp_path / "home" / "hop3" / "venv" / "bin" / "hop3-rootd"
    old.parent.mkdir(parents=True)
    old.write_text("#!/usr/bin/env python3\n")
    with pytest.raises(ServiceStartError) as exc:
        rootd._resolve_daemon_command()
    assert "not found" in str(exc.value)
    assert str(old) not in str(exc.value)


def test_the_daemon_runs_from_the_root_owned_venv() -> None:
    """The unit, the Docker program and the installer agree on one path."""
    from hop3_installer.constants import ROOTD_BIN  # ruff:ignore[import-outside-top-level]
    from hop3_installer.deployer.backends.docker import (  # ruff:ignore[import-outside-top-level]
        SUPERVISOR_CONFIG,
    )

    assert str(ROOTD_BIN) == "/opt/hop3-rootd/bin/hop3-rootd"
    assert f"command={ROOTD_BIN} --socket-path" in SUPERVISOR_CONFIG
    assert "/home/hop3/venv/bin/hop3-rootd" not in SUPERVISOR_CONFIG


def test_an_existing_unit_is_moved_to_the_root_owned_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A server installed before 0.8.1 has a unit running the daemon from hop3's
    venv. setup_rootd rewrites it on every run, then reloads and restarts.
    """
    binary = tmp_path / "opt" / "bin" / "hop3-rootd"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env python3\n")
    unit = tmp_path / "hop3-rootd.service"
    unit.write_text("[Service]\nExecStart=/home/hop3/venv/bin/hop3-rootd\n")
    state = tmp_path / "state"
    for name, value in {
        "ROOTD_BIN": binary,
        "SERVICE_PATH": unit,
        "SOCKET_PATH": tmp_path / "hop3-rootd.socket",
        "LOGROTATE_PATH": tmp_path / "logrotate",
        "STATE_DIR": state,
        "STATE_FILE": state / "state.json",
        "LOG_DIR": tmp_path / "log",
        "RUNTIME_DIR": tmp_path / "run",
        "BIND_ALLOWLIST_FILE": state / "bind-allowlist",
        "CGROUP_CONTROLLERS": tmp_path / "cgroup.controllers",
        "SUDOERS_FRAGMENT": tmp_path / "sudoers",
    }.items():
        monkeypatch.setattr(rootd, name, value)
    (state).mkdir()
    (state / "state.json").write_text("{}")
    commands: list[list[str]] = []

    def run_cmd(cmd, **_kw):
        commands.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rootd, "run_cmd", run_cmd)
    monkeypatch.setattr(rootd, "has_systemd", lambda: True)
    monkeypatch.setattr(rootd, "cmd_exists", lambda _name: False)
    monkeypatch.setattr(rootd, "_verify_rootd_running", lambda: None)

    rootd.setup_rootd()

    assert f"ExecStart={binary}" in unit.read_text()
    assert "/home/hop3/venv" not in unit.read_text()
    reload_at = commands.index(["systemctl", "daemon-reload"])
    restart = ["systemctl", "restart", "hop3-rootd.socket", "hop3-rootd.service"]
    assert reload_at < commands.index(restart)


# ---- SERVICE_TEMPLATE rendering ------------------------------------------


def test_service_template_renders_with_daemon_command() -> None:
    cmd = "/opt/hop3-rootd/bin/hop3-rootd"
    rendered = rootd.SERVICE_TEMPLATE.format(daemon_command=cmd)
    assert f"ExecStart={cmd}" in rendered
    assert "Type=notify" in rendered
    # Restart loop is capped so a persistent failure surfaces (the 1620x class).
    assert "StartLimitBurst=" in rendered
    # systemd manages the runtime/state/log dirs.
    assert "RuntimeDirectory=hop3-rootd" in rendered
    assert "{" not in rendered
    assert "}" not in rendered


def test_service_template_is_minimal_pending_v06_hardening() -> None:
    """
    Guard the v0.6 decision: the subprocess-breaking hardening directives
    must NOT be present in the active unit until the hardening is redesigned and
    tested against nft + nginx + systemctl. If you re-add one, do it knowingly
    (and update notes/security/rootd-hardening.md), not by accident.
    """
    rendered = rootd.SERVICE_TEMPLATE.format(daemon_command="/x/hop3-rootd")
    for breaking in (
        "ProtectHome=",
        "ProtectSystem=",
        "CapabilityBoundingSet=",
        "SystemCallFilter=",
        "MemoryDenyWriteExecute=",
    ):
        assert breaking not in rendered, f"{breaking} re-added without v0.6 review"


def test_unit_keeps_cgroup_and_mount_ops_working() -> None:
    """
    ADR 046 P2 (§18): the cgroup.*/mount.* ops rely on the unit NOT setting
    ProtectControlGroups (would block cgroup writes) or PrivateMounts (would hide
    bind/tmpfs mounts from the app's namespace). Guard against a premature re-add.
    """
    rendered = rootd.SERVICE_TEMPLATE.format(daemon_command="/x/hop3-rootd")
    for breaking in ("ProtectControlGroups=", "PrivateMounts="):
        assert breaking not in rendered, f"{breaking} would break ADR 046 P2 ops"


# ---- _ensure_bind_allowlist ----------------------------------------------


def test_ensure_bind_allowlist_creates_default_deny(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "bind-allowlist"
    monkeypatch.setattr(rootd, "BIND_ALLOWLIST_FILE", f)
    rootd._ensure_bind_allowlist()
    assert f.exists()
    content = f.read_text()
    assert "DEFAULT-DENY" in content
    # No non-comment, non-blank lines → deny-all (nothing pre-allowed).
    active = [
        ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")
    ]
    assert active == []


def test_ensure_bind_allowlist_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator-edited allow-list must never be clobbered on re-install."""
    f = tmp_path / "bind-allowlist"
    f.write_text("/srv/shared\n")
    monkeypatch.setattr(rootd, "BIND_ALLOWLIST_FILE", f)
    rootd._ensure_bind_allowlist()
    assert f.read_text() == "/srv/shared\n"


# ---- _check_cgroup_v2 ----------------------------------------------------


def test_check_cgroup_v2_present_is_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    controllers = tmp_path / "cgroup.controllers"
    controllers.write_text("memory cpu pids")
    monkeypatch.setattr(rootd, "CGROUP_CONTROLLERS", controllers)
    rootd._check_cgroup_v2()  # must not raise
    out = capsys.readouterr()
    assert "present" in (out.out + out.err)


def test_check_cgroup_v2_absent_warns_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rootd, "CGROUP_CONTROLLERS", tmp_path / "nope")
    rootd._check_cgroup_v2()  # non-fatal: a Docker-only / no-limits box is fine
    out = capsys.readouterr()
    assert "no cgroup v2" in (out.out + out.err)


# ---- docker (supervisor) launch ------------------------------------------


def test_docker_supervisor_config_launches_rootd() -> None:
    """
    rootd must be launched in the Docker deploy too (no systemd as PID 1, so
    supervisor is the process manager). Omitting it meant the rootd socket never
    appeared and EVERY app deploy's proxy reload failed with 'hop3-rootd is not
    reachable' -- the c_e2e regression this guards against.
    """
    from hop3_installer.deployer.backends.docker import (  # ruff:ignore[import-outside-top-level]
        SUPERVISOR_CONFIG,
    )

    assert "[program:hop3-rootd]" in SUPERVISOR_CONFIG
    assert "hop3-rootd --socket-path /run/hop3-rootd/socket" in SUPERVISOR_CONFIG
