# hop3-installer Tests

This directory contains tests for the hop3-installer package.

## Test Structure

```
tests/
├── a_unit/           # Unit tests (fast, no external dependencies)
├── b_integration/    # Integration tests
└── c_e2e/            # End-to-end tests (Docker, SSH, Vagrant)
```

## E2E Tests

The E2E tests verify that installers work correctly on real targets. They support multiple backends:

| Backend | Description | Default |
|---------|-------------|---------|
| `docker` | Local Docker containers | Yes (if Docker available) |
| `ssh` | Remote SSH hosts | Yes (if `HOP3_TEST_HOST` set) |
| `vagrant` | Local Vagrant VMs | No (requires `--vagrant`) |

### CLI Options

```
Hop3 E2E test options:
  --docker              Enable Docker backend
  --ssh                 Enable SSH backend (requires HOP3_TEST_HOST or --ssh-host)
  --ssh-host HOST       SSH host to test against (implies --ssh)
  --vagrant             Enable Vagrant backend (slow, starts VMs)
```

**Behavior:**
- If no options specified: defaults to Docker + SSH (if configured)
- If any option specified: only those backends are enabled

### Running E2E Tests

```bash
# Default: Docker + SSH (if HOP3_TEST_HOST is set)
pytest tests/c_e2e/ -v

# Docker only
pytest tests/c_e2e/ --docker

# SSH only (using environment variable)
HOP3_TEST_HOST=server.example.com pytest tests/c_e2e/ --ssh

# SSH only (using CLI option)
pytest tests/c_e2e/ --ssh-host server.example.com

# Vagrant only
pytest tests/c_e2e/ --vagrant

# Docker + Vagrant
pytest tests/c_e2e/ --docker --vagrant

# All three backends
HOP3_TEST_HOST=server.example.com pytest tests/c_e2e/ --docker --ssh --vagrant
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_TEST_HOST` | SSH target hostname (e.g., `server.example.com`) |
| `HOP3_SSH_USER` | SSH user (default: `root`) |

### Backend Requirements

#### Docker

- Docker must be installed and running
- The `hop3-test-systemd` image is built automatically for systemd tests

#### SSH

- SSH host must be specified via `HOP3_TEST_HOST` or `--ssh-host`
- SSH key authentication must be configured for the target user
- The user must have sudo access on the target

#### Vagrant

- Vagrant must be installed
- A Vagrantfile must be present in the testing directory
- Always requires explicit `--vagrant` flag

## Test Categories

### CLI Installer Tests (`test_cli_installer.py`)

Tests the `install-cli.py` bundled installer:
- Installation from git repository
- Installation from local path

### Server Installer Tests (`test_server_installer.py`)

Tests the `install-server.py` bundled installer:
- Installation from git repository
- Installation from local path
- Service configuration (PostgreSQL, nginx, hop3-server)

### Deployer Tests (`test_deployer.py`)

Tests the `hop3-deploy` command:
- Deployment to Docker containers
- Deployment to SSH targets
