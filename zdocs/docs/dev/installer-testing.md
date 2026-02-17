# Testing the Hop3 Installers

This document explains how to test the Hop3 installers using the unified test script.

## Overview

The `hop3-test-installers` command provides a unified interface for testing Hop3 installers across different environments:

| Backend | Command | Use Case |
|---------|---------|----------|
| SSH | `hop3-test-installers ssh` | Production-like testing on real servers |
| Docker | `hop3-test-installers docker` | Quick iteration, CI/CD pipelines |
| Vagrant | `hop3-test-installers vagrant` | Full system testing with systemd |

## Quick Start

```bash
# Test on remote server via SSH
hop3-test-installers ssh --host root@server.example.com

# Test in Docker container
hop3-test-installers docker --distro ubuntu

# Test in Vagrant VM
hop3-test-installers vagrant --vm ubuntu
```

## Common Options

All backends support these options:

| Option | Description |
|--------|-------------|
| `--type TYPE` | Installer to test: `cli`, `server`, or `both` (default: `both`) |
| `--method METHOD` | Installation method: `pypi`, `git`, `local`, or `all` (default: `git`) |
| `--branch BRANCH` | Git branch for git method (default: `devel`) |
| `--version VERSION` | Version for pypi method |
| `--keep` | Keep environment after test |
| `--verbose` | Show detailed output |

## SSH Backend

Test on remote servers via SSH. This is the most realistic test environment.

### Prerequisites

1. **SSH access** to a target server (key-based authentication recommended)
2. **Python 3.10+** installed on the target server
3. **Root/sudo access** for server installer tests

### Usage

```bash
# Set target host (or use --host argument)
export HOP3_TEST_HOST=user@server.example.com

# Run all tests
hop3-test-installers ssh --host root@server.example.com

# Test only CLI installer
hop3-test-installers ssh --host user@server --type cli

# Test git installation from specific branch
hop3-test-installers ssh --host user@server --method git --branch main

# Dry run (preview commands)
hop3-test-installers ssh --host user@server --dry-run

# Keep installation after test
hop3-test-installers ssh --host user@server --keep --verbose
```

### SSH-Specific Options

| Option | Description |
|--------|-------------|
| `--host HOST` | SSH target (user@hostname) |
| `--dry-run` | Show commands without executing |

## Docker Backend

Test in Docker containers for fast, isolated testing without needing a remote server.

### Prerequisites

- Docker installed and running locally

### Usage

```bash
# Test on Ubuntu (default)
hop3-test-installers docker

# Test on specific distro
hop3-test-installers docker --distro fedora

# Test on all distros
hop3-test-installers docker --all

# Cleanup containers
hop3-test-installers docker --cleanup
```

### Supported Distros

- `ubuntu` - Ubuntu 24.04 LTS
- `debian` - Debian 12
- `fedora` - Fedora 40

### Docker-Specific Options

| Option | Description |
|--------|-------------|
| `--distro DISTRO` | Distribution to test on (default: `ubuntu`) |
| `--all` | Test on all available distros |
| `--cleanup` | Remove all test containers and exit |

### Limitations

- Server installer tests are limited (no systemd in containers)
- Best for CLI installer testing and quick iteration

## Vagrant Backend

Test in Vagrant VMs for full system testing including systemd services.

### Prerequisites

- Vagrant installed
- VirtualBox or another Vagrant provider

### Usage

```bash
# Test on Ubuntu (default)
hop3-test-installers vagrant --vm ubuntu

# Test server installer
hop3-test-installers vagrant --vm ubuntu --type server

# Test on all VMs
hop3-test-installers vagrant --all

# Keep VMs running
hop3-test-installers vagrant --keep

# Cleanup all VMs
hop3-test-installers vagrant --cleanup
```

### Available VMs

- `ubuntu` - Ubuntu 24.04 LTS
- `debian` - Debian 12
- `fedora` - Fedora 40

### Vagrant-Specific Options

| Option | Description |
|--------|-------------|
| `--vm VM` | VM to test on (default: `ubuntu`) |
| `--all` | Test on all available VMs |
| `--cleanup` | Destroy all VMs and exit |

## Installation Methods

