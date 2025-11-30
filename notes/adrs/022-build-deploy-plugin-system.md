# ADR-022: Build and Deployment Plugin System

Status: `Accepted`

## Context

The original Hop3 architecture combined build and deployment logic into a monolithic class with hardcoded conditionals for different application types. Supporting new build systems (Docker, Nix) or deployment targets (Kubernetes, external orchestrators) required invasive core changes. With the pluggable architecture (ADR-020), build and deployment became the first two stages of the pipeline, with a key principle: **the application's codebase determines which strategies are used**.

## Decision

We implement build and deployment as a two-stage plugin system with **per-application auto-detection**:

1. **Per-Application Selection:** Each application auto-detects appropriate build and deployment strategies based on its codebase
2. **Two Protocol Interfaces:** `Builder` and `Deployer` define interfaces with `accept()` methods
3. **Plugin Discovery:** Strategies discovered via `get_builders()` and `get_deployers()` hookspecs
4. **Data Flow Pipeline:** `DeploymentContext` → `BuildArtifact` → `DeploymentInfo`
5. **Orchestration:** `do_deploy(app, deltas)` coordinates the pipeline

## Build Plugin Interface

### Builder Protocol

```python
class Builder(Protocol):
    """Interface for turning source code into a runnable artifact."""

    name: str                    # Strategy identifier (e.g., "python", "docker")
    context: DeploymentContext   # Application context

    def accept(self) -> bool:
        """Return True if this strategy can build the app.

        Examine the application's source code to determine compatibility:
        - DockerBuilder: Checks for Dockerfile/Containerfile
        - PythonBuilder: Checks for requirements.txt, pyproject.toml, setup.py
        - NodeBuilder: Checks for package.json
        - StaticBuilder: Checks for HTML files, no build requirements

        Returns:
            bool: True if strategy can handle this application
        """

    def build(self) -> BuildArtifact:
        """Execute build and return artifact descriptor.

        Performs the build process:
        1. Set up build environment (venv, node_modules, etc.)
        2. Install dependencies
        3. Compile/transpile code if needed
        4. Return artifact descriptor

        Returns:
            BuildArtifact: Descriptor of the built artifact

        Raises:
            RuntimeError: If build fails
            FileNotFoundError: If required files missing
        """
```

### BuildArtifact Data Structure

```python
@dataclass
class BuildArtifact:
    """Describes a build artifact produced by a Builder."""

    kind: str         # Artifact type: "buildpack", "docker-image", "nix-closure", "static"
    location: str     # Path or identifier: "/path/to/venv", "myapp:latest"
    metadata: dict[str, Any]  # Additional strategy-specific data

# Examples:
BuildArtifact(
    kind="buildpack",
    location="/home/hop3/apps/myapp/.venv",
    metadata={"python_version": "3.11", "packages": 42}
)

BuildArtifact(
    kind="docker-image",
    location="myapp:f8a9c3d",
    metadata={"size_mb": 250, "layers": 12}
)

BuildArtifact(
    kind="static",
    location="/home/hop3/apps/landing-page",
    metadata={"files": 15, "total_size": 1024000}
)
```

### DeploymentContext Input

```python
@dataclass
class DeploymentContext:
    """Context information passed to build and deployment strategies."""

    app_name: str          # Application identifier
    source_path: Path      # Path to application source code
    app_config: dict       # Parsed Procfile and hop3.toml
    app: App | None        # Full App ORM object (optional)

# Example:
DeploymentContext(
    app_name="myapp",
    source_path=Path("/home/hop3/repos/myapp"),
    app_config={
        "workers": {
            "web": "gunicorn app:app",
            "worker": "celery -A tasks worker"
        }
    },
    app=<App object>
)
```

## Deployment Plugin Interface

### Deployer Protocol

