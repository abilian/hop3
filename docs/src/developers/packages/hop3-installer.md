# hop3-installer Deep Dive

This document provides detailed internal documentation for the hop3-installer package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-installer serves two distinct purposes:

1. **Production installers** (`hop3-install`) - Single-file scripts for end users
2. **Developer deployment** (`hop3-deploy`) - Tool for development workflow

Both are designed with no external dependencies (stdlib only for installers).

## Module Structure

```
hop3_installer/
├── __init__.py
├── main.py              # Unified entry point for hop3-install
├── common.py            # Shared utilities (Colors, run_cmd, env helpers)
├── constants.py         # Shared constants (paths, defaults, package names)
├── bundler.py           # Single-file installer bundler
├── validators.py        # Installation validators (CLI + server)
├── nginx_templates.py   # Nginx and systemd unit templates
├── cli_installer/       # CLI installer (hop3-install cli)
│   ├── config.py        # CLIInstallerConfig dataclass
│   └── installer.py     # CLI installation logic
├── server_installer/    # Server installer (hop3-install server)
│   ├── config.py        # ServerInstallerConfig dataclass
│   └── installer.py     # Full server setup orchestration
└── deployer/            # Developer deployment (hop3-deploy)
    ├── cli.py           # hop3-deploy CLI (argparse)
    ├── deploy.py        # Deployer class orchestration
    ├── config.py        # DeployConfig dataclass
    └── backends/
        ├── base.py      # DeployBackend abstract base class
        ├── ssh.py       # SSHDeployBackend
        └── docker.py    # DockerDeployBackend
```

The `cli_installer/` and `server_installer/` packages use only the Python standard library so they can be bundled into self-contained single-file scripts. The `deployer/` package is a developer tool and is never bundled.

## Single-File Bundling

The bundler combines multiple Python modules into a single script:

### Bundling Process

```python
def bundle_installer(installer_type: str) -> str:
    """Bundle an installer into a single file.

    installer_type is "cli" or "server"; returns the bundled source.
    """
    # 1. Pick the ordered module list (CLI_MODULES or SERVER_MODULES)
    modules = CLI_MODULES if installer_type == "cli" else SERVER_MODULES

    # 2. For each module: collect stdlib imports, strip relative imports
    #    and docstrings, and inline the code body. Detect top-level name
    #    collisions across modules and abort if any are found.

    # 3. Emit a header (shebang, Python version check), the deduplicated
    #    stdlib import block, the inlined module bodies, and an entry point.

    # 4. Validate the result with ast.parse() before returning it.
    ...
```

The bundler returns the source as a string; the CLI (`hop3-install bundle`) and `DeployConfig.installer_path` write it to disk and `chmod 0o755` it. Module order matters — `common.py` and `constants.py` come first because later modules depend on them.

### Why Single-File?

- **No pip required** - Works on fresh systems
- **Curl-friendly** - `curl ... | python3 -`
- **Offline capable** - Copy and run
- **Auditable** - Single file to review

## CLI Installer (`hop3-install cli`)

Installs hop3-cli on local machines:

### Installation Steps

1. Check system requirements (Python 3.10+)
2. Create a dedicated virtual environment at `~/.hop3-cli/venv`
3. Install the `hop3-cli` package (from PyPI by default, or `--git` / a local path)
4. Symlink the `hop3` and `hop` commands into `~/.local/bin`
5. Configure PATH in the user's shell config (unless `--no-modify-path`)
6. Verify the installation

The CLI is installed into its own venv with command symlinks rather than via pipx or `pip install --user`, which keeps the install self-contained and easy to remove (`rm -rf ~/.hop3-cli`).

### Configuration

```python
@dataclass
class CLIInstallerConfig:
    version: str | None = None
    use_git: bool = False
    branch: str = "main"
    local_path: str | None = None
    bin_dir: Path = Path.home() / ".local" / "bin"
    force: bool = False
    no_modify_path: bool = False
    verbose: bool = False
```

## Server Installer (`hop3-install server`)

Installs hop3-server on target machines (requires root):

### Installation Steps

The server installer runs as a numbered sequence of steps (see `server_installer/installer.py`):

1. **System dependencies** — install base system packages (nginx, uwsgi, git, etc.) plus the catalogue-derived baseline on Debian/Fedora
2. **Create `hop3` user and group**
3. **Create the Python virtual environment** at `/home/hop3/venv`
4. **Install the `hop3-server` package** into the venv
5. **Run initial setup** (`hop3-server` first-run setup)
6. **Configure SSH keys**
7. **Set up systemd services** (writes the secret key, unit files)
8. **Set up self-signed SSL certificates**
9. **Configure nginx** (and install `hop3-rootd`, the privileged-operations daemon required for nginx reloads on the deploy path)
10. **Configure PostgreSQL** (the default database)
11. **Configure MySQL** (only when requested with `--with mysql`)

Optional toolchains (Rust, Node global packages, Leiningen, Elixir, Nix) and extra features (`redis`, `s3`, `docker`) are installed when requested via `--with`. A final verification step checks the resulting install.

### Directory Structure Created

```
/home/hop3/
├── venv/               # Python virtual environment (hop3-server, uwsgi, hop3-rootd)
├── apps/               # Per-app deployment trees
├── nginx/              # Per-app nginx config fragments
├── uwsgi-available/    # uWSGI app configs
├── uwsgi-enabled/      # Active uWSGI configs (symlinks watched by the emperor)
├── ssl/                # Per-domain SSL certificates
└── hop3.db             # SQLite database (only when SQLite is used)

/etc/hop3/ssl/          # Self-signed cert/key for initial nginx setup

/etc/nginx/sites-enabled/hop3   # Main nginx site (or conf.d/hop3.conf on RHEL)

/etc/systemd/system/
├── hop3-server.service        # The API server
└── uwsgi-hop3.service         # uWSGI emperor

/etc/default/hop3              # EnvironmentFile read by the systemd units
```

