# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
A server snapshot brings back what was destroyed: the whole-server backup and
restore commands, end to end.

``hop3-backup-server`` and ``hop3-restore-server`` run on the operator's
machine and drive a server over ssh as root. The claim they make is that a
snapshot taken before an operation is enough to undo it. This test makes the
claim checkable: deploy an app with a PostgreSQL addon, write a row and an
environment variable, snapshot the server, destroy the app and its addon
outright, restore the snapshot, and require the app to serve again with its
row and its variable back.

Against the e2e container by default: the CLI talks to its HTTP API with a
minted token, the two server commands reach root over ssh with the container's
key (root's key is the same as hop3's there, the production shape). With
``--ssh-host user@box`` the same test runs against a real, expendable server
with the developer's own keys and login, which is the only way to prove the
systemd half of the restore script.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from hop3_testing.targets.constants import hermetic_cli_cwd

from .conftest import (
    ALLOW_PLAIN_HTTP,
    cli_env,
    create_flask_app,
    init_git_repo,
    wait_for_http_ready,
)

if TYPE_CHECKING:
    from pathlib import Path

_PG_REQUIREMENTS = "flask==3.0.0\npsycopg2-binary==2.9.9\n"
_SQL_RUNNER = """
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
cur = conn.cursor()
cur.execute({sql!r})
print(cur.fetchall() if cur.description else "ok")
"""


@dataclass(frozen=True)
class Box:
    """The server under test, as the CLI and as root over ssh."""

    host: str
    ssh_port: int
    key: str | None  # None: the developer's own keys (a real box)
    cli_environment: dict[str, str]
    http_base: str
    home: Path

    def cli_env(self) -> dict[str, str]:
        return dict(self.cli_environment)

    def server_tool_args(self) -> list[str]:
        """The target flags for hop3-backup-server / hop3-restore-server."""
        args = ["--host", self.host, "--port", str(self.ssh_port), "--user", "root"]
        if self.key:
            args += [
                "--identity",
                self.key,
                "--ssh-option",
                f"UserKnownHostsFile={self.home / 'known_hosts'}",
            ]
        return args


@pytest.fixture
def box(
    request: pytest.FixtureRequest, hop3_container: dict[str, Any], tmp_path: Path
) -> Box:
    home = tmp_path / "home"
    home.mkdir()
    remote = request.config.getoption("--ssh-host")
    if remote:
        # The developer's own login for that server, over its ssh transport.
        user, _, host = remote.rpartition("@")
        env = os.environ.copy()
        env["HOP3_API_URL"] = f"ssh://{user or 'root'}@{host}"
        env["HOP3_NO_INPUT"] = "1"
        return Box(
            host=host,
            ssh_port=22,
            key=None,
            cli_environment=env,
            http_base=f"http://{host}",
            home=home,
        )
    return Box(
        host=hop3_container["host"],
        ssh_port=int(hop3_container["ssh_port"]),
        key=hop3_container["ssh_key"],
        cli_environment=cli_env(hop3_container),
        http_base=hop3_container["http_base"],
        home=home,
    )


