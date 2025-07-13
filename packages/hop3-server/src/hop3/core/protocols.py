# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from hop3.orm import App

    from .env import Env


#
# --- Data Structures ---
#
@dataclass
class DeploymentContext:
    """
    A simple data class to pass around context
    """

    app_name: str
    source_path: Path
    app_config: dict

    def __post_init__(self):
        assert self.source_path.is_dir()

    # app: App
    # app_config: AppConfig
    # new_rev: str
    # log_callback: Callable[[str], None]  # To stream logs back


@dataclass
class BuildArtifact:
    """
    Represents a build artifact produced by a BuildStrategy.
    """

    kind: str  # e.g., "buildpack", "docker-image"
    location: str  # e.g., "/path/to/app/venv", "my-app:latest"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentInfo:
    protocol: str
    address: str
    port: int | None = None


#
# --- Protocols (Interfaces for the Strategies) ---
#
class BuildStrategy(Protocol):
    """Interface for turning source code into a runnable artifact."""

    name: str
    context: DeploymentContext

    # @property
    # def name(self) -> str:
    #     """A unique name for the strategy, e.g., 'buildpack' or 'docker'."""

    def accept(self) -> bool:
        """Return True if this strategy can build the app."""

    def build(self) -> BuildArtifact:
        """Execute the build process and return an artifact."""


class DeploymentStrategy(Protocol):
    """Interface for running a build artifact."""

    name: str

    context: DeploymentContext
    artifact: BuildArtifact

    # @property
    # def name(self) -> str:
    #     """A unique name, e.g., 'uwsgi' or 'docker-compose'."""

    def accept(self) -> bool:
        """Return True if this target can deploy the given artifact."""

    def deploy(self, deltas: dict[str, int] | None = None) -> dict:
        """
        Deploy the artifact.
        Returns a dictionary with deployment details for the proxy,
        e.g., {"protocol": "http", "host": "127.0.0.1", "port": 8000}.
        """

    def scale(self, deltas: dict[str, int] | None = None) -> None: ...

    def stop(self) -> None: ...


class Proxy(Protocol):
    """A protocol for defining a proxy interface.

    This defines the required attributes and methods
    that any proxy (like Nginx, Apache Httpd, etc.) should implement.
    It provides an abstraction layer to
    manage communication and configuration of different web server front-ends.

    Attributes:
    - app (App): An instance of the App class representing the application to be proxied.
    - env (Env): An instance of the Env class representing the environment configuration.
    - workers (dict[str, str]):
        A dictionary representing worker configurations with keys as worker names and
        values as their respective settings.
    """

    app: App
    env: Env
    workers: dict[str, str]

    def setup(self) -> None: ...
