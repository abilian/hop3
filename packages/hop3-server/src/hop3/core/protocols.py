# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, NoReturn, Protocol

# BuildArtifact is imported from artifacts.py - see ADR 035
# It includes RuntimeConfig for build/run separation
from hop3.core.artifacts import (
    BuildArtifact,
    ProxySettings,
    RuntimeConfig,
    load_backend_protocol,
    load_proxy_settings,
)
from hop3.lib.diagnostics import Diagnosis, abort_with_diagnosis
from hop3.lib.path import REJECTED_SUFFIX, restore_on_failure

__all__ = ["BuildArtifact", "RuntimeConfig"]  # Re-export for backwards compatibility


if TYPE_CHECKING:
    from collections.abc import Mapping

    from hop3.orm import App
    from hop3.project.schema import WafSection

    from .env import Env


#
# --- Data Structures ---
#
@dataclass
class BuildContext:
    """
    Context for build operations (before deployment).

    Contains information needed during the build phase, before deployment.
    Separate from DeploymentContext to avoid coupling build and deploy concerns.
    """

    app_name: str
    source_path: Path
    app_config: dict

    def __post_init__(self) -> None:
        assert self.source_path.is_dir()


@dataclass
class DeploymentContext:
    """
    Context for deployment operations (after build).

    Contains information needed during the deployment phase, after build.
    """

    app_name: str
    source_path: Path
    app_config: dict
    app: App | None = None  # The full App object from the database

    def __post_init__(self) -> None:
        assert self.source_path.is_dir()

    # app_config: AppConfig
    # new_rev: str
    # log_callback: Callable[[str], None]  # To stream logs back


@dataclass
class DeploymentInfo:
    protocol: str
    address: str
    port: int | None = None


#
# --- Protocols (Interfaces for the Strategies) ---
#
class Builder(Protocol):
    """
    Top-level build orchestrator - defines HOW to build.

    Builders orchestrate the build process and may delegate to language
    toolchains for language-specific operations.

    Examples:
    - LocalBuilder: Builds on host using native language toolchains
    - DockerBuilder: Builds in container using Dockerfile
    - NixBuilder: Builds with Nix for reproducibility

    Note: This protocol will transition from DeploymentContext to BuildContext
    in future phases. Current implementations still use DeploymentContext for
    backward compatibility.
    """

    name: str
    context: DeploymentContext

    def __init__(self, context: DeploymentContext) -> None:
        """Initialize the builder with a deployment context."""
        ...

    def accept(self) -> bool:
        """Return True if this strategy can build the app."""

    def build(self) -> BuildArtifact:
        """Execute the build process and return an artifact."""


class LanguageToolchain(Protocol):
    """
    Language-specific build toolchain - defines WHAT tools to use.

    Toolchains handle language-specific build operations like installing
    dependencies, compiling code, and bundling assets.

    LanguageToolchains are used by LocalBuilder to build applications
    in specific programming languages. Other builders (DockerBuilder, NixBuilder)
    do not use toolchains.

    Examples:
    - PythonToolchain: Uses pip/uv, creates virtualenv, compiles .pyc
    - NodeToolchain: Uses npm/yarn, runs webpack, transpiles JS
    - JavaToolchain: Uses maven/gradle, compiles .class files
    """

    name: str
    context: BuildContext

    def __init__(self, context: BuildContext) -> None:
        """Initialize the toolchain with a build context."""
        ...

    def accept(self) -> bool:
        """
        Check if this toolchain applies to the project.

        Examples:
        - PythonToolchain: checks for requirements.txt or pyproject.toml
        - NodeToolchain: checks for package.json
        """

    def build(self) -> BuildArtifact:
        """Execute language-specific build and return the artifact."""


class Deployer(Protocol):
    """Interface for running a build artifact."""

    # These are set at construction and should not be mutated afterward
    name: str
    context: DeploymentContext
    artifact: BuildArtifact

    def __init__(self, context: DeploymentContext, artifact: BuildArtifact) -> None:
        """Initialize the deployer with context and build artifact."""
        ...

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

    def check_status(self) -> bool:
        """
        Check if the deployed application is actually running.

        Returns:
            True if processes/containers are confirmed running, False otherwise.

        This method should verify actual running state by checking:
        - For uWSGI: socket files, process listings, config files
        - For Docker: container status (docker ps)
        - For systemd: service status (systemctl is-active)
        - For Podman: container status (podman ps)
        - etc.

        Implementation should be reliable and not assume state based on
        configuration files alone.
        """
        ...


