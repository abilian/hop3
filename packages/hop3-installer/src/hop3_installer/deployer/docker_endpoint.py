# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Which Docker daemon a run uses, decided once.

The ``docker`` CLI follows contexts (``DOCKER_CONTEXT``, then the current
context); docker-py reads ``DOCKER_HOST`` and ignores contexts. With the current
context on a remote machine, the deployer started its container there through
the CLI while the harness looked for it on the local socket through docker-py.
Pinning ``DOCKER_HOST`` to the endpoint the CLI would use makes both agree, in
this process and in every process it starts.

A container's published ports live on the daemon's machine, so the endpoint
also names the host the harness reaches them at.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Schemes whose daemon runs on this machine.
_LOCAL_SCHEMES = frozenset({"unix", "npipe"})


@dataclass(frozen=True)
class DockerEndpoint:
    """A Docker daemon address, as ``DOCKER_HOST`` spells it."""

    url: str

    @property
    def published_host(self) -> str:
        """Where a container's published ports answer."""
        parts = urlsplit(self.url)
        if parts.scheme in _LOCAL_SCHEMES:
            return "localhost"
        if not parts.hostname:
            msg = f"Docker endpoint {self.url!r} names no host"
            raise RuntimeError(msg)
        return parts.hostname


def pin_docker_endpoint() -> DockerEndpoint:
    """
    Resolve the daemon the ``docker`` CLI would use and export it as ``DOCKER_HOST``.

    Call it before the first Docker operation of a run.
    """
    url = os.environ.get("DOCKER_HOST") or _current_context_host()
    os.environ["DOCKER_HOST"] = url
    return DockerEndpoint(url)


def _current_context_host() -> str:
    # With no name, `context inspect` reads the context the CLI would use:
    # DOCKER_CONTEXT, else the config's currentContext.
    try:
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        msg = "Docker endpoint unknown: no `docker` command on PATH"
        raise RuntimeError(msg) from None
    url = result.stdout.strip()
    if result.returncode != 0 or not url:
        msg = (
            "Docker endpoint unknown: `docker context inspect` failed "
            f"({result.stderr.strip() or f'exit {result.returncode}'}). "
            "Set DOCKER_HOST or DOCKER_CONTEXT."
        )
        raise RuntimeError(msg)
    return url
