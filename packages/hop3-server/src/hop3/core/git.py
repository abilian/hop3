# Copyright (c) 2024-2025, Abilian SAS
"""
Server-side git operations.

This module provides a GitManager class to handle git operations on the
server side.
"""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from attrs import frozen

from hop3 import config as c
from hop3.lib import (
    CommandError,
    CommandFailedError,
    CommandTimeoutError,
    log,
    robust_rmtree,
)

if TYPE_CHECKING:
    from hop3.orm import App

# Caps on cloning a repository named by an operator. A clone is the one
# deploy step whose cost is chosen entirely by whoever supplies the URL, and
# an unbounded one fills the disk, which takes down every app on the host and
# not only the one being created.
CLONE_TIMEOUT_SECONDS = 600
CLONE_MAX_BYTES = 2 * 1024**3

# How often the clone is inspected: `_WAIT` bounds how late the timeout can
# fire, `_MEASURE` how often the (O(files)) size walk runs.
_WAIT_SECONDS = 0.25
_MEASURE_SECONDS = 2.0


class CloneTooLargeError(CommandError):
    """Raised when a clone outgrows its byte cap and is killed."""

    def __init__(self, cmd: list[str], max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(cmd, f"exceeded the {max_bytes} byte clone limit")


def extract_app_name_from_repo_path(repo_path: str) -> str:
    """
    Extract app name from git repository path.

    This function handles various path formats that git may use when
    running git-receive-pack or git-upload-pack via SSH.

    Examples:
        /home/hop3/apps/myapp/git → myapp
        /home/hop3/apps/myapp/git/ → myapp
        myapp.git → myapp
        myapp → myapp
        'myapp' → myapp (with quotes stripped)

    Args:
        repo_path: The repository path from SSH_ORIGINAL_COMMAND

    Returns:
        The extracted app name
    """
    # Strip quotes that git sometimes adds
    repo_path = repo_path.strip().strip("'\"")

    path = Path(repo_path)

    # Handle /home/hop3/apps/<app>/git format
    # The path might end with a trailing slash
    if path.name == "git" and path.parent.parent.name == "apps":
        return path.parent.name

    # Handle empty path.name due to trailing slash
    if not path.name and path.parent.name == "git":
        return path.parent.parent.name

    # Handle <app>.git format
    if path.suffix == ".git":
        return path.stem

    # Handle plain <app> format
    return path.name


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
        """
        Handle git pushes for an app.

        This sets the current working directory to the app's repository
        path and runs the 'git-receive-pack' command with the repository
        path as an argument. It ensures that any incoming git pushes are
        processed appropriately.

        If the bare repository doesn't exist yet, it will be initialized
        automatically with the post-receive hook configured.
        """
        # Lazy initialization: set up bare repo if it doesn't exist
        if not (self.repo_path / "HEAD").exists():
            log(f"Initializing bare repository for '{self.app_name}'", level=2)
            self.setup_hook()

        cwd = self.app.repo_path
        cmd = ["git-receive-pack", str(self.repo_path)]
        subprocess.run(cmd, cwd=cwd, check=True)

    def upload_pack(self) -> None:
        """
        Handle git upload pack for an app.

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


def clone_repository(
    repo_url: str,
    dest: Path,
    *,
    timeout: float = CLONE_TIMEOUT_SECONDS,
    max_bytes: int = CLONE_MAX_BYTES,
) -> None:
    """
    Clone ``repo_url`` into ``dest`` under a wall-clock and a byte cap.

    Shallow and single-branch, so a long history costs nothing to fetch, and
    killed outright once the checkout passes ``max_bytes`` — git offers no
    size limit of its own, and `--depth 1` bounds the history rather than the
    content. A clone that fails, times out or overruns leaves nothing behind:
    the partial tree is removed, because a cap that keeps the bytes it just
    refused has not capped anything.

    ``repo_url`` must already have passed ``validate_repo_url``; the ``--``
    below stops git reading a hostile value as an option, and is belt to that
    validation's braces.

    Raises:
        CommandTimeoutError: the clone outlived ``timeout``.
        CloneTooLargeError: the checkout outgrew ``max_bytes``.
        CommandFailedError: git exited non-zero (unreachable host, bad ref…).
    """
    if dest.exists() and any(dest.iterdir()):
        msg = (
            f"Git can't clone into {dest}: the directory already exists and is "
            f"not empty. Remove it, or create the app under another name."
        )
        raise FileExistsError(msg)

    cmd = [
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--single-branch",
        "--",
        repo_url,
        str(dest),
    ]
    try:
        _run_capped(cmd, watched=dest, timeout=timeout, max_bytes=max_bytes)
    except (CommandError, OSError):
        robust_rmtree(dest)
        raise


def _run_capped(
    cmd: list[str], *, watched: Path, timeout: float, max_bytes: int
) -> None:
    """
    Run ``cmd`` until it exits, outlives ``timeout``, or fills ``watched``.

    Output goes to a temporary file rather than a pipe: a pipe that nobody
    drains until the process exits deadlocks a chatty git, and the deadlock
    would surface as a timeout, hiding whatever git was trying to say.
    """
    with tempfile.TemporaryFile("w+") as output:
        # Its own session, so killing the clone kills the transport helpers
        # (git-remote-https, ssh) it spawned rather than orphaning them to
        # carry on downloading.
        proc = subprocess.Popen(
            cmd,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        next_measure = 0.0

        while proc.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                _kill_session(proc)
                raise CommandTimeoutError(cmd, timeout)
            if now >= next_measure:
                if _tree_size(watched) > max_bytes:
                    _kill_session(proc)
                    raise CloneTooLargeError(cmd, max_bytes)
                next_measure = now + _MEASURE_SECONDS
            time.sleep(_WAIT_SECONDS)

        if proc.returncode != 0:
            output.seek(0)
            # Both streams were merged into `output`; they travel as stderr so
            # the exception's message carries what git actually said.
            raise CommandFailedError(cmd, proc.returncode, stderr=output.read())


def _kill_session(proc: subprocess.Popen) -> None:
    """Kill the process and everything it spawned, then reap it."""
    with suppress(ProcessLookupError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    proc.wait()


def _tree_size(path: Path) -> int:
    """Bytes held by ``path``, counting only what is there right now."""
    total = 0
    for root, _dirs, files in os.walk(path, onerror=None):
        for name in files:
            # A clone churns: a pack file counted a moment ago can be renamed
            # or removed before it is measured.
            with suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
    return total


def make_executable(path: Path) -> None:
    """Make a file executable by the user."""
    # Retrieve the current file permissions and add executable permission for the user
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
