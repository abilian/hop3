# Copyright (c) 2024-2025, Abilian SAS
"""Server-side git operations.

This module provides a GitManager class to handle git operations on the
server side.
"""

from __future__ import annotations

import stat
import subprocess
from textwrap import dedent
from typing import TYPE_CHECKING

from attrs import frozen

from hop3 import config as c
from hop3.lib import log

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm import App


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
        """Handle git pushes for an app.

        This sets the current working directory to the app's repository
        path and runs the 'git-receive-pack' command with the repository
        path as an argument. It ensures that any incoming git pushes are
        processed appropriately.
        """
        cwd = self.app.repo_path
        cmd = ["git-receive-pack", str(self.repo_path)]
        subprocess.run(cmd, cwd=cwd, check=True)

    def upload_pack(self) -> None:
        """Handle git upload pack for an app.

        This executes the 'git-upload-pack' command in the application's
        repository path.
        """
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
                    cat | HOP3_ROOT="{c.HOP3_ROOT}" {c.HOP3_SCRIPT} git-hook {self.app_name}
                    """,
                )
            )
            make_executable(hook_path)

    def clone(self) -> None:
        """Clone the git repository to the source directory.

        This checks if the source path for the application exists. If it
        does not exist, it creates the application directory and clones
        the specified git repository into it.
        """
        if not self.app.src_path.exists():
            log(f"Creating app '{self.app_name}'", level=2, fg="green")
            self.app.create()

            # Prepare the git clone command with the repository path and source path
            cmd = [
                "git",
                "clone",
                "--quiet",
                str(self.repo_path),
                str(self.app.src_path),
            ]
            cwd = self.app.repo_path

            # Execute the git clone command in the specified working directory
            subprocess.run(cmd, cwd=cwd, check=True)


def make_executable(path: Path) -> None:
    """Make a file executable by the user."""
    # Retrieve the current file permissions and add executable permission for the user
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