def _hop3(box: Box, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hop3", *args],
        env=box.cli_env(),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _sql(box: Box, app: str, sql: str) -> str:
    result = _hop3(
        box, "run", "--app", app, "python", "-c", _SQL_RUNNER.format(sql=sql)
    )
    assert result.returncode == 0, (
        f"SQL failed: {sql}\n{result.stdout}\n{result.stderr}"
    )
    return result.stdout


def _server_tool(box: Box, module: str, *args: str) -> subprocess.CompletedProcess:
    """Run hop3-backup-server / hop3-restore-server as this interpreter's module."""
    return subprocess.run(
        [sys.executable, "-m", module, *box.server_tool_args(), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )


class TestServerSnapshotRestore:
    def test_a_destroyed_app_comes_back_from_a_snapshot(self, box: Box, tmp_path: Path):
        app = f"snap-{secrets.token_hex(3)}"
        addon = f"{app}-db"
        label = f"e2e-{app}"
        # An app gets an nginx vhost only under a HOST_NAME; without one the
        # proxy step is skipped and nginx closes the connection. Set it, then
        # redeploy so the vhost is rendered, and ask for it by Host header.
        host = f"{app}.localhost"
        by_host = {"Host": host}
        app_dir = create_flask_app(
            tmp_path, app, response=f"snapshot {app}", requirements=_PG_REQUIREMENTS
        )
        # The page is read over plain HTTP; without this it answers 301.
        (app_dir / "hop3.toml").write_text(ALLOW_PLAIN_HTTP)
        init_git_repo(app_dir)  # hop3 deploy expects a git repository
        try:
            deployed = _hop3(box, "deploy", "--app", app, str(app_dir))
            assert deployed.returncode == 0, (
                f"deploy failed:\n{deployed.stdout}\n{deployed.stderr}"
            )
            for step in (
                ("addon", "create", "postgres", addon),
                ("addon", "attach", addon, "--app", app),
                (
                    "env",
                    "set",
                    "--app",
                    app,
                    "SNAPSHOT_MARKER=kept",
                    f"HOST_NAME={host}",
                ),
                ("deploy", "--app", app, str(app_dir)),
            ):
                result = _hop3(box, *step)
                assert result.returncode == 0, (
                    f"{' '.join(step)} failed:\n{result.stderr}"
                )
            _sql(box, app, "CREATE TABLE marker (v text)")
            _sql(box, app, "INSERT INTO marker VALUES ('before')")
            wait_for_http_ready(
                box.http_base,
                expected_content=f"snapshot {app}",
                timeout=120,
                headers=by_host,
            )

            # The snapshot, fetched home as an operator would.
            snapshot = _server_tool(
                box,
                "hop3_installer.deployer.backup",
                "--label",
                label,
                "--fetch",
                str(tmp_path / "fetched"),
            )
            assert snapshot.returncode == 0, (
                f"backup failed:\n{snapshot.stdout}\n{snapshot.stderr}"
            )
            fetched = next((tmp_path / "fetched").glob(f"*-{label}"), None)
            assert fetched is not None, snapshot.stdout
            assert (fetched / "hop3.db").is_file(), snapshot.stdout
            assert (fetched / "postgres-all.sql.gz").is_file()

            # Destroy the app and its database outright.
            for step in (
                ("addon", "detach", addon, "--app", app),
                ("addon", "destroy", addon, "-y"),
                ("app", "destroy", "--app", app, "--confirm", app),
            ):
                result = _hop3(box, *step)
                assert result.returncode == 0, (
                    f"{' '.join(step)} failed:\n{result.stderr}"
                )
            assert _hop3(box, "env", "show", "--app", app).returncode != 0, (
                "the app still exists"
            )

            # Restore from the copy on the server (the fetched copy is the same bytes).
            restored = _server_tool(
                box,
                "hop3_installer.deployer.restore",
                "--snapshot",
                fetched.name,
                "--yes",
            )
            assert restored.returncode == 0, (
                f"restore failed:\n{restored.stdout}\n{restored.stderr}"
            )

            # Everything is back: the row, the variable, the app serving its page.
            shown = _hop3(box, "env", "show", "--app", app)
            assert shown.returncode == 0, shown.stderr
            assert "SNAPSHOT_MARKER" in shown.stdout, shown.stdout
            assert "before" in _sql(box, app, "SELECT v FROM marker")
            wait_for_http_ready(
                box.http_base,
                expected_content=f"snapshot {app}",
                timeout=180,
                headers=by_host,
            )
        finally:
            _hop3(box, "addon", "detach", addon, "--app", app)
            _hop3(box, "addon", "destroy", addon, "-y")
            _hop3(box, "app", "destroy", "--app", app, "--confirm", app)