The default database is PostgreSQL (step 10); `hop3.db` only exists for SQLite-backed installs. The `apps/`, `uwsgi-available/`, and `uwsgi-enabled/` directories under `/home/hop3` are created and populated when apps are deployed, not by the installer itself.

## Developer Deployer (`hop3-deploy`)

Tool for deploying during development:

### Backends

Both backends subclass `DeployBackend` and implement the same interface: `setup()`, `run()`, `upload_file()`, `upload_dir()`, `is_hop3_installed()`, `clean()`, `teardown()`, and `get_server_url()`. They take a `DeployConfig`.

#### SSH Backend

```python
class SSHDeployBackend(DeployBackend):
    def __init__(self, config: DeployConfig):
        ...  # reads config.host, config.ssh_user, config.ssh_port

    def setup(self) -> bool:
        """Verify connectivity to the remote host."""
        ...

    def run(self, command: str, *, check: bool = True,
            stdin: str | None = None) -> CommandResult:
        """Run a command on the remote host."""
        ...

    def upload_file(self, local_path: Path, remote_path: str) -> bool: ...
    def upload_dir(self, local_path: Path, remote_path: str) -> bool: ...
```

#### Docker Backend

```python
class DockerDeployBackend(DeployBackend):
    def __init__(self, config: DeployConfig):
        self.container_name = config.docker_container  # default: hop3-dev
        self.image = self.TEST_IMAGE                   # falls back to ubuntu:24.04

    def setup(self) -> bool:
        """Start the container (with supervisor as the process manager)."""
        ...

    def run(self, command: str, *, check: bool = True,
            stdin: str | None = None) -> CommandResult:
        """Run a command inside the container."""
        ...
```

### Deployment Flow

```
hop3-deploy --local

1. Check target connectivity (SSH or Docker)
2. If --clean: remove existing installation
3. If --local:
   a. Upload local package source to the target
   b. Run the installer against the uploaded source
4. Else: run the installer, which installs from PyPI by default
   (--git installs from git, --version pins a PyPI release)
5. If --admin-domain:
   a. Configure the admin interface
   b. Create the admin user
6. Configure local CLI (unless --no-cli-setup)
```

The default install source is PyPI. Use `--git` (optionally `--branch`) to install from the repository, or `--local` to upload and use working-tree code.

## Installation Validators

The `validators.py` module provides validation functions used both as post-install self-tests (run by the installers themselves) and by E2E tests through the deploy backends. Each validator takes a `runner` callable that executes a shell command and returns a `CommandResult`, so the same logic works locally (`LocalRunner`) or remotely (a deploy backend's `run`):

```python
def validate_cli_installation(runner: CommandRunner) -> bool:
    """Check the CLI venv, the hop3/hop commands, and the PATH symlink."""
    ...

def validate_server_installation(
    runner: CommandRunner,
    *,
    check_systemd: bool = True,
    verbose: bool = False,
) -> bool:
    """Check the hop3 user, venv, hop3-server binary, and (optionally)
    systemd services: hop3-server, PostgreSQL, and nginx."""
    ...
```

`check_systemd=False` is used on Docker targets that run supervisor instead of systemd, where the systemd service checks would not apply.

Broader app/deploy testing lives in the separate `hop3-testing` package (`hop3-test`), which deploys Hop3 to Docker or SSH targets and then deploys and verifies real apps. See the [hop3-testing overview](hop3-testing.md).

## Environment Variables

### For hop3-deploy

| Variable | Description |
|----------|-------------|
| `HOP3_DEV_HOST` | Target server hostname (alias: `HOP3_TEST_SERVER`) |
| `HOP3_SSH_USER` | SSH user (default: root) |
| `HOP3_GIT` | Install from git instead of PyPI (PyPI is the default) |
| `HOP3_BRANCH` | Git branch to deploy (implies `HOP3_GIT`, default: devel) |
| `HOP3_LOCAL` | Upload and use local working-tree code |
| `HOP3_CLEAN` | Clean before deploy |
| `HOP3_DOCKER` | Use the Docker backend instead of SSH |

### For hop3-install server

| Variable | Description |
|----------|-------------|
| `HOP3_DOMAIN` | Server domain name (for nginx / ACME) |
| `HOP3_ACME_EMAIL` | Email for Let's Encrypt registration |
| `HOP3_WITH` | Optional features (comma-separated: `mysql`, `redis`, `docker`, `nix`, `s3`, `rust`, or `all`) |
| `HOP3_VERSION` | Specific PyPI version to install |
| `HOP3_GIT` | Install from git instead of PyPI |
| `HOP3_BRANCH` | Git branch (implies `HOP3_GIT`) |

PostgreSQL is always installed as the default database; there is no database-type environment variable.

## Security Considerations

- **Root required** - Server installer must run as root
- **SSH keys** - Deployer uses SSH key authentication; it never prompts interactively for a password
- **Admin password** - The deployer auto-generates an admin password when one isn't supplied, and passes it to the server via stdin (not argv) so it never appears in process listings; it's shown only with `--verbose` and only when a new admin user is created
- **Minimal privileges** - The `hop3` user has minimal system access

## Debugging

### Common Issues

| Issue | Check |
|-------|-------|
| SSH connection fails | `ssh -v user@host` |
| Docker container won't start | `docker logs hop3-dev` |
| Service not starting | `journalctl -u hop3-server` |
| Permissions errors | Check hop3 user ownership |

### Verbose Mode

```bash
hop3-deploy --verbose  # Detailed output
hop3-deploy --dry-run  # Show what would happen
```
