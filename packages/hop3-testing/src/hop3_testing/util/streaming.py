# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Streaming subprocess execution for long-running commands."""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


_IS_POSIX = sys.platform != "win32"


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Send SIGKILL to the entire process group started by ``process``.

    ``run_streaming`` starts the child in its own session (see
    ``start_new_session`` in :func:`run_streaming`), so the child's pid is
    also the process-group id. Killing the group takes down any
    grand-children (``nix-build``, ``docker compose up``, ``hop3-deploy``
    via SSH, …) that would otherwise orphan when only the top-level
    process is killed.

    Falls back to ``process.kill()`` on Windows or if ``killpg`` fails.
    """
    if _IS_POSIX:
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            # The child already exited between the timeout check and here.
            return
        try:
            os.killpg(pgid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            # Fall through to single-process kill as a last resort
            pass

    with contextlib.suppress(ProcessLookupError):
        process.kill()


@dataclass
class StreamingResult:
    """Result of a streaming subprocess execution."""

    returncode: int
    """Exit code of the process."""

    stdout: str
    """Complete captured stdout."""

    stderr: str
    """Complete captured stderr (if separate)."""

    timed_out: bool = False
    """Whether the command timed out."""


def _process_line(
    line: bytes,
    output_lines: list[str],
    on_output: Callable[[str], None] | None,
) -> None:
    """Decode and process a single output line."""
    decoded = line.decode("utf-8", errors="replace").rstrip()
    output_lines.append(decoded)
    if on_output and decoded:
        on_output(decoded)


def _drain_queue(
    output_queue: queue.Queue[bytes | None],
    output_lines: list[str],
    on_output: Callable[[str], None] | None,
) -> None:
    """Drain remaining items from the queue after process finishes."""
    time.sleep(0.1)  # Give thread time to finish
    while True:
        try:
            line = output_queue.get_nowait()
            if line is None:
                break
            _process_line(line, output_lines, on_output)
        except queue.Empty:
            break


def run_streaming(
    cmd: list[str] | str,
    on_output: Callable[[str], None] | None = None,
    timeout: int = 600,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> StreamingResult:
    """Run a command with streaming output.

    Uses a separate thread to read output lines, avoiding blocking issues
    with large outputs. Lines are passed to the callback as they arrive.

    Args:
        cmd: Command to run (list or string)
        on_output: Callback for each line of output (optional)
        timeout: Maximum execution time in seconds (default 10 minutes)
        cwd: Working directory
        env: Environment variables

    Returns:
        StreamingResult with exit code and captured output
    """
    shell = isinstance(cmd, str)

    process = subprocess.Popen(
        cmd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        # No inherited stdin: a deploy step that prompts (ssh host-key on a
        # freshly-rebuilt box, apt, sudo) would otherwise read the parent's
        # stdin and hang the full timeout. DEVNULL gives it EOF -> fail fast.
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        env=env,
        # Start in its own session so _terminate_process_tree can kill
        # grand-children (nix-build, docker, ssh) on timeout. Without
        # this, only the direct child receives SIGKILL and subprocesses
        # orphan — polluting Docker containers and leaving nix daemons
        # holding locks.
        start_new_session=_IS_POSIX,
    )

    output_queue: queue.Queue[bytes | None] = queue.Queue()
    output_lines: list[str] = []

    def reader_thread():
        """Read lines from process stdout and put them in queue."""
        try:
            while True:
                assert process.stdout is not None
                line = process.stdout.readline()
                if not line:
                    break
                output_queue.put(line)
        except Exception:
            pass
        finally:
            output_queue.put(None)  # Signal EOF

    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()

    start_time = time.time()
    timed_out = False

    while True:
        # Check timeout
        if time.time() - start_time > timeout:
            _terminate_process_tree(process)
            timed_out = True
            break

        try:
            line = output_queue.get(timeout=1.0)
            if line is None:
                break
            _process_line(line, output_lines, on_output)
        except queue.Empty:
            # No output available, check if process is still running
            if process.poll() is not None:
                _drain_queue(output_queue, output_lines, on_output)
                break

    thread.join(timeout=2.0)
    process.wait()

    return StreamingResult(
        returncode=process.returncode,
        stdout="\n".join(output_lines),
        stderr="",
        timed_out=timed_out,
    )