class Addon(Protocol):
    """
    Interface for managing addons (backing services like databases, caches, etc.).

    An addon represents a resource that applications can attach to,
    like PostgreSQL, Redis, or Elasticsearch. Addons are created independently
    and can be shared across multiple applications.

    In 12-factor app terminology, these are called "backing services" - resources
    the app consumes over the network as part of its normal operation.

    Attributes:
    - name (str): Addon type identifier, e.g., 'postgres' or 'redis'.
    - addon_name (str): The specific instance name for this addon.

    TODO: Rename 'name' to 'addon_type' for clarity
    """

    name: str
    addon_name: str

    def __init__(self, *, addon_name: str) -> None:
        """
        Initialize the addon with an instance name.

        Args:
            addon_name: The specific instance name for this addon.
        """
        ...

    def create(self) -> None:
        """
        Create the addon instance.

        This should provision the necessary resources for the addon,
        such as creating a database, user, or cache instance.
        """

    def destroy(self) -> None:
        """
        Destroy the addon instance.

        This should completely remove all resources associated with the addon,
        including data. This operation should be idempotent.
        """

    def get_connection_details(self) -> dict[str, str]:
        """
        Get environment variables for connecting to this addon.

        Returns:
            A dictionary of environment variable names and values that
            applications need to connect to this addon.
            For example: {"DATABASE_URL": "postgresql://user:pass@host/db"}
        """

    def backup(self) -> Path:
        """
        Create a backup of the addon data.

        Returns:
            Path to the backup file or directory.
        """

    def restore(self, backup_path: Path) -> None:
        """
        Restore addon data from a backup.

        Args:
            backup_path: Path to the backup file or directory to restore from.
        """

    def info(self) -> dict[str, Any]:
        """
        Get information about the addon instance.

        Returns:
            Dictionary with addon details like status, version, size, etc.
        """


