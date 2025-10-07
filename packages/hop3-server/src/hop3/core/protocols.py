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

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """
        Deploy the artifact.
        Returns a dictionary with deployment details for the proxy,
        e.g., {"protocol": "http", "host": "127.0.0.1", "port": 8000}.
        """

    def scale(self, deltas: dict[str, int] | None = None) -> None: ...

    def stop(self) -> None: ...


class ServiceStrategy(Protocol):
    """Interface for managing backing services (databases, caches, etc.).

    A service represents a resource that applications can attach to,
    like PostgreSQL, Redis, or Elasticsearch. Services are created independently
    and can be shared across multiple applications.

    Attributes:
    - name (str): A unique name for the service type, e.g., 'postgres' or 'redis'.
    - service_name (str): The specific instance name for this service.
    """

    name: str
    service_name: str

    def create(self) -> None:
        """Create the service instance.

        This should provision the necessary resources for the service,
        such as creating a database, user, or cache instance.
        """

    def destroy(self) -> None:
        """Destroy the service instance.

        This should completely remove all resources associated with the service,
        including data. This operation should be idempotent.
        """

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this service.

        Returns:
            A dictionary of environment variable names and values that
            applications need to connect to this service.
            For example: {"DATABASE_URL": "postgresql://user:pass@host/db"}
        """

    def backup(self) -> Path:
        """Create a backup of the service data.

        Returns:
            Path to the backup file or directory.
        """

    def restore(self, backup_path: Path) -> None:
        """Restore service data from a backup.

        Args:
            backup_path: Path to the backup file or directory to restore from.
        """

    def info(self) -> dict[str, Any]:
        """Get information about the service instance.

        Returns:
            Dictionary with service details like status, version, size, etc.
        """


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