| Method | What It Tests |
|--------|---------------|
| `pypi` | Install from PyPI (use `--version` for specific version) |
| `git` | Install from git repository (use `--branch` option) |
| `local` | Install from local package directory |

## What Gets Tested

**CLI Installer Tests:**
- Virtual environment creation at `~/.hop3-cli/venv`
- Package installation (`hop3-cli`)
- Command symlinks (`hop3`, `hop`) in `~/.local/bin`
- Command execution (`hop3 --help`)

**Server Installer Tests:**
- System user/group creation (`hop3`)
- Virtual environment at `/home/hop3/venv`
- Package installation (`hop3-server`)
- Systemd service configuration (`hop3-server.service`)
- PostgreSQL database and role setup
- Nginx reverse proxy configuration
- SSL certificate setup
- Service status verification

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_TEST_HOST` | SSH target for SSH backend tests |
| `HOP3_BRANCH` | Git branch to test (default: devel) |
| `HOP3_VERSION` | Specific version to test |

## CI/CD Integration

For CI/CD pipelines, use the Docker backend:

```yaml
# Example GitHub Actions
test-installers:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Test CLI installer
      run: ./installer/test-installers.py docker --type cli --all
```

For more thorough testing, use the SSH backend with a test server:

```yaml
test-installers-e2e:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Test installers on server
      env:
        HOP3_TEST_HOST: ${{ secrets.TEST_SERVER_HOST }}
      run: ./installer/test-installers.py ssh --method git
```

## Troubleshooting

### SSH Connection Failed

```
[FAIL] Cannot connect to user@server
```

**Solutions:**
1. Verify SSH access: `ssh user@server echo ok`
2. Set up key-based auth: `ssh-copy-id user@server`
3. Check firewall rules

### Python Version Too Old

```
[FAIL] Python 3 not found on remote host
```

**Solutions:**
1. Install Python 3.10+: `sudo apt install python3.11`
2. Verify: `python3 --version`

### Server Tests Need Root

Server installer tests require root or sudo access:

```bash
# Use root user
hop3-test-installers ssh --host root@server --type server

# Or ensure sudo works without password
hop3-test-installers ssh --host user@server --type server
```

### Package Not Found on PyPI

```
[FAIL] Installation failed (pypi method)
```

The package may not be published yet. Use git or local method instead:

```bash
hop3-test-installers ssh --host user@server --method git
```

### Docker Container Won't Start

```
[FAIL] Failed to start container
```

**Solutions:**
1. Verify Docker is running: `docker ps`
2. Check for port conflicts
3. Run cleanup: `hop3-test-installers docker --cleanup`

### Vagrant VM Won't Start

```
[FAIL] Failed to start VM
```

**Solutions:**
1. Verify Vagrant and VirtualBox are installed
2. Check VirtualBox settings
3. Run cleanup: `hop3-test-installers vagrant --cleanup`

## Test Output

Successful test output looks like:

```
============================================================
  Hop3 Installer E2E Tests (SSH)
============================================================

  Host:    user@server.example.com
  Type:    both
  Method:  git
  Branch:  devel

============================================================
  CLI Installer Tests
============================================================

--- Testing CLI: Git (devel branch) ---

[INFO] Cleaning up CLI installation...
[PASS] CLI cleanup complete
[INFO] Running installer (git)...
[PASS] CLI installer completed
[INFO] Validating CLI installation...
[PASS] Virtual environment exists
[PASS] CLI command installed
[PASS] Symlink created
[PASS] CLI command runs successfully

============================================================
  Test Summary
============================================================

  Total:   2
  Passed:  2
  Failed:  0

  [PASS] cli-git
  [PASS] server-git

[PASS] All tests passed!
```

## Architecture

The test framework uses a modular architecture:

```
installer/
├── test-installers.py       # Unified CLI
└── testing/
    ├── __init__.py
    ├── common.py            # Shared utilities (logging, CommandResult)
    ├── runner.py            # TestRunner, TestConfig, TestResult
    ├── validators.py        # Validation functions
    └── backends/
        ├── __init__.py
        ├── base.py          # Abstract Backend class
        ├── ssh.py           # SSHBackend
        ├── docker.py        # DockerBackend
        └── vagrant.py       # VagrantBackend
```

Each backend implements the same interface, making it easy to add new test environments.
