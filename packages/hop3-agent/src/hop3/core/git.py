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

from hop3.system.constants import HOP3_ROOT, HOP3_SCRIPT
from hop3.util import log

if TYPE_CHECKING:
    from pathlib import Path

    from .app import App


@frozen
class GitManager:
    app: App

    @property
    def repo_path(self) -> Path:
        return self.app.repo_path

    @property
    def app_name(self) -> str:
        return self.app.name

    def receive_pack(self) -> None:
        """Handle git pushes for an app."""
        cwd = self.app.repo_path
        cmd = ["git-receive-pack", str(self.repo_path)]
        subprocess.run(cmd, cwd=cwd, check=True)

    def upload_pack(self) -> None:
        """Handle git upload pack for an app."""
        cwd = self.app.repo_path
        cmd = ["git-upload-pack", str(self.repo_path)]
        subprocess.run(cmd, cwd=cwd, check=True)

    def setup_hook(self) -> None:
        """Setup a post-receive hook for an app."""
        hook_path = self.repo_path / "hooks" / "post-receive"

        if not hook_path.exists():
            hook_path.parent.mkdir(parents=True)

            # Initialize the repository with a hook to this script
            cmd = ["git", "init", "--quiet", "--bare", str(self.repo_path)]
            cwd = self.app.repo_path
            subprocess.run(cmd, cwd=cwd, check=True)

            hook_path.write_text(
                dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -e; set -o pipefail;
                    cat | HOP3_ROOT="{HOP3_ROOT}" {HOP3_SCRIPT} git-hook {self.app_name}
                    """,
                )
            )
            make_executable(hook_path)

    def clone(self) -> None:
        """Clone a repository for an app."""
        if not self.app.src_path.exists():
            log(f"Creating app '{self.app_name}'", level=2, fg="green")
            self.app.create()

            cmd = [
                "git",
                "clone",
                "--quiet",
                str(self.repo_path),
                str(self.app.src_path),
            ]
            cwd = self.app.repo_path
            subprocess.run(cmd, cwd=cwd, check=True)


def make_executable(path: Path) -> None:
    """Make file executable by the user."""
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
