# Copyright (c) 2024, Abilian SAS

"""
Server-side git operations.

This module provides a GitManager class to handle git operations on the server side.
"""

from __future__ import annotations

import stat
import subprocess
from textwrap import dedent
from typing import TYPE_CHECKING

from attrs import frozen

from hop3.system.constants import APP_ROOT, GIT_ROOT, HOP3_ROOT, HOP3_SCRIPT
from hop3.util import echo

if TYPE_CHECKING:
    from pathlib import Path

    from .app import App


@frozen
class GitManager:
    app: App

    def receive_pack(self) -> None:
        """Handle git pushes for an app."""
        cmd = ["git-receive-pack", self.app.name]
        subprocess.run(cmd, cwd=GIT_ROOT)

    def upload_pack(self) -> None:
        """Handle git upload pack for an app."""
        cmd = ["git-upload-pack", self.app.name]
        subprocess.run(cmd, cwd=GIT_ROOT)

    def setup_hook(self) -> None:
        """Setup a post-receive hook for an app."""
        app = self.app
        hook_path = app.repo_path / "hooks" / "post-receive"
        if not hook_path.exists():
            hook_path.parent.mkdir(parents=True)

            # Initialize the repository with a hook to this script
            cmd = ["git", "init", "--quiet", "--bare", app.name]
            subprocess.run(cmd, cwd=GIT_ROOT)

            hook_path.write_text(
                dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -e; set -o pipefail;
                    cat | HOP3_ROOT="{HOP3_ROOT}" {HOP3_SCRIPT} git-hook {app.name}
                    """,
                )
            )
            make_executable(hook_path)

    def clone(self) -> None:
        """Clone a repository for an app."""
        if not self.app.app_path.exists():
            echo(f"-----> Creating app '{self.app.name}'", fg="green")
            self.app.create()

            cmd = ["git", "clone", "--quiet", str(self.app.repo_path), str(self.app.name)]
            subprocess.run(cmd, cwd=APP_ROOT)


def make_executable(path: Path) -> None:
    """Make file executable by the user."""
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
