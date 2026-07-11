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
| `docker` | Local Docker containers | **Yes** (the default target) |
| `ssh` | Remote SSH hosts | No — explicit `--ssh-host HOST` only |
| `vagrant` | Local Vagrant VMs | No (requires `--vagrant`) |

> **A remote host is never taken from an env var.** `HOP3_TEST_HOST` and
> `HOP3_DEV_HOST` are **taboo** for pytest (ADR 043): the root conftest strips
> them, so an ambient value set for `hop3-deploy-server` / `hop3-test` can't
> silently redirect a test run at a real box (which once collided with a live
> `hop3-test` run). Remote testing is opt-in **only** via `--ssh-host`.

### CLI Options

```
Hop3 test options:
  --ssh-host HOST       Run against a remote SSH host (explicit opt-in)
  --docker              Run against Docker (the default with no flags)
  --vagrant             Enable Vagrant backend (slow, starts VMs)
```

**Behavior:**
- No flags → Docker only.
- Any explicit flag → exactly the requested targets. `--ssh-host HOST` adds the
  remote target; combine with `--docker` to run both.

### Running E2E Tests

```bash
# Default: Docker only
pytest tests/c_e2e/ -v

# Docker only (explicit)
pytest tests/c_e2e/ --docker

# Remote SSH host (the ONLY way to run against a real box)
pytest tests/c_e2e/ --ssh-host server.example.com

# Docker + remote
pytest tests/c_e2e/ --docker --ssh-host server.example.com

# Vagrant only
pytest tests/c_e2e/ --vagrant
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_SSH_USER` | SSH user for `--ssh-host` when it has no `user@` (default: `root`) |

`HOP3_TEST_HOST` / `HOP3_DEV_HOST` are **not** read — pass `--ssh-host` instead.

### Backend Requirements

#### Docker

- Docker must be installed and running
- The `hop3-test-systemd` image is built automatically for systemd tests

#### SSH

- SSH host must be specified via `--ssh-host HOST` (env vars are ignored)
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
