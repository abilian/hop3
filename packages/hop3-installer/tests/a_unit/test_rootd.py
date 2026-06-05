# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3-rootd installation (systemd unit generation).

Regression focus:
- The unit once crash-looped ~1620 times with ``status=203/EXEC`` because its
  ExecStart pointed at a non-existent binary; _resolve_daemon_command now fails
  loudly instead of writing a phantom ExecStart.
- The heavy sandbox (ProtectHome/ProtectSystem/CapabilityBoundingSet/seccomp)
  was incompatible with rootd's nft+nginx+systemctl executor role and is
  deferred to v0.6 (see notes/v0.6-rootd-hardening.md); these tests pin the
  current minimal-functional unit so the breaking directives don't silently
  creep back before that redesign.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_installer.common import ServiceStartError
from hop3_installer.server_installer import rootd

if TYPE_CHECKING:
    from pathlib import Path

# ---- _resolve_daemon_command ---------------------------------------------


def test_resolve_daemon_command_returns_existing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_venv = tmp_path / "venv"
    binary = fake_venv / "bin" / "hop3-rootd"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setattr(rootd, "VENV_DIR", fake_venv)

    assert rootd._resolve_daemon_command() == str(binary)


def test_resolve_daemon_command_raises_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No binary anywhere -> raise, never return a phantom path. Writing a unit
    with a non-existent ExecStart is what caused the 203/EXEC crash loop."""
    # Point VENV_DIR at an empty dir; the hard-coded fallbacks (/usr/local/bin,
    # /opt/..., /home/hop3/.venv) do not exist in the test environment.
    monkeypatch.setattr(rootd, "VENV_DIR", tmp_path / "empty-venv")
    with pytest.raises(ServiceStartError) as exc:
        rootd._resolve_daemon_command()
    assert "not found" in str(exc.value)


# ---- SERVICE_TEMPLATE rendering ------------------------------------------


def test_service_template_renders_with_daemon_command() -> None:
    cmd = "/home/hop3/venv/bin/hop3-rootd"
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
    """Guard the v0.6 decision: the subprocess-breaking hardening directives
    must NOT be present in the active unit until the hardening is redesigned and
    tested against nft + nginx + systemctl. If you re-add one, do it knowingly
    (and update notes/v0.6-rootd-hardening.md), not by accident."""
    rendered = rootd.SERVICE_TEMPLATE.format(daemon_command="/x/hop3-rootd")
    for breaking in (
        "ProtectHome=",
        "ProtectSystem=",
        "CapabilityBoundingSet=",
        "SystemCallFilter=",
        "MemoryDenyWriteExecute=",
    ):
        assert breaking not in rendered, f"{breaking} re-added without v0.6 review"
