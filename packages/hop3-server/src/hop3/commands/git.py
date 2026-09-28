# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Git-related CLI commands for deployment via git push."""

from __future__ import annotations

import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.core.git import GitManager
from hop3.core.identifiers import validate_app_name
from hop3.core.roles import Role
from hop3.deployers import do_deploy, make_way_for_new_source
from hop3.lib import log
from hop3.lib.archives import extract_archive_to_dir
from hop3.lib.args import pop_app_flag
from hop3.lib.registry import register
from hop3.orm import App, AppRepository

from ._base import Command
from ._errors import command_context
from ._helpers import get_app
from ._response import error, success, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class GitHookCmd(Command):
    """
    Handle git post-receive hook to trigger deployment.

    Usage: hop3 git-hook --app <app>
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("git-hook",)
    min_role: ClassVar[Role] = Role.DEPLOYER
    hidden: ClassVar[bool] = True  # Internal command, called by git hook

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        """
        Process git post-receive hook data and trigger deployment.

        This command is called by the git post-receive hook when code is pushed.
        It reads push data from stdin, extracts the new commit to the app's
        source directory, and triggers a deployment.

        Hook data format from stdin: <old-sha> <new-sha> <ref-name>
        Example: aa453216... 68f7abf4... refs/heads/master
        """
        app_name, _rest = pop_app_flag(args)

        if app_name is None:
            raise self.usage_error()

        validate_app_name(app_name)

        # Get the app from database
        app_repo = AppRepository(session=self.db_session)
        app = app_repo.get_one_or_none(name=app_name)
        if not app:
            return [error(f"App '{app_name}' not found.")]

        # Read push data from stdin (sent by git hook)
        push_data = sys.stdin.read().strip()
        if not push_data:
            return [error("No push data received from git hook")]

        # Parse the push data: <old-sha> <new-sha> <ref-name>
        lines = push_data.split("\n")
        if not lines:
            return [error("Invalid push data format")]

        # Process the first ref (usually master/main)
        parts = lines[0].split()
        if len(parts) != 3:
            return [error(f"Invalid push data format: {push_data}")]

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
            do_deploy(app, db_session=self.db_session)

            # Persist changes to database (run_state, image_tag, port, etc.)
            self.db_session.commit()

            log(
                f"Deployment from git push completed for '{app_name}'",
                level=0,
                fg="green",
            )

        return [
            text("-----> Deployment successful"),
            text(f"-----> {app_name} deployed from git push ({new_sha[:8]})"),
        ]

    def _extract_commit_to_source(self, app: App, commit_sha: str) -> None:
        """
        Replace the app's source tree with the tree of ``commit_sha``.

        `git archive` reads the commit without checking out the bare repository.
        The archive goes through the hardened extractor an upload and the SSH
        push hook (`server/cli/git.py`) use, so its checks live in one place.

        Raises:
            subprocess.CalledProcessError: If `git archive` fails
        """
        make_way_for_new_source(app)
        log(f"Extracting commit {commit_sha[:8]} to {app.src_path}", level=2)
        archive = subprocess.run(
            ["git", "archive", "--format=tar.gz", commit_sha],
            cwd=app.repo_path,
            check=True,
            capture_output=True,
        )
        extract_archive_to_dir(archive.stdout, app.src_path)

        log(
            f"Successfully extracted commit {commit_sha[:8]} to source",
            level=2,
            fg="green",
        )


@register
@dataclass(frozen=True)
class GitSetupCmd(Command):
    """
    Set up git push deployment for an app.

    This command initializes a bare git repository for the app and configures
    the post-receive hook for automatic deployment. After running this, you can
    deploy using `git push`.

    Usage:
        hop3 git setup [--app <app>]

    Example:
        hop3 git setup --app myapp
        # Then on your local machine:
        git remote add hop3 hop3@your-server:myapp
        git push hop3 main
    """

    # Hidden per ADR 036 D3: removed from user-visible surface. Still callable
    # explicitly by operators (`hop3 git setup --app <app>`); used internally by the
    # deploy flow. Could be folded into `app git-setup` in a future revision.
    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("git", "setup")
    min_role: ClassVar[Role] = Role.DEPLOYER
    hidden: ClassVar[bool] = True

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        app_name, _rest = pop_app_flag(args)

        if app_name is None:
            raise self.usage_error()

        # Get the app from database
        app = get_app(self.db_session, app_name)

        # Set up git repository with hook
        git_manager = GitManager(app)
        git_manager.setup_hook()

        # Get the hostname for the git URL
        # Try to get the configured hostname first, fall back to socket hostname
        hostname = app.hostname or socket.gethostname()

        # Build the git remote URL
        git_url = f"hop3@{hostname}:{app_name}"

        return [
            success(f"Git deployment enabled for '{app_name}'"),
            text(""),
            text("Add the remote to your local repository:"),
            text(f"  git remote add hop3 {git_url}"),
            text(""),
            text("Then deploy with:"),
            text("  git push hop3 main"),
        ]