```python
class Deployer(Protocol):
    """Interface for running a build artifact."""

    name: str                    # Strategy identifier
    context: DeploymentContext   # Application context
    artifact: BuildArtifact      # Build artifact to deploy

    def accept(self) -> bool:
        """Return True if this strategy can deploy the artifact.

        Check artifact compatibility:
        - UWSGIDeployer: Accepts "buildpack" artifacts (native builds)
        - DockerDeployer: Accepts "docker-image" artifacts
        - StaticDeployer: Accepts "static" artifacts

        Returns:
            bool: True if strategy can deploy this artifact
        """

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy the artifact and return connection information.

        Performs deployment:
        1. Create/update worker processes
        2. Configure environment variables
        3. Start/restart services
        4. Return connection details for proxy

        Args:
            deltas: Worker scaling adjustments {"web": 1, "worker": -1}
                   Positive = add workers, Negative = remove workers

        Returns:
            DeploymentInfo: Connection details for reverse proxy

        Raises:
            RuntimeError: If deployment fails
        """

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scale worker processes up or down.

        Args:
            deltas: Worker adjustments {"web": 2} adds 2 web workers
        """

    def stop(self) -> None:
        """Stop all workers for this application."""
```

### DeploymentInfo Data Structure

```python
@dataclass
class DeploymentInfo:
    """Connection information returned by deployment strategies."""

    protocol: str         # "http", "uwsgi", "fastcgi"
    address: str          # Socket path or IP: "/tmp/app.sock", "127.0.0.1"
    port: int | None      # Port number or None for Unix sockets

# Examples:
DeploymentInfo(
    protocol="uwsgi",
    address="/tmp/myapp-web.sock",
    port=None
)

DeploymentInfo(
    protocol="http",
    address="127.0.0.1",
    port=8000
)
```

## Plugin Registration

### Build Plugin Example

```python
from hop3.core.hooks import hookimpl

class NativeBuildPlugin:
    """Plugin providing native build strategies for various languages."""

    name = "native-build"

    @hookimpl
    def get_builders(self) -> list:
        """Return list of build strategy classes."""
        return [
            PythonBuilder,
            NodeBuilder,
            RubyBuilder,
            GoBuilder,
            StaticBuilder,
        ]

plugin = NativeBuildPlugin()
```

### Deployment Plugin Example

```python
class UWSGIPlugin:
    """Plugin providing uWSGI deployment strategy."""

    name = "uwsgi-deploy"

    @hookimpl
    def get_deployers(self) -> list:
        """Return list of deployment strategy classes."""
        return [UWSGIDeployer]

plugin = UWSGIPlugin()
```

## Configuration

### Auto-Detection (Current Default)

Applications are automatically detected based on files present:

```bash
# Python app with requirements.txt
$ ls myapp/
requirements.txt  app.py  Procfile
# → Auto-selects: PythonBuilder → UWSGIDeployer

# Node.js app with package.json
$ ls webapp/
package.json  server.js  Procfile
# → Auto-selects: NodeBuilder → UWSGIDeployer

# Static HTML site
$ ls landing/
index.html  style.css  images/
# → Auto-selects: StaticBuilder → StaticDeployer
```

### Explicit Configuration (Planned)

Override auto-detection in `hop3.toml`:

```toml
[build]
strategy = "docker"  # Force Docker build

[deploy]
strategy = "docker"  # Force Docker deployment
```

**Status:** Not yet implemented. Auto-detection works well for current use cases.

## Complete Example: Python Application

### PythonBuilder Implementation

```python
@dataclass
class PythonBuilder:
    """Build strategy for Python applications."""

    name: str = "python"
    context: DeploymentContext

    def accept(self) -> bool:
        """Check if this is a Python application."""
        source = self.context.source_path
        return (
            (source / "requirements.txt").exists()
            or (source / "pyproject.toml").exists()
            or (source / "setup.py").exists()
        )

    def build(self) -> BuildArtifact:
        """Build Python application with virtualenv."""
        venv_path = self.context.source_path / ".venv"

        # 1. Create virtualenv
        run(["python3", "-m", "venv", str(venv_path)])

        # 2. Install dependencies
        pip = venv_path / "bin" / "pip"
        run([str(pip), "install", "-r", "requirements.txt"])

        # 3. Return artifact descriptor
        return BuildArtifact(
            kind="buildpack",
            location=str(venv_path),
            metadata={
                "python_version": self._get_python_version(),
                "packages": self._count_packages(venv_path),
            }
        )
```

