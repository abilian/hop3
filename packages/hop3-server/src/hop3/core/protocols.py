# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from dataclasses import dataclass, field
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
    source_path: str
    app_config: dict

    # app: App
    # app_config: AppConfig
    # new_rev: str
    # log_callback: Callable[[str], None]  # To stream logs back


@dataclass
class BuildArtifact:
    """
    Represents a build artifact produced by a BuildStrategy.
    """

    kind: str  # e.g., "buildpack", "docker_image"
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

    # @property
    # def name(self) -> str:
    #     """A unique name for the strategy, e.g., 'buildpack' or 'docker'."""

    def accept(self, context: DeploymentContext) -> bool:
        """Return True if this strategy can build the app."""

    def build(self, context: DeploymentContext) -> BuildArtifact:
        """Execute the build process and return an artifact."""


class DeploymentStrategy(Protocol):
    """Interface for running a build artifact."""

    name: str

    # @property
    # def name(self) -> str:
    #     """A unique name, e.g., 'uwsgi' or 'docker-compose'."""

    def accept(self, artifact: BuildArtifact, context: DeploymentContext) -> bool:
        """Return True if this target can deploy the given artifact."""

    def deploy(self, artifact: BuildArtifact, context: DeploymentContext) -> dict:
        """
        Deploy the artifact.
        Returns a dictionary with deployment details for the proxy,
        e.g., {"protocol": "http", "host": "127.0.0.1", "port": 8000}.
        """

    def scale(self, app: App, deltas: dict[str, int]) -> None: ...

    def stop(self, app: App) -> None: ...


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
