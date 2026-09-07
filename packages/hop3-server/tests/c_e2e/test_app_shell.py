# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 app shell` end to end: the forced-command path into `hop3-server app-shell`.

Pushes an app, then opens the session the CLI would (``ssh -t hop3@host
"app-shell <app>"``) with a scripted stdin, and checks what the CLI relies on:
the shell runs in the app's source tree with the app's environment, its exit
status travels back, and a missing app is refused instead of landing the
caller in an empty directory.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from .conftest import FLASK_REQUIREMENTS, init_git_repo
from .test_git_push import FLASK_APP_CODE, add_hop3_remote, git_push_to_hop3

if TYPE_CHECKING:
    from pathlib import Path


def open_shell(
    container_info: dict[str, Any], app_name: str, script: str
) -> subprocess.CompletedProcess[str]:
    """Open the app shell over ssh with a pty and feed it ``script``."""
    argv = [
        "ssh",
        "-tt",  # a pty even though our stdin is a pipe: what the CLI gets from a terminal
        "-i", container_info["ssh_key"],
        "-p", str(container_info["ssh_port"]),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        container_info["ssh_host"],
        f"app-shell {app_name}",
    ]  # fmt: skip
    return subprocess.run(
        argv, input=script, capture_output=True, text=True, timeout=60, check=False
    )


@pytest.mark.e2e
class TestAppShell:
    def test_shell_runs_in_the_app_context(
        self, hop3_container: dict[str, Any], tmp_path: Path
    ) -> None:
        app_name = "shell-app"
        app_dir = tmp_path / app_name
        app_dir.mkdir()
        (app_dir / "app.py").write_text(FLASK_APP_CODE)
        (app_dir / "requirements.txt").write_text(FLASK_REQUIREMENTS)
        (app_dir / "Procfile").write_text(
            "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
        )
        init_git_repo(app_dir)
        add_hop3_remote(app_dir, hop3_container, app_name)
        push = git_push_to_hop3(app_dir, hop3_container)
        assert push.returncode == 0, f"Push failed: {push.stderr}"
        assert "Deployment successful" in push.stdout + push.stderr

        result = open_shell(
            hop3_container,
            app_name,
            "echo APP=$APP; pwd; echo PORT=$PORT; "
            "echo SECRET=${HOP3_SECRET_KEY-unset}; exit 7\n",
        )

        assert result.returncode == 7, result.stdout + result.stderr
        assert f"APP={app_name}" in result.stdout
        assert f"/home/hop3/apps/{app_name}/src" in result.stdout
        assert re.search(r"PORT=\d+", result.stdout), result.stdout
        assert "SECRET=unset" in result.stdout

    def test_a_missing_app_is_refused(self, hop3_container: dict[str, Any]) -> None:
        result = open_shell(hop3_container, "no-such-app", "exit 0\n")
        assert result.returncode == 1
        assert "no app named 'no-such-app'" in result.stdout + result.stderr
