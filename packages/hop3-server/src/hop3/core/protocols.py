# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from abc import ABC, abstractmethod
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
    app: App | None = None  # The full App object from the database

    def __post_init__(self):
        assert self.source_path.is_dir()

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


@dataclass(frozen=True)
class BaseProxy(ABC):
    """Abstract base class for proxy implementations.

    This class provides common functionality for all proxy strategies
    (Nginx, Caddy, Traefik, etc.) to eliminate code duplication.

    Concrete proxy classes should inherit from this and implement
    the abstract methods for proxy-specific behavior.
    """

    app: App
    env: Env
    workers: dict[str, str]

    @property
    def app_name(self) -> str:
        """Get the application name."""
        return self.app.name

    @property
    def app_path(self) -> Path:
        """Get the application directory path."""
        return self.app.app_path

    @property
    def src_path(self) -> Path:
        """Get the application source directory path."""
        return self.app.src_path

    @abstractmethod
    def get_proxy_name(self) -> str:
        """Return the proxy name (e.g., 'nginx', 'caddy', 'traefik').

        This is used to construct proxy-specific environment variable names.
        """

    def update_env(self, key: str, value: str = "", template: str = "") -> None:
        """Update an environment variable, optionally from a template.

        Args:
            key: Environment variable name
            value: Value to set (used if template is empty)
            template: Template string to format with current env vars
        """
        if template:
            value = template.format(**self.env)
        self.env[key] = value

    def setup(self) -> None:
        """Configure the proxy environment for the application.

        This orchestrates the setup process by calling various setup methods
        in the correct order. This method is the same for all proxies.
        """
        self.setup_backend()
        self.setup_certificates()
        self.setup_cache()
        self.setup_static()
        self.extra_setup()
        self.generate_config()
        self.check_config()
        self.reload_proxy()

    @abstractmethod
    def setup_backend(self) -> None:
        """Configure the backend connection (TCP or Unix socket)."""

    @abstractmethod
    def setup_certificates(self) -> None:
        """Setup SSL certificates for the application."""

    @abstractmethod
    def setup_cache(self) -> None:
        """Configure caching for the application."""

    @abstractmethod
    def setup_static(self) -> None:
        """Configure static file serving."""

    @abstractmethod
    def extra_setup(self) -> None:
        """Perform additional proxy-specific setup."""

    @abstractmethod
    def generate_config(self) -> None:
        """Generate the proxy configuration file."""

    @abstractmethod
    def check_config(self) -> None:
        """Validate the generated proxy configuration."""

    @abstractmethod
    def reload_proxy(self) -> None:
        """Reload the proxy to apply configuration changes."""

    def get_static_paths(self) -> list[tuple[str, Path]]:
        """Get a mapping of static URL prefixes to file system paths.

        This method is identical across all proxy implementations,
        only the environment variable name differs.

        Returns:
            list of tuples: Each tuple contains a URL prefix and Path object.
        """
        proxy_name = self.get_proxy_name().upper()
        static_paths = self.env.get(f"{proxy_name}_STATIC_PATHS", "")

        # Prepend static worker path if present
        if "static" in self.workers:
            stripped = self.workers["static"].strip("/").rstrip("/")
            if stripped.startswith(":"):
                prefix = "/"
            else:
                prefix = "/:"

            if not stripped:
                stripped = "."

            separator = "," if static_paths else ""
            static_paths = prefix + stripped + "/" + separator + static_paths

        items = static_paths.split(",") if static_paths else []

        result = []
        for item in items:
            static_url, static_path_str = item.split(":")
            static_path_str = static_path_str.rstrip()
            if static_path_str[0] == "/":
                # Use absolute path
                static_path = Path(static_path_str)
            else:
                # Use relative path based on src_path
                static_path = self.src_path / static_path_str
            result.append((static_url, static_path))

        return result


class OSSetupStrategy(Protocol):
    """Interface for OS-specific server setup and configuration.

    An OS setup strategy handles the installation of dependencies and
    system configuration for a specific Linux distribution and version.
    This allows hop3 to support multiple operating systems through plugins.

    Attributes:
    - name (str): Unique identifier for this OS, e.g., 'debian12', 'ubuntu2204'
    - display_name (str): Human-readable name, e.g., 'Debian 12 (Bookworm)'
    - packages (list[str]): List of system packages required for hop3
    """

    name: str
    display_name: str
    packages: list[str]

    def detect(self) -> bool:
        """Check if this strategy matches the current operating system.

        This should read /etc/os-release or similar system files to
        determine if the current OS matches this strategy.

        Returns:
            True if this strategy should be used for the current OS.
        """

    def setup_server(self) -> None:
        """Install dependencies and configure the system for hop3.

        This should:
        1. Configure package manager settings (e.g., APT config)
        2. Create the hop3 user account
        3. Install required system packages
        4. Set up necessary symbolic links or system configurations

        This method should be idempotent - safe to run multiple times.
        """

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install system packages using the OS package manager.

        Args:
            packages: List of package names to install
            update: Whether to update package lists before installing
        """

    def ensure_user(self, user: str, home: str, shell: str, group: str) -> None:
        """Create a system user account if it doesn't exist.

        Args:
            user: Username to create
            home: Home directory path
            shell: Default shell path
            group: Primary group name
        """
