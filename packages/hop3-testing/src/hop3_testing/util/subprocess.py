# Copyright (c) 2024-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Subprocess utilities for test execution."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.targets import TargetInfo


def build_test_env(target_info: TargetInfo) -> dict[str, str]:
    """
    Build environment variables for test subprocess execution.

    The ``HOP3_TEST_*`` vars are OUTPUTS the harness hands to a test/tutorial/
    demo subprocess (check.py, validoc) so it knows where the deployed server
    is. They are NOT target selectors: the harness resolves its own target from
    an explicit ``--host`` / ``--docker`` only (ADR 043 retired HOP3_TEST_HOST /
    HOP3_DEV_HOST as ambient selectors), then reports the result here.

    Args:
        target_info: Target information with SSH connection details.

    Returns:
        Environment dict with HOP3_TEST_* variables added.
    """
    env = {
        **os.environ,
        "HOP3_TEST_HOST": target_info.ssh_host,
        "HOP3_TEST_PORT": str(target_info.ssh_port),
        "HOP3_TEST_SSH_KEY": target_info.ssh_key or "",
        # Tutorials/demos run `hop3 deploy` (and friends) non-interactively
        # via validoc; without this, the ADR-042 deploy confirm prompt blocks
        # on a tty until the per-command timeout, failing every tutorial.
        "HOP3_NO_INPUT": "1",
    }
    # Tutorials set HOST_NAME=<app>.$HOP3_TEST_DOMAIN and then curl that host, so
    # the domain MUST resolve to the target. Default to <host>.sslip.io —
    # *.<ip>.sslip.io resolves to <ip> via public wildcard DNS, so app vhosts
    # work with zero DNS setup. Without it HOST_NAME is "<app>." (empty domain),
    # no nginx vhost is created, and curl fails to resolve. An operator can
    # override HOP3_TEST_DOMAIN (e.g. a real wildcard domain pointed at the box).
    if not env.get("HOP3_TEST_DOMAIN"):
        env["HOP3_TEST_DOMAIN"] = f"{target_info.ssh_host}.sslip.io"
    return env


def run_captured(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """
    Like ``subprocess.run(capture_output=True, text=True, timeout=...)`` but
    kills the child's whole process *group* on timeout before draining output.

    Demo and tutorial runs spawn grandchildren (the ``hop3`` CLI, then ``ssh``)
    that inherit the captured stdout/stderr pipes. ``subprocess.run`` only kills
    the direct child on timeout, so a surviving grandchild keeps the pipe's
    write end open and the post-kill ``communicate()`` blocks forever — the run
    never returns and the dashboard shows "No logs recorded". Running the child
    in its own session lets us SIGKILL the entire tree, then drain whatever was
    buffered before the kill.

    Raises ``subprocess.TimeoutExpired`` with ``output``/``stderr`` populated on
    timeout, matching ``subprocess.run`` so callers keep a single handler. Does
    not raise on a non-zero exit (equivalent to ``check=False``).
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,  # never inherit a tty: a prompt must fail
        # fast (a non-tty read hits EOF / the CLI's no-tty refusal) rather
        # than block on input until the timeout — the tutorial-hang failure.
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # own process group, so we can kill the tree
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        # The tree is dead now, so the pipes have closed; this drain returns.
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd, timeout, output=stdout, stderr=stderr
        ) from None
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def as_text(stream: str | bytes | None) -> str:
    """
    Coerce a captured subprocess stream (str / bytes / None) to text.

    ``subprocess.TimeoutExpired.stdout`` is typed loosely (it can be bytes when
    ``text=False``); this normalises it so timeout handlers can build a log
    string without tripping the type checker.
    """
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return stream


def _kill_process_group(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group, falling back to the child."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
