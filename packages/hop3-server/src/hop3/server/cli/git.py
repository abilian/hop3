# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SSH git command handlers for git push deployment.

These commands are invoked via SSH when a user runs:
    git push hop3@server:myapp main

The SSH authorized_keys file is configured to force all commands through
hop3-server, so when git runs `git-receive-pack '/home/hop3/apps/myapp/git'`,
it actually executes: `hop3-server git-receive-pack '/home/hop3/apps/myapp/git'`
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hop3.core.git import GitManager, extract_app_name_from_repo_path
from hop3.lib import echo
from hop3.lib.archives import extract_archive_to_dir
from hop3.lib.registry import register
from hop3.orm import App, AppRepository, get_session_factory

from ._base import Command

if TYPE_CHECKING:
    from argparse import ArgumentParser


@register
class GitReceivePackCmd(Command):
    """Handle git-receive-pack from SSH for git push.

    This command is called when a user runs `git push hop3@server:myapp`.
    It handles the git protocol, auto-creates apps on first push, and
    initializes bare repositories as needed.

    Usage (called automatically by git):
        hop3-server git-receive-pack /home/hop3/apps/myapp/git
        hop3-server git-receive-pack myapp
        hop3-server git-receive-pack myapp.git
    """

    name = "git-receive-pack"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("repo_path", type=str, help="Path to the git repository")

    def run(self, repo_path: str) -> None:
        app_name = extract_app_name_from_repo_path(repo_path)

        session_factory = get_session_factory()
        with session_factory() as session:
            app_repo = AppRepository(session=session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                # Auto-create app on first push (like Heroku/piku)
                echo(f"-----> Creating new app: {app_name}", fg="green")
                app = App(name=app_name)
                app.create(setup_git=True)
                session.add(app)
                session.commit()
                echo(f"-----> App '{app_name}' created", fg="green")

            git_manager = GitManager(app)
            git_manager.receive_pack()


@register
class GitUploadPackCmd(Command):
    """Handle git-upload-pack from SSH for git clone/fetch.

    This command is called when a user runs `git clone hop3@server:myapp`
    or `git fetch` on an existing repository.

    Usage (called automatically by git):
        hop3-server git-upload-pack /home/hop3/apps/myapp/git
        hop3-server git-upload-pack myapp
    """

    name = "git-upload-pack"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("repo_path", type=str, help="Path to the git repository")

    def run(self, repo_path: str) -> None:
        app_name = extract_app_name_from_repo_path(repo_path)

        session_factory = get_session_factory()
        with session_factory() as session:
            app_repo = AppRepository(session=session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                print(
                    f"ERROR: App '{app_name}' not found",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check if repository exists
            if not (app.repo_path / "HEAD").exists():
                print(
                    f"ERROR: Repository for '{app_name}' not initialized. "
                    "Push code first with: git push hop3 main",
                    file=sys.stderr,
                )
                sys.exit(1)

            git_manager = GitManager(app)
            git_manager.upload_pack()


@register
class GitHookCmd(Command):
    """Handle git post-receive hook to trigger deployment.

    This command is called by the post-receive hook when code is pushed.
    It reads push data from stdin and triggers deployment.

    Usage (called by post-receive hook):
        hop3-server git-hook myapp
    """

    name = "git-hook"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app_name", type=str, help="Name of the app to deploy")

    def run(self, app_name: str) -> None:
        import subprocess  # ruff:ignore[import-outside-top-level]

        from hop3.deployers import do_deploy  # ruff:ignore[import-outside-top-level]

        session_factory = get_session_factory()
        with session_factory() as session:
            app_repo = AppRepository(session=session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                print(f"ERROR: App '{app_name}' not found", file=sys.stderr)
                sys.exit(1)

            # Read push data from stdin (sent by git hook)
            push_data = sys.stdin.read().strip()
            if not push_data:
                print("ERROR: No push data received from git hook", file=sys.stderr)
                sys.exit(1)

            # Parse the push data: <old-sha> <new-sha> <ref-name>
            lines = push_data.split("\n")
            if not lines:
                print("ERROR: Invalid push data format", file=sys.stderr)
                sys.exit(1)

            # Process the first ref (usually master/main)
            parts = lines[0].split()
            if len(parts) != 3:
                print(f"ERROR: Invalid push data format: {push_data}", file=sys.stderr)
                sys.exit(1)

            _old_sha, new_sha, ref_name = parts

            # Extract branch name from ref
            branch = ref_name.split("/")[-1] if "/" in ref_name else ref_name

            echo(
                f"-----> Git push detected for '{app_name}' branch '{branch}' ({new_sha[:8]})",
                fg="green",
            )

            # Extract the commit to app's source directory
            echo(f"-----> Extracting commit {new_sha[:8]}...", fg="cyan")

            # SECURITY: route the archive through the same hardened
            # extractor the RPC repository-upload path uses. git's own
            # tooling already prevents path-traversal entries in repo
            # paths, but threading both archive sources through one
            # validator keeps the controls in one place. See
            # notes/security.md §3.5 / 0.5.0.dev3 H-002.
            git_archive = subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=tar.gz",
                    new_sha,
                ],
                cwd=app.repo_path,
                check=True,
                capture_output=True,
            )
            extract_archive_to_dir(git_archive.stdout, app.src_path)

            # Trigger deployment
            echo(f"-----> Deploying '{app_name}'...", fg="cyan")
            do_deploy(app, db_session=session)
            session.commit()

            echo(f"-----> Deployment successful for '{app_name}'", fg="green")
