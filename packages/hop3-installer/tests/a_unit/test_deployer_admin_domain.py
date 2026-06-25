# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The deployer must persist ADMIN_DOMAIN into the server config.

Regression: `hop3-deploy --admin-domain X` (or `--host` as an FQDN) configured
nginx for the domain but never wrote ADMIN_DOMAIN to hop3-server.toml, so the
server didn't know its own public URL — `auth:magic-link` returned a bare token
and the CLI emitted http://<host>:8000/auth/magic/... instead of
https://<domain>/auth/magic/....
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


class _RecordingBackend:
    def __init__(self, *, ok: bool = True) -> None:
        self.commands: list[str] = []
        self._ok = ok

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        return SimpleNamespace(success=self._ok, stdout="", stderr="", returncode=0)


def _persist_commands(domain: str = "hop3.abilian.com", *, ok: bool = True) -> list[str]:
    backend = _RecordingBackend(ok=ok)
    deployer = Deployer(DeployConfig(quiet=True), backend=backend)  # type: ignore[arg-type]
    deployer._persist_admin_domain(domain)
    return backend.commands


def test_writes_admin_domain_to_server_toml():
    cmds = _persist_commands()
    write = next(c for c in cmds if "hop3-server.toml" in c)
    assert 'ADMIN_DOMAIN = "hop3.abilian.com"' in write
    assert "chown hop3:hop3" in write


def test_update_or_append_is_idempotent():
    """The write both updates an existing line and appends a new one."""
    write = next(c for c in _persist_commands() if "hop3-server.toml" in c)
    assert "grep -q '^ADMIN_DOMAIN'" in write  # update branch
    assert "printf" in write  # append branch


def test_restarts_server_after_writing():
    assert any("systemctl restart hop3-server" in c for c in _persist_commands())


def test_no_restart_when_write_fails():
    """A failed config write must not be followed by a restart (and is loud)."""
    cmds = _persist_commands(ok=False)
    assert not any("systemctl restart" in c for c in cmds)
