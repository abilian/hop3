# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The download cache has to outlive the container it was filled in.

`hop3-fetch` exists so a catalog run stops re-downloading tarballs it already
has — GitHub's codeload rate-limits the address, and once it does, deploys fail
with HTTP 429 through no fault of the recipe. On a real server the cache sits
under the hop3 home and persists by itself. Here the container is rebuilt every
run, so a cache inside it is empty every time and buys nothing: the run makes
the same twenty-odd requests, gets throttled again, and the limit never heals.

Hence a named volume — not a bind mount, which on macOS presents its own
ownership and would leave the hop3 user unable to write there.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_installer.deployer.backends.docker import (
    DOWNLOAD_CACHE_PATH,
    DOWNLOAD_CACHE_VOLUME,
    SUPERVISOR_CONFIG,
    DockerDeployBackend,
)
from hop3_installer.deployer.config import DeployConfig


def _run_argv() -> list[str]:
    backend = DockerDeployBackend(DeployConfig(use_docker=True))
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        backend._start_container()
        return list(run.call_args[0][0])


def test_the_cache_is_backed_by_a_named_volume():
    argv = _run_argv()

    assert f"{DOWNLOAD_CACHE_VOLUME}:{DOWNLOAD_CACHE_PATH}" in argv


def test_the_mount_precedes_the_image():
    """A -v after the image name is an argument to `sleep`, not a mount."""
    argv = _run_argv()

    assert argv.index(f"{DOWNLOAD_CACHE_VOLUME}:{DOWNLOAD_CACHE_PATH}") < argv.index(
        "sleep"
    )


def test_the_server_is_told_where_the_cache_is():
    """
    Build hooks inherit the server process's environment.

    Without this the helper would fall back to its default under the hop3 home,
    which is inside the container and therefore thrown away between runs — the
    volume would be mounted and never written to, and the whole thing would look
    like it worked.
    """
    assert f'HOP3_DOWNLOAD_CACHE="{DOWNLOAD_CACHE_PATH}"' in SUPERVISOR_CONFIG


class _StopError(Exception):
    """Ends start_services at its first command, which is the one under test."""


def test_the_volume_is_handed_to_the_hop3_user():
    """
    Docker creates a fresh volume root-owned; builds run as hop3.

    It has to happen before supervisor starts anything, or the first deploy
    races a cache it cannot write to.
    """
    backend = DockerDeployBackend(DeployConfig(use_docker=True))
    issued: list[str] = []

    def record(command: str, **_kwargs):
        issued.append(command)
        raise _StopError

    with patch.object(backend, "run", side_effect=record), pytest.raises(_StopError):
        backend.start_services()

    assert issued == [f"chown hop3:hop3 {DOWNLOAD_CACHE_PATH}"]
