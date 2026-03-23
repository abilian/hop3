---
date: 2026-03-22
template: blog_post.html
description: Clean architecture for portable deployment artifacts.
tags:
  - Architecture
  - Engineering
---

# Separating Build and Run: The BuildArtifact Pattern

When we started Hop3, build and run were tightly coupled. The Python toolchain would create a virtualenv, and the uWSGI deployer knew to look for `venv/bin/python`. This worked until we wanted to support Docker builds, Nix builds, or running apps on different machines than they were built on.

We needed to separate concerns: **build** produces an artifact, **run** consumes it.

## The Problem

Our original code looked like this:

```python
# In deployer.py
def deploy(app: App) -> None:
    # Build and run interleaved
    if (app.src_path / "requirements.txt").exists():
        create_virtualenv(app)
        install_requirements(app)
        spawn_uwsgi(app)
    elif (app.src_path / "package.json").exists():
        npm_install(app)
        spawn_pm2(app)
    # ... many more conditions
```

Problems:
1. **Tightly coupled**: Run logic knew about build details
2. **Not portable**: Couldn't build on one machine, run on another
3. **Hard to extend**: Each new language needed changes in multiple places
4. **Implicit contracts**: How does the deployer know where Python is?

## The Solution: BuildArtifact

We introduced a `BuildArtifact` dataclass that captures everything needed to run an application:

```python
@dataclass
class RuntimeConfig:
    """How to run the application."""

    env_vars: dict[str, str] = field(default_factory=dict)
    path_prepend: list[str] = field(default_factory=list)
    working_dir: str = ""
    workers: dict[str, str] = field(default_factory=dict)
    before_run: list[str] = field(default_factory=list)
    static_paths: dict[str, str] = field(default_factory=dict)
    healthcheck_path: str = ""
    healthcheck_timeout: int = 30


@dataclass
class BuildArtifact:
    """Complete description of a built application."""

    kind: str  # "python", "node", "static", etc.
    location: str  # Root path, /nix/store path, or image reference
    runtime: RuntimeConfig
    builder: str = "local"  # "local", "nix", "docker"
    app_name: str = ""
    built_at: str = ""  # ISO 8601 timestamp
    build_id: str = ""  # Unique ID (UUID or git SHA)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Now build and run are cleanly separated:

```python
# Build phase
def build(app: App, toolchain: LanguageToolchain) -> BuildArtifact:
    artifact = toolchain.build()
    save_artifact(app.path / "BUILD_ARTIFACT.json", artifact)
    return artifact

# Run phase
def run(app: App) -> None:
    artifact = load_artifact(app.path / "BUILD_ARTIFACT.json")
    deployer = get_deployer_for_artifact(artifact)
    deployer.deploy(app, artifact)
```

## How Toolchains Produce Artifacts

Each toolchain now returns a complete `BuildArtifact`:

```python
class PythonToolchain(LanguageToolchain):
    def build(self) -> BuildArtifact:
        # Do the actual build work
        self.make_virtual_env()
        self.install_dependencies()

        # Compute runtime configuration
        venv_bin = self.virtual_env / "bin"

        runtime = RuntimeConfig(
            working_dir=str(self.src_path),
            env_vars={
                "PYTHONUNBUFFERED": "1",
                "VIRTUAL_ENV": str(self.virtual_env),
            },
            path_prepend=[str(venv_bin)],
            workers=self._get_workers(),
            before_run=self._get_before_run(),
            static_paths=self._get_static_paths(),
        )

        return BuildArtifact(
            kind="python",
            location=str(self.src_path),
            runtime=runtime,
            builder="local",
            app_name=self.app_name,
            built_at=self._get_build_timestamp(),
            build_id=self._get_build_id(),
            metadata={
                "python_path": str(venv_bin / "python"),
            },
        )
```

The artifact contains everything needed to run the app—no guessing required.

## Deployers Consume Artifacts

Deployers accept artifacts based on their `kind`:

```python
class UWSGIDeployer:
    def accept(self, artifact: BuildArtifact) -> bool:
        return artifact.kind in ("python", "ruby", "clojure")

    def deploy(self, app: App, artifact: BuildArtifact) -> None:
        # Use artifact.runtime for configuration
        env = artifact.runtime.env_vars.copy()
        env["PATH"] = ":".join(artifact.runtime.path_prepend + [os.environ["PATH"]])

        # Run before-run commands
        for cmd in artifact.runtime.before_run:
            subprocess.run(cmd, shell=True, env=env, cwd=artifact.runtime.working_dir)

        # Start workers
        for name, command in artifact.runtime.workers.items():
            self.spawn_worker(name, command, env)
