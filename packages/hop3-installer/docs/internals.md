# hop3-installer Deep Dive

This document provides detailed internal documentation for the hop3-installer package. For a quick overview, see the [package README](../README.md).

## Architecture Overview

hop3-installer serves two distinct purposes:

1. **Production installers** (`hop3-install`) - Single-file scripts for end users
2. **Developer deployment** (`hop3-deploy`) - Tool for development workflow

Both are designed with no external dependencies (stdlib only for installers).

## Module Structure

```
hop3_installer/
├── __init__.py
├── main.py              # Unified entry point
├── common.py            # Shared utilities (Colors, Spinner)
├── bundler.py           # Single-file bundler
├── cli/
│   ├── config.py        # CLI installer configuration
│   └── installer.py     # CLI installation logic
├── server/
│   ├── config.py        # Server installer configuration
│   └── installer.py     # Server installation logic
├── deployer/
│   ├── cli.py           # hop3-deploy CLI
│   ├── deploy.py        # Deployment orchestration
│   ├── config.py        # Deployer configuration
│   └── backends/
│       ├── base.py      # Abstract backend
│       ├── ssh.py       # SSH deployment
│       └── docker.py    # Docker deployment
└── testing/
    ├── runner.py        # Test execution
    ├── validators.py    # Installation validators
    └── backends/
        ├── base.py      # Abstract test backend
        ├── docker.py    # Docker containers
        ├── ssh.py       # SSH remote
        └── vagrant.py   # Vagrant VMs
```

## Single-File Bundling

The bundler combines multiple Python modules into a single script:

### Bundling Process

```python
def bundle(installer_type: str, output_path: Path) -> None:
    """Bundle installer into single file."""
    # 1. Collect all required modules
    modules = collect_modules(f"hop3_installer.{installer_type}")

    # 2. Generate combined source
    combined = generate_combined_source(modules)

    # 3. Add shebang and metadata
    script = f"#!/usr/bin/env python3\n# Generated installer\n{combined}"

    # 4. Write output
    output_path.write_text(script)
    output_path.chmod(0o755)
```

### Why Single-File?

- **No pip required** - Works on fresh systems
- **Curl-friendly** - `curl ... | python3 -`
- **Offline capable** - Copy and run
- **Auditable** - Single file to review

## CLI Installer (`hop3-install cli`)

Installs hop3-cli on local machines:

### Installation Steps

1. Check Python version (3.10+)
2. Determine installation method:
   - pipx (preferred)
   - pip with --user
   - pip in venv
3. Install hop3-cli package
4. Verify installation

### Configuration

```python
@dataclass
class CLIInstallerConfig:
    package: str = "hop3-cli"
    version: str | None = None
    method: str = "pipx"  # pipx, pip-user, venv
```

## Server Installer (`hop3-install server`)

Installs hop3-server on target machines (requires root):

### Installation Steps

1. **System check**
   - Root privileges
   - OS detection (Debian, Ubuntu, RHEL, etc.)
   - Python version

2. **User setup**
   - Create `hop3` user
   - Setup home directory structure
   - Configure SSH authorized_keys

3. **Dependencies**
   - Install system packages (nginx, uwsgi, git, etc.)
   - Install Python packages in venv

4. **Services**
   - Configure uWSGI emperor
   - Configure nginx
   - Setup systemd services

5. **Database**
   - PostgreSQL (optional)
   - MySQL (optional)
   - Initialize hop3 database

6. **Verification**
   - Service health checks
   - Connectivity tests

### Directory Structure Created

```
/home/hop3/
├── .venv/              # Python virtual environment
├── apps/               # Application storage
├── nginx/              # Nginx configurations
├── uwsgi-available/    # uWSGI configs
├── uwsgi-enabled/      # Active configs (symlinks)
├── certificates/       # SSL certificates
└── hop3.db            # SQLite database

/etc/
├── nginx/sites-enabled/hop3-admin.conf
└── systemd/system/
    ├── hop3-server.service
    └── uwsgi-emperor.service
```

## Developer Deployer (`hop3-deploy`)

Tool for deploying during development:

### Backends

#### SSH Backend

```python
class SSHBackend:
    def __init__(self, host: str, user: str = "root"):
        self.host = host
        self.user = user

    def execute(self, command: str) -> tuple[int, str, str]:
        """Execute command on remote host."""
        ...

    def upload_file(self, local: Path, remote: Path) -> None:
        """Upload file to remote host."""
        ...

    def upload_directory(self, local: Path, remote: Path) -> None:
        """Upload directory recursively."""
        ...
```

#### Docker Backend

```python
class DockerBackend:
    def __init__(self, image: str = "ubuntu:24.04"):
        self.image = image
        self.container_name = "hop3-dev"

    def start(self) -> None:
        """Start Docker container with systemd."""
        ...

    def execute(self, command: str) -> tuple[int, str, str]:
        """Execute command in container."""
        ...
```

### Deployment Flow

```
hop3-deploy --local

1. Check target connectivity (SSH or Docker)
2. If --clean: remove existing installation
3. If --local:
   a. Upload local code to target
   b. Run installer with --local-path
4. Else:
   a. Run installer (pulls from git)
5. If --admin-domain:
   a. Setup admin interface
   b. Create admin user
6. Configure local CLI (unless --no-cli-setup)
```

## Testing Framework

For validating installers across environments:

### Test Runner

```python
class InstallerTestRunner:
    def __init__(self, backend: TestBackend):
        self.backend = backend

    def run_tests(self) -> TestResults:
        """Run all installation tests."""
        results = TestResults()

        # Test installation
        results.add(self.test_installation())

        # Test services
        results.add(self.test_services())

        # Test deployment
        results.add(self.test_deployment())

        return results
```

### Validators

```python
class InstallationValidator:
    """Validate installation correctness."""

    def validate_user_exists(self) -> bool:
        """Check hop3 user exists."""
        ...

    def validate_services_running(self) -> bool:
        """Check required services are running."""
        ...

    def validate_directory_structure(self) -> bool:
        """Check directory structure is correct."""
        ...

    def validate_permissions(self) -> bool:
        """Check file permissions are correct."""
        ...
```

### Test Backends

| Backend | Use Case | Speed |
|---------|----------|-------|
| Docker | CI, quick iteration | Fast |
| SSH | Real server testing | Medium |
| Vagrant | Multi-OS testing | Slow |

## Environment Variables

### For hop3-deploy

| Variable | Description |
|----------|-------------|
| `HOP3_DEV_HOST` | Target server hostname |
| `HOP3_SSH_USER` | SSH user (default: root) |
| `HOP3_BRANCH` | Git branch to deploy |
| `HOP3_LOCAL` | Use local code |
| `HOP3_CLEAN` | Clean before install |
| `HOP3_DOCKER` | Use Docker backend |

### For hop3-install server

| Variable | Description |
|----------|-------------|
| `HOP3_DOMAIN` | Server domain name |
| `HOP3_ADMIN_EMAIL` | Admin email for Let's Encrypt |
| `HOP3_DB_TYPE` | Database type (sqlite, postgresql) |

## Security Considerations

- **Root required** - Server installer must run as root
- **SSH keys** - Deployer uses SSH key authentication
- **No passwords** - Never prompt for or store passwords
- **Minimal privileges** - hop3 user has minimal system access

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