### UWSGIDeployer Implementation

```python
@dataclass
class UWSGIDeployer:
    """Deployment strategy using uWSGI application server."""

    name: str = "uwsgi"
    context: DeploymentContext
    artifact: BuildArtifact

    def accept(self) -> bool:
        """Check if artifact is compatible."""
        return self.artifact.kind == "buildpack"

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy using uWSGI."""
        workers = self.context.app_config["workers"]
        sockets = {}

        # 1. Create uWSGI config for each worker
        for worker_name, command in workers.items():
            socket_path = f"/tmp/{self.context.app_name}-{worker_name}.sock"
            sockets[worker_name] = socket_path

            uwsgi_config = self._generate_uwsgi_config(
                app_name=self.context.app_name,
                command=command,
                socket=socket_path,
                venv=self.artifact.location,
            )

            config_file = Path(f"/tmp/{worker_name}.ini")
            config_file.write_text(uwsgi_config)

        # 2. Start/restart uWSGI processes
        for worker_name, socket in sockets.items():
            run(["uwsgi", "--ini", f"/tmp/{worker_name}.ini"])

        # 3. Return connection info for first worker (web)
        return DeploymentInfo(
            protocol="uwsgi",
            address=sockets["web"],
            port=None
        )

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scale workers up/down."""
        for worker_name, delta in (deltas or {}).items():
            if delta > 0:
                # Add workers
                for _ in range(delta):
                    self._spawn_worker(worker_name)
            elif delta < 0:
                # Remove workers
                for _ in range(abs(delta)):
                    self._terminate_worker(worker_name)

    def stop(self) -> None:
        """Stop all uWSGI workers."""
        run(["pkill", "-f", f"uwsgi.*{self.context.app_name}"])
```

## Orchestration: do_deploy()

The orchestrator coordinates the pipeline:

```python
def do_deploy(app: App, deltas: dict[str, int] | None = None) -> None:
    """Deploy application using pluggable strategies.

    Args:
        app: Application to deploy
        deltas: Optional worker scaling adjustments
    """
    # 1. Create deployment context
    context = DeploymentContext(
        app_name=app.name,
        source_path=app.src_path,
        app_config=AppConfig.from_dir(app.app_path).to_dict(),
        app=app,
    )

    # 2. Select and run builder
    builder = get_builder(context)  # Auto-detects via accept()
    log(f"Building with: {builder.name}")

    artifact = builder.build()
    log(f"Built: {artifact.kind} at {artifact.location}")

    # 3. Select and run deployment strategy
    deployer = get_deployment_strategy(context, artifact)
    log(f"Deploying with: {deployer.name}")

    deployment_info = deployer.deploy(deltas)
    log(f"Deployed: {deployment_info.protocol}://{deployment_info.address}")

    # (Proxy configuration happens separately - see ADR-021)
```

### Strategy Selection Functions

```python
def get_builder(context: DeploymentContext) -> Builder:
    """Find and instantiate appropriate builder.

    Tries each registered builder's accept() method until one returns True.

    Args:
        context: Application context

    Returns:
        Builder instance ready to build

    Raises:
        RuntimeError: If no strategy accepts the application
    """
    pm = get_plugin_manager()
    strategy_classes = flatten(pm.hook.get_builders())

    for strategy_class in strategy_classes:
        strategy = strategy_class(context)
        if strategy.accept():
            return strategy

    raise RuntimeError("No build strategy found for this application")


def get_deployment_strategy(
    context: DeploymentContext,
    artifact: BuildArtifact
) -> Deployer:
    """Find and instantiate appropriate deployment strategy.

    Tries each registered strategy's accept() method until one accepts the artifact.

    Args:
        context: Application context
        artifact: Build artifact from build stage

    Returns:
        Deployer instance ready to deploy

    Raises:
        RuntimeError: If no strategy accepts the artifact
    """
    pm = get_plugin_manager()
    strategy_classes = flatten(pm.hook.get_deployers())

    for strategy_class in strategy_classes:
        strategy = strategy_class(context, artifact)
        if strategy.accept():
            return strategy

    raise RuntimeError(f"No deployment strategy for artifact kind '{artifact.kind}'")
```