```

The deployer doesn't need to know Python vs Ruby specifics—it just reads the artifact.

## Persistence

Artifacts are serialized to JSON for persistence and debugging:

```python
def save_artifact(path: Path, artifact: BuildArtifact) -> None:
    # BuildArtifact has a built-in save() method:
    artifact.save(path)

    # Which serializes to:
    # {
    #     "kind": ...,
    #     "location": ...,
    #     "builder": ...,
    #     "app_name": ...,
    #     "built_at": ...,
    #     "build_id": ...,
    #     "runtime": {...},
    #     "metadata": {...},
    # }
```

You can inspect `BUILD_ARTIFACT.json` to see exactly what was built:

```json
{
  "kind": "python",
  "location": "/home/hop3/apps/myapp/src",
  "builder": "local",
  "app_name": "myapp",
  "built_at": "2026-03-21T10:30:00Z",
  "build_id": "abc123",
  "runtime": {
    "working_dir": "/home/hop3/apps/myapp/src",
    "env_vars": {
      "PYTHONUNBUFFERED": "1",
      "VIRTUAL_ENV": "/home/hop3/apps/myapp/venv"
    },
    "path_prepend": ["/home/hop3/apps/myapp/venv/bin"],
    "workers": {
      "web": "gunicorn app:app -b 0.0.0.0:$PORT"
    },
    "before_run": ["python manage.py migrate"],
    "static_paths": {},
    "healthcheck_path": "",
    "healthcheck_timeout": 30
  },
  "metadata": {}
}
```

## Benefits

### 1. Portable Builds

Build on your CI server, run on production:

```bash
# On CI
hop3 build myapp --output artifact.json

# On production server
hop3 run myapp --artifact artifact.json
```

### 2. Debugging

When something goes wrong, inspect the artifact:

```bash
cat /home/hop3/apps/myapp/BUILD_ARTIFACT.json | jq .runtime
```

### 3. Reproducibility

The artifact captures the exact build output:

```json
{
  "build_id": "abc123def456",
  "built_at": "2026-03-21T10:30:00Z"
}
```

Roll back by keeping old artifacts.

### 4. Future Extensibility

This pattern enables:

- **Nix builds**: Produce Nix store paths as artifacts
- **Container builds**: Produce image tags as artifacts
- **Remote execution**: Ship artifacts to different machines

### 5. Simpler Deployers

Deployers went from complex language-detection logic to simple artifact consumption:

```python
# Before: 200+ lines of detection and setup
# After: 50 lines reading from artifact
```

## The RuntimeManifest Builder

Artifacts need runtime information from multiple sources:

- `Procfile`: Worker definitions
- `hop3.toml`: Configuration overrides
- Toolchain: Language-specific settings

We merge these with a `RuntimeManifestBuilder`:

```python
class RuntimeManifestBuilder:
    def build(self, artifact: BuildArtifact, hop3_config: Hop3Config) -> BuildArtifact:
        """Enhance artifact with hop3.toml configuration."""

        # Start with toolchain-provided runtime
        runtime = artifact.runtime

        # Override with hop3.toml settings
        runtime = RuntimeConfig(
            working_dir=runtime.working_dir,
            env_vars=runtime.env_vars,
            path_prepend=runtime.path_prepend,
            workers=hop3_config.named_workers or runtime.workers,
            before_run=hop3_config.pre_run or runtime.before_run,
            static_paths=hop3_config.static_paths or runtime.static_paths,
            healthcheck_path=hop3_config.healthcheck_path,
        )

        return BuildArtifact(
            kind=artifact.kind,
            location=artifact.location,
            runtime=runtime,
            builder=artifact.builder,
            app_name=artifact.app_name,
            built_at=artifact.built_at,
            build_id=artifact.build_id,
            metadata=artifact.metadata,
        )
```

Precedence: `hop3.toml` > `Procfile` > toolchain defaults.

## Migration from Legacy

We support apps that don't have artifacts yet:

```python
def get_artifact(app: App) -> BuildArtifact:
    artifact_path = app.path / "BUILD_ARTIFACT.json"

    if artifact_path.exists():
        return load_artifact(artifact_path)

    # Legacy fallback: detect and create artifact on the fly
    return create_legacy_artifact(app)
```

This lets existing deployments continue working while new deployments use proper artifacts.

## Lessons Learned

1. **Explicit is better**: Artifacts make implicit contracts explicit
2. **Serialization matters**: JSON makes debugging and tooling easy
3. **Immutability helps**: Frozen dataclasses prevent accidental mutation
4. **Layering works**: Toolchain → Manifest → Deployer is a clean pipeline

---

*Related: [Plugin Architecture](2026-01-plugin-architecture.md) explains how toolchains and deployers are structured. For the full details, see [ADR 035: Build Artifacts](/adrs/035-build-artifacts/) and the [Build System documentation](/developers/build-system/).*