class Proxy(Protocol):
    """
    A protocol for defining a proxy interface.

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

    #: Capabilities a deploy checks before it relies on them; see BaseProxy.
    backend_protocols: ClassVar[frozenset[str]]
    serves_files: ClassVar[bool]
    fronts_waf: ClassVar[bool]
    hosts_certbot: ClassVar[bool]
    gates_access: ClassVar[bool]
    refuses_paths: ClassVar[bool]

    app: App
    env: Env
    workers: dict[str, str]

    def __init__(self, app: App, env: Env, workers: dict[str, str]) -> None:
        """
        Initialize the proxy with application, environment, and worker configuration.

        Args:
            app: The application to be proxied.
            env: Environment configuration.
            workers: Worker configurations.
        """
        ...

    def setup(self) -> None: ...


#: The port hop3-server listens on (`hop3-server serve` passes it to Granian).
#: The installer's HOP3_SERVER_BIND names the same port: it is a separate,
#: stdlib-only package and keeps its own copy.
SERVER_PORT = 8000

#: Where a proxy reaches hop3-server's access-gate check (ADR 062): the
#: server's own port on loopback. It relied on Granian's default port, which
#: the server never stated.
GATE_CHECK_UPSTREAM = f"127.0.0.1:{SERVER_PORT}"

#: The request headers a gated app receives from the check's answer, never
#: from the client: the proxy deletes each, then sets those the check returned.
#: The underscore spellings are listed because a WSGI server maps them to the
#: same variable as the real header (nginx drops them on its own).
GATE_REQUEST_HEADERS = (
    "X-Hop3-User",
    "X-Hop3-Role",
    "Cookie",
    "X_Hop3_User",
    "X-Hop3_User",
    "X_Hop3-User",
    "X_Hop3_Role",
    "X-Hop3_Role",
    "X_Hop3-Role",
)


@dataclass(frozen=True)
class BaseProxy(ABC):
    """
    Abstract base class for proxy implementations.

    This class provides common functionality for all proxy strategies
    (Nginx, Caddy, Traefik, etc.) to eliminate code duplication.

    Concrete proxy classes should inherit from this and implement
    the abstract methods for proxy-specific behavior.
    """

    #: What the proxy can speak to an app's port (the build artifact's
    #: ``backend_protocol``). Proxying anything else publishes a 502.
    backend_protocols: ClassVar[frozenset[str]] = frozenset({"http"})
    #: Serves files from disk: a ``static`` worker, ``<PROXY>_STATIC_PATHS``.
    serves_files: ClassVar[bool] = True
    #: Routes an app through its LeWAF proxy (ADR 050) with a client IP the
    #: WAF can trust (its invariant 1). Proven for nginx only.
    fronts_waf: ClassVar[bool] = False
    #: Hop3 obtains and renews Let's Encrypt certificates through certbot
    #: behind it: a temporary vhost answers the first challenge, and renewal
    #: installs the certificate and reloads the proxy. Wired for nginx only.
    hosts_certbot: ClassVar[bool] = False
    #: Puts an app behind the access gate (ADR 062): forward-auth to
    #: hop3-server's check, the ``/_hop3/auth/`` route, and the identity
    #: headers and cookies the check returns, in place of the client's.
    gates_access: ClassVar[bool] = False
    #: Answers the paths an app lists in ``[proxy] deny`` with 404, without
    #: reaching the app or the disk.
    refuses_paths: ClassVar[bool] = True

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

    @property
    def proxy_settings(self) -> ProxySettings:
        """
        What this app declared the proxy may carry ([proxy] in hop3.toml).

        Identical across proxy implementations — only the directive each one
        renders differs.
        """
        return load_proxy_settings(self.app_path)

    @abstractmethod
    def get_proxy_name(self) -> str:
        """
        Return the proxy name (e.g., 'nginx', 'caddy', 'traefik').

        This is used to construct proxy-specific environment variable names.
        """
        ...

    def update_env(self, key: str, value: str = "", template: str = "") -> None:
        """
        Update an environment variable, optionally from a template.

        Args:
            key: Environment variable name
            value: Value to set (used if template is empty)
            template: Template string to format with current env vars
        """
        if template:
            value = template.format(**self.env)
        self.env[key] = value

    def setup(self) -> None:
        """
        Configure the proxy environment for the application.

        This orchestrates the setup process by calling various setup methods
        in the correct order. This method is the same for all proxies.
        """
        self.refuse_unsupported()
        self.setup_backend()
        self.setup_certificates()
        self.setup_cache()
        self.setup_static()
        self.extra_setup()
        # A config the proxy *rejects* does not stay on disk: the proxy reads
        # every file in the directory, so one left behind would break the next
        # app's deploy and every certificate renewal, naming neither.
        #
        # A failed *reload* is deliberately outside this. "Rejected" is
        # unambiguous; "the reload did not take" is not — nginx accepts a
        # reload and forks its new workers asynchronously, so a reload
        # reported as failed may have been merely slow on a loaded host and
        # already applied. Rolling back there would leave the file disagreeing
        # with what nginx is actually serving, and the next reload — another
        # app's deploy, a certificate renewal — would silently revert this
        # app's routes. A validated config left in place has no blast radius:
        # it passes `nginx -t`, so it breaks nothing, and the next reload
        # picks it up.
        with restore_on_failure(self.conf_path):
            self.generate_config()
            self.check_config()
        self.reload_proxy()

    def refuse_unsupported(self) -> None:
        """Abort, before writing any config, on an app this proxy would serve wrong."""
        proxy = self.get_proxy_name()
        protocol = load_backend_protocol(self.app_path)
        if protocol not in self.backend_protocols:
            self._refuse(
                f"the app's port speaks {protocol}, which {proxy} cannot proxy",
                hint=(
                    f"run '{self.app_name}' on a server whose proxy speaks "
                    f"{protocol}, or give it an HTTP server in [run].start"
                ),
            )
        if not self.serves_files and (paths := self.get_static_paths()):
            urls = ", ".join(url for url, _path in paths)
            self._refuse(
                f"the app serves files from disk ({urls}), and {proxy} serves no files",
                hint=(
                    f"run '{self.app_name}' on a server whose proxy serves "
                    f"files (nginx or caddy), or let the app serve them itself"
                ),
            )
        if not self.refuses_paths and (denied := self.proxy_settings.deny):
            self._refuse(
                f"the app declares [proxy] deny ({', '.join(denied)}), and "
                f"{proxy} cannot refuse a path",
                hint=(
                    f"run '{self.app_name}' on a server whose proxy refuses "
                    f"paths (nginx or caddy)"
                ),
            )

    def include_file(self, variable: str) -> str:
        """
        The proxy snippet an app names in ``variable``, or ``""`` if it names none.

        The value is a path in the app's source tree, where a recipe ships the
        file. It must stay inside that tree: the snippet is copied into the
        proxy's own configuration.
        """
        name = self.env.get(variable)
        if not name:
            return ""
        root = Path(self.src_path).resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            self._refuse(
                f"{variable}={name} points outside the app's source tree",
                hint="name a file in the app's repository, relative to its root",
            )
        if not path.is_file():
            self._refuse(
                f"{variable}={name} names no file in the app's source tree",
                hint=(
                    f"ship {name} in the app's repository, at that path from "
                    f"its root, or unset {variable}"
                ),
            )
        return path.read_text()

    def _refuse(self, reason: str, hint: str) -> NoReturn:
        abort_with_diagnosis(
            Diagnosis(
                component=self.get_proxy_name().capitalize(),
                action=f"route '{self.app_name}'",
                reason=reason,
                hint=hint,
            )
        )

    @abstractmethod
    def setup_backend(self) -> None:
        """Configure the backend connection (TCP or Unix socket)."""
        ...

    @abstractmethod
    def setup_certificates(self) -> None:
        """Setup SSL certificates for the application."""
        ...

    @abstractmethod
    def setup_cache(self) -> None:
        """Configure caching for the application."""
        ...

    @abstractmethod
    def setup_static(self) -> None:
        """Configure static file serving."""
        ...

    @abstractmethod
    def extra_setup(self) -> None:
        """Perform additional proxy-specific setup."""
        ...

    @property
    @abstractmethod
    def conf_path(self) -> Path:
        """Path of the app's config file in the proxy's include directory."""
        ...

    @property
    def rejected_conf_path(self) -> Path:
        """Where :func:`restore_on_failure` parks a config the proxy refused."""
        return self.conf_path.with_name(self.conf_path.name + REJECTED_SUFFIX)

    @abstractmethod
    def generate_config(self) -> None:
        """Generate the proxy configuration file."""
        ...

    @abstractmethod
    def check_config(self) -> None:
        """Validate the generated proxy configuration."""
        ...

    @abstractmethod
    def reload_proxy(self) -> None:
        """Reload the proxy to apply configuration changes."""
        ...

    def get_static_paths(self) -> list[tuple[str, Path]]:
        """
        Get a mapping of static URL prefixes to file system paths.

        This method is identical across all proxy implementations,
        only the environment variable name differs.

        Returns:
            list of tuples: Each tuple contains a URL prefix and Path object.
        """
        proxy_name = self.get_proxy_name().upper()
        static_paths = self.env.get(f"{proxy_name}_STATIC_PATHS", "")

        # Prepend static worker path if present
        if "static" in self.workers:
            raw_path = self.workers["static"].rstrip("/")
            if not raw_path:
                raw_path = "."

            # Build "url:path" entry. Use "/:" prefix to map "/" to the path.
            # Preserve leading "/" for absolute paths (e.g., /nix/store/...).
            separator = "," if static_paths else ""
            static_paths = "/:" + raw_path + "/" + separator + static_paths

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


Severity = Literal["ok", "warn", "fail"]


@dataclass
class HealthCheckResult:
    """
    Result of a health check.

    Attributes:
        name: Display name for this check (e.g., "MySQL", "PostgreSQL")
        passed: Whether the check passed
        message: Human-readable status message
        details: Optional dict with additional diagnostic info
        severity: Explicit severity ("ok" | "warn" | "fail"). When omitted, it
            is derived from ``passed``. Set it explicitly when the binary
            pass/fail doesn't capture the right rendering — e.g., an
            optional service that's unreachable is ``passed=False`` but
            ``severity="warn"`` (the result is unacceptable from the
            check's perspective, but the operator can still ship).
    """

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    severity: Severity | None = None

    @property
    def derived_severity(self) -> Severity:
        """Resolve the severity, defaulting from ``passed`` when not set."""
        if self.severity is not None:
            return self.severity
        return "ok" if self.passed else "fail"


class HealthCheck(Protocol):
    """
    Interface for health checks contributed by plugins.

    Health checks verify that a service or resource is properly configured
    and accessible. They are run during server startup and via the
    `system check` command.

    Attributes:
        name: Unique identifier for this health check (e.g., 'mysql', 'postgresql')

    Example implementation:
        ```python
        class MySQLHealthCheck:
            name = "mysql"

            def check(self) -> HealthCheckResult:
                try:
                    # Test MySQL connection
                    connection = mysql.connector.connect(...)
                    connection.close()
                    return HealthCheckResult(
                        name="MySQL",
                        passed=True,
                        message="Connection successful"
                    )
                except Exception as e:
                    return HealthCheckResult(
                        name="MySQL",
                        passed=False,
                        message=f"Connection failed: {e}"
                    )
        ```
    """

    name: str

    def is_configured(self) -> bool:
        """
        Check if this service is configured and should be checked.

        Returns:
            True if the service is configured (e.g., password set in config),
            False if it should be skipped.
        """
        ...

    def check(self) -> HealthCheckResult:
        """
        Perform the health check.

        Returns:
            HealthCheckResult with pass/fail status and message.
        """
        ...


class OS(Protocol):
    """
    Interface for OS-specific server setup and configuration.

    An OS setup strategy handles the installation of dependencies and
    system configuration for a specific Linux distribution and version.
    This allows hop3 to support multiple operating systems through plugins.

    Attributes:
    - name (str): Unique identifier for this OS, e.g., 'debian12', 'ubuntu2204'
    - display_name (str): Human-readable name, e.g., 'Debian 12 (Bookworm)'
    - packages (list[str]): List of system packages required for hop3
    """

    name: str

    def __init__(self) -> None:
        """
        Initialize the OS strategy.

        OS strategies are typically instantiated without arguments
        and use system introspection (e.g., /etc/os-release) to configure themselves.
        """
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for this OS."""
        ...

    @property
    def packages(self) -> list[str]:
        """List of system packages required for hop3."""
        ...

    def detect(self) -> bool:
        """
        Check if this strategy matches the current operating system.

        This should read /etc/os-release or similar system files to
        determine if the current OS matches this strategy.

        Returns:
            True if this strategy should be used for the current OS.
        """

    def setup_server(self) -> None:
        """
        Install dependencies and configure the system for hop3.

        This should:
        1. Configure package manager settings (e.g., APT config)
        2. Create the hop3 user account
        3. Install required system packages
        4. Set up necessary symbolic links or system configurations

        This method should be idempotent - safe to run multiple times.
        """

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """
        Install system packages using the OS package manager.

        Args:
            packages: List of package names to install
            update: Whether to update package lists before installing
        """

    def ensure_user(self, user: str, home: str, shell: str, group: str) -> None:
        """
        Create a system user account if it doesn't exist.

        Args:
            user: Username to create
            home: Home directory path
            shell: Default shell path
            group: Primary group name
        """


class WafEngine(Protocol):
    """
    A Layer-7 WAF engine (ADR 050).

    Compiles a per-app ``[waf]`` policy into the engine's native rules and
    manages the WAF service. LeWAF is the first implementation; Coraza can
    follow behind the same interface. ``get_waf_engines()`` returns the engine
    *classes*; the deploy flow instantiates the selected one.

    The platform supervises the proxy process itself (a uWSGI Emperor vassal,
    ADR 050 §1); the engine only generates config, validates it, and builds the
    command that runs the proxy.
    """

    name: str

    def configure_app(
        self, app_name: str, policy: WafSection, networks: Mapping[str, list[str]]
    ) -> Path:
        """
        Write the app's compiled rules; return the rules-file path.

        ``networks`` maps each named network (resolved from the operator
        registry) to its CIDRs, for gate conditions.
        """
        ...

    def remove_app(self, app_name: str) -> None:
        """Remove the app's compiled rules (on destroy / WAF disabled)."""
        ...

    def validate(self, app_name: str) -> None:
        """
        Load the compiled rules into the engine; raise on a parse error.

        The compile-before-commit gate (ADR 050 §5) — the deploy aborts rather
        than front an app with rules the engine can't load.
        """
        ...

    def proxy_command(
        self, app_name: str, upstream_url: str, listen_port: int
    ) -> list[str]:
        """
        The argv that runs the WAF proxy: fronts ``upstream_url`` for the app
        on ``listen_port`` (loopback), reading the real client IP from the single
        trusted nginx hop (Security invariant 1).
        """
        ...

    def audit_path(self, app_name: str) -> Path:
        """Path of the JSONL audit stream the proxy writes (the scorer's input)."""
        ...

    def write_bans(self, app_name: str, banned: list[str]) -> bool:
        """
        Rewrite the app's ban denylist from the active set, if it changed.

        Returns True when the file was (re)written — the scorer reloads the proxy
        only then, so an unchanged denylist never churns the running proxy
        (ADR 050 §4).
        """
        ...
