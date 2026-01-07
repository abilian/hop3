# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Git-related CLI commands for deployment via git push."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3.deployers import do_deploy
from hop3.lib import log
from hop3.lib.registry import register
from hop3.orm import App, AppRepository

from ._base import Command
from ._errors import command_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class GitHookCmd(Command):
    """Handle git post-receive hook to trigger deployment."""

    db_session: Session
    name: ClassVar[str] = "git-hook"

    def call(self, *args):
        """Process git post-receive hook data and trigger deployment.

        This command is called by the git post-receive hook when code is pushed.
        It reads push data from stdin, extracts the new commit to the app's
        source directory, and triggers a deployment.

        Hook data format from stdin: <old-sha> <new-sha> <ref-name>
        Example: aa453216... 68f7abf4... refs/heads/master
        """
        if not args:
            msg = "Usage: hop3 git-hook <app_name>"
            raise ValueError(msg)

        app_name = args[0]

        # Get the app from database
        app_repo = AppRepository(session=self.db_session)
        app = app_repo.get_one_or_none(name=app_name)
        if not app:
            return [{"t": "error", "text": f"App '{app_name}' not found."}]

        # Read push data from stdin (sent by git hook)
        push_data = sys.stdin.read().strip()
        if not push_data:
            return [{"t": "error", "text": "No push data received from git hook"}]

        # Parse the push data: <old-sha> <new-sha> <ref-name>
        lines = push_data.split("\n")
        if not lines:
            return [{"t": "error", "text": "Invalid push data format"}]

        # Process the first ref (usually master/main)
        parts = lines[0].split()
        if len(parts) != 3:
            return [{"t": "error", "text": f"Invalid push data format: {push_data}"}]

        _old_sha, new_sha, ref_name = parts

        # Extract branch name from ref (refs/heads/master -> master)
        branch = ref_name.split("/")[-1] if "/" in ref_name else ref_name

        log(
            f"Git push detected for '{app_name}' branch '{branch}' ({new_sha[:8]})",
            level=0,
            fg="cyan",
        )

        with command_context(
            "deploying from git push", app_name=app_name, commit=new_sha[:8]
        ):
            # Extract the commit to app's source directory
            self._extract_commit_to_source(app, new_sha)

            # Trigger deployment using the unified deployment engine
            do_deploy(app)

            log(
                f"Deployment from git push completed for '{app_name}'",
                level=0,
                fg="green",
            )

        return [
            {"t": "text", "text": "-----> Deployment successful"},
            {
                "t": "text",
                "text": f"-----> {app_name} deployed from git push ({new_sha[:8]})",
            },
        ]

    def _extract_commit_to_source(self, app: App, commit_sha: str) -> None:
        """Extract a specific commit from the git repository to the source directory.

        This uses `git archive` to safely extract a commit without checking out
        the repository. The archive is created in a temporary location and then
        extracted to the app's source directory.

        Args:
            app: The application instance
            commit_sha: The git commit SHA to extract

        Raises:
            subprocess.CalledProcessError: If git operations fail
        """
        # Clean the source directory first
        if app.src_path.exists():
            log(f"Cleaning existing source directory: {app.src_path}", level=2)
            shutil.rmtree(app.src_path)
        app.src_path.mkdir(parents=True, exist_ok=True)

        # Use git archive to create a tarball from the commit
        # This is safer than git checkout as it doesn't modify the bare repo
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "commit.tar"

            # Create archive from commit
            log(f"Creating archive from commit {commit_sha[:8]}", level=2)
            cmd = [
                "git",
                "archive",
                "--format=tar",
                f"--output={archive_path}",
                commit_sha,
            ]
            subprocess.run(
                cmd,
                cwd=app.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Extract archive to source directory
            log(f"Extracting archive to {app.src_path}", level=2)
            cmd = [
                "tar",
                "-xf",
                str(archive_path),
                "-C",
                str(app.src_path),
            ]
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

        log(
            f"Successfully extracted commit {commit_sha[:8]} to source",
            level=2,
            fg="green",
        )