## Rationale

### Why Per-Application (Not Server-Wide)?

Unlike proxy (server-wide, ADR-021), build and deployment must be **per-application**:

- **Different Requirements:** Python apps need pip/venv, Node apps need npm, static sites need no build
- **No Shared Resource:** Each app has independent build and processes (unlike shared reverse proxy)
- **Flexibility:** Different apps on same server use different strategies
- **Isolation:** Build/deploy failures isolated to individual applications

**Alternative Rejected:** Server-wide build/deploy strategy would force all applications to use the same approach.

### Why Auto-Detection (Not Explicit Config)?

**Convention over configuration:**

- **Developer Experience:** Most applications "just work" without configuration
- **Simplicity:** No need to learn strategy names for common cases
- **Flexibility:** Explicit configuration remains available for edge cases

**Example:** Application with `requirements.txt` automatically uses `PythonBuilder` → `UWSGIDeployer`

### Why Two Separate Stages?

Separating build from deployment enables composition:

- **Mix and Match:** Docker build + Kubernetes deploy, Nix build + uWSGI deploy
- **Reuse Artifacts:** Build once, deploy to multiple environments
- **Clear Separation:** Build concerns (dependencies) vs runtime concerns (processes)

## Consequences

### Benefits

1. **Application Flexibility:** Each app uses the approach that suits its needs
2. **Automatic Detection:** Most apps work without configuration
3. **Extensibility:** New strategies added as plugins
4. **Clear Data Flow:** Explicit data structures between stages
5. **Composability:** Build and deployment strategies can be mixed

### Drawbacks

1. **Complexity:** More moving parts than monolithic deployer
2. **Configuration Overhead:** When auto-detection fails, users need to understand plugin system
3. **Strategy Conflicts:** Multiple strategies might accept same application (resolved by ordering)

### Trade-offs Considered

| Aspect | Decision | Alternative | Why Rejected |
|--------|----------|-------------|--------------|
| **Scope** | Per-application | Server-wide | Apps have different build requirements |
| **Selection** | Auto-detection | Explicit config | Better UX, config available for edge cases |
| **Stages** | Separate build/deploy | Combined | Enables composition and artifact reuse |
| **Interface** | Protocol | ABC | Structural typing more Pythonic |

## Implementation Status

**Fully Implemented.** Current strategies:

**Build:**
- `NativeBuildPlugin` - Python, Node.js, Ruby, Go, Clojure, Static sites
- `DockerBuilder` - Docker-based builds (in progress)

**Deployment:**
- `UWSGIDeployer` - uWSGI application server with Unix sockets
- `StaticDeployer` - Static file serving via reverse proxy
- `DockerDeployer` - Container deployment (in progress)

## Prior Art

- **Heroku Buildpacks:** Auto-detection based on files (e.g., `requirements.txt`)
- **Cloud Foundry Buildpacks:** Similar auto-detection with pluggable strategies
- **Kubernetes Operators:** Separate concerns into distinct controllers
- **GitLab CI/CD:** Pipeline stages with clear data flow

## References

- [ADR-020: Pluggable Architecture](./020-pluggable-architecture.md)
- [ADR-021: Proxy Plugin System](./021-proxy-plugin-system.md)
- [Heroku Buildpacks](https://devcenter.heroku.com/articles/buildpacks)
- [Python Protocol (PEP 544)](https://peps.python.org/pep-0544/)
