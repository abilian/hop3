# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclasses for deployment targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hop3_testing.targets.constants import DEFAULT_DOCKER_IMAGE


@dataclass
class DeploymentConfig:
    """Configuration for optional Hop3 deployment.

    When provided to a target, Hop3 will be deployed before running tests.
    When None, the target connects to an already-running Hop3 server.
    """

    source: Literal["local", "git", "pypi"] = "local"
    """Deployment source: local code, git branch, or PyPI package."""

    branch: str = "devel"
    """Git branch to deploy (only used when source="git")."""

    version: str | None = None
    """Pinned PyPI version, emitted as --version (only used when source="pypi").
    Drives an upgrade chain: install 0.6.0, then upgrade to 0.6.2, etc."""

    legacy_flags: bool = False
    """Emit old-style source flags (--local/--git/--pypi) instead of --from.
    Set when running an OLD version's own deployer (upgrade chain) — pre-ADR-052
    releases don't have --from, and the current deployer keeps the aliases."""

    clean: bool = False
    """Whether to clean existing installation before deploying."""

    verbose: bool = False
    """Whether to show verbose deployment output."""

    domain: str | None = None
    """Admin domain, emitted as --admin-domain (enables admin setup). Used by the
    cloud path; None on the plain run path means no admin domain is configured."""

    acme_email: str | None = None
    """Email for Let's Encrypt registration, emitted as --acme-email (cloud path)."""

    features: list[str] = field(default_factory=list)
    """Features to install (e.g., docker, mysql, redis, nix, or 'all')."""

    command_prefix: list[str] | None = None
    """Prepended to the deploy command, e.g. ["uv", "run"]. The cloud path (7b.5)
    deploys from a source checkout via `uv run hop3-deploy-server`; the plain run
    path leaves this None and invokes the installed console script directly."""

    cwd: Path | None = None
    """Working directory for the deploy subprocess (the cloud path's cloned/local
    repo). None on the run path -> current directory."""


@dataclass
class DockerConfig:
    """Configuration for Docker-based targets.

    Examples:
        # Use pre-built image (fast app testing)
        DockerConfig(image="hop3-ready:latest")

        # Build from Dockerfile
        DockerConfig(dockerfile=Path("Dockerfile"))

        # Custom container name
        DockerConfig(container_name="my-test")

        # Reuse existing container
        DockerConfig(container_name="hop3-test", reuse_container=True)
    """

    image: str = DEFAULT_DOCKER_IMAGE
    """Base Docker image to use."""

    container_name: str = "hop3-test"
    """Name for the Docker container."""

    dockerfile: Path | None = None
    """Path to Dockerfile (if building custom image)."""

    reuse_container: bool = False
    """Connect to existing container instead of creating new one."""

    ports: dict[str, int | None] = field(
        default_factory=lambda: {
            "22/tcp": None,  # SSH - random port
            "80/tcp": None,  # HTTP - random port
            "8000/tcp": None,  # API - random port
        }
    )
    """Port mappings (container_port -> host_port, None for random)."""

    log_dir: Path = field(default_factory=lambda: Path("test-logs"))
    """Directory for diagnostic logs."""


@dataclass
class RemoteConfig:
    """Configuration for SSH-based remote targets.

    Examples:
        # Basic connection
        RemoteConfig(host="server.example.com")

        # With SSH key
        RemoteConfig(host="server.example.com", ssh_key="~/.ssh/id_rsa")

        # Non-standard port
        RemoteConfig(host="server.example.com", port=2222)
    """

    host: str
    """SSH hostname or IP address."""

    port: int = 22
    """SSH port."""

    user: str = "root"
    """SSH username."""

    ssh_key: str | None = None
    """Path to SSH private key file."""

    password: str | None = None
    """SSH password (if not using key)."""

    http_base: str | None = None
    """Base URL for HTTP access (default: http://{host})."""

    api_url: str | None = None
    """Hop3 API URL (default: http://{host}:8000)."""

    log_dir: Path = field(default_factory=lambda: Path("test-logs"))
    """Directory for diagnostic logs."""

    def __post_init__(self) -> None:
        """Set default URLs based on host."""
        if self.http_base is None:
            self.http_base = f"http://{self.host}"
        if self.api_url is None:
            self.api_url = f"http://{self.host}:8000"
