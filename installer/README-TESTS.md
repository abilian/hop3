# Testing the Hop3 Installers

This document explains how to test the Hop3 installers using the provided test scripts.

## Overview

There are three test scripts available, each suited for different scenarios:

| Script | Environment | Use Case |
|--------|-------------|----------|
| `test-installers-e2e.py` | Remote server via SSH | Production-like testing on real servers |
| `test-installers-docker.py` | Local Docker containers | Quick iteration, CI/CD pipelines |
| `test-installers.py` | Local Vagrant VMs | Full system testing with systemd |

## E2E Testing on Remote Servers

The `test-installers-e2e.py` script tests installers on a real remote server via SSH. This is the most realistic test environment.

### Prerequisites

1. **SSH access** to a target server (key-based authentication recommended)
2. **Python 3.10+** installed on the target server
3. **Root/sudo access** for server installer tests

### Quick Start

```bash
# Set target host (or use --host argument)
export HOP3_TEST_HOST=user@server.example.com

# Run all tests (CLI + Server, all methods)
./test-installers-e2e.py

# Or specify host directly
./test-installers-e2e.py --host root@server.example.com
```

### Command-Line Options

```
--host HOST         SSH target (user@hostname)
--type TYPE         Installer to test: cli, server, or both (default: both)
--method METHOD     Installation method: pypi, git, version, local, or all (default: all)
--branch BRANCH     Git branch for git method (default: devel)
--version VERSION   Version for version method (default: 0.3.0)
--keep              Keep installation after test (don't cleanup)
--verbose           Show detailed output
--dry-run           Show commands without executing
```

### Installation Methods

| Method | What It Tests |
|--------|---------------|
| `pypi` | Install from PyPI (use `--version` for specific version, default: latest) |
| `git` | Install from git repository (use `--branch` option) |
| `local` | Upload and install from local package directory |

### Examples

```bash
# Test only CLI installer
./test-installers-e2e.py --host user@server --type cli

# Test only server installer (requires root)
./test-installers-e2e.py --host root@server --type server

# Test only git installation method
./test-installers-e2e.py --host user@server --method git

# Test git installation from specific branch
./test-installers-e2e.py --host user@server --method git --branch main

# Test PyPI with specific version
./test-installers-e2e.py --host user@server --method pypi --version 0.3.0

# Test local path installation (uploads packages from your machine)
./test-installers-e2e.py --host user@server --method local

# Dry run (preview commands)
./test-installers-e2e.py --host user@server --dry-run

# Keep installation after test (for manual inspection)
./test-installers-e2e.py --host user@server --keep --verbose
```

### What Gets Tested

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
- Service status verification

### Cleanup

By default, the script cleans up installations between tests. Use `--keep` to preserve the installation for inspection:

```bash
# Run test and keep installation
./test-installers-e2e.py --host user@server --method git --keep

# Then SSH in to inspect
ssh user@server
ls -la ~/.hop3-cli/
~/.hop3-cli/venv/bin/hop3 --help
```

## Docker Testing

The `test-installers-docker.py` script uses Docker containers for fast, isolated testing without needing a remote server.

### Prerequisites

- Docker installed and running locally

### Usage

```bash
# Test CLI installer on Ubuntu (default)
./test-installers-docker.py

# Test on specific distro
./test-installers-docker.py --distro fedora

# Test on all distros
./test-installers-docker.py --all

# Cleanup containers
./test-installers-docker.py --cleanup
```

### Supported Distros

- `ubuntu` - Ubuntu 24.04 LTS
- `debian` - Debian 12
- `fedora` - Fedora 40

### Limitations

- Server installer tests are limited (no systemd in containers)
- Best for CLI installer testing and quick iteration

## Vagrant Testing

The `test-installers.py` script uses Vagrant VMs for full system testing including systemd services.

### Prerequisites

- Vagrant installed
- VirtualBox or another Vagrant provider

### Usage

```bash
# Test CLI installer on Ubuntu (default)
./test-installers.py

# Test server installer
./test-installers.py --vm ubuntu --type server

# Test on all VMs
./test-installers.py --all

# Keep VMs running
./test-installers.py --keep

# Cleanup all VMs
./test-installers.py --cleanup
```

### Available VMs

- `ubuntu` - Ubuntu 24.04 LTS
- `debian` - Debian 12
- `fedora` - Fedora 40

## Environment Variables

All test scripts support configuration via environment variables:

| Variable | Description |
|----------|-------------|
| `HOP3_TEST_HOST` | SSH target for E2E tests |
| `HOP3_BRANCH` | Git branch to test (default: devel) |
| `HOP3_VERSION` | Specific version to test |

## CI/CD Integration

For CI/CD pipelines, use the Docker test script:

```yaml
# Example GitHub Actions
test-installers:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Test CLI installer
      run: ./installer/test-installers-docker.py --type cli --all
```

For more thorough testing, use the E2E script with a test server:

```yaml
test-installers-e2e:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Test installers on server
      env:
        HOP3_TEST_HOST: ${{ secrets.TEST_SERVER_HOST }}
      run: ./installer/test-installers-e2e.py --method git
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
./test-installers-e2e.py --host root@server --type server

# Or ensure sudo works without password
./test-installers-e2e.py --host user@server --type server
```

### Package Not Found on PyPI

```
[FAIL] Installation failed (pypi method)
```

The package may not be published yet. Use git or local method instead:

```bash
./test-installers-e2e.py --host user@server --method git
```

## Test Output

Successful test output looks like:

```
============================================================
  Hop3 Installer E2E Tests
============================================================

  Host:    user@server.example.com
  Type:    both
  Method:  all
  Branch:  devel

[INFO] Checking SSH connection...
[PASS] SSH connection OK
[INFO] Checking Python version on remote host...
[PASS] Remote Python: Python 3.12.0

============================================================
  CLI Installer Tests
============================================================

--- Testing CLI: Git (devel branch) ---

[INFO] Cleaning up CLI installation...
[PASS] CLI cleanup complete
[INFO] Running installer (git devel)...
[INFO] Validating installation...
[PASS] Virtual environment exists
[PASS] CLI command installed
[PASS] Symlink created
[PASS] CLI command runs successfully

============================================================
  Test Summary
============================================================

  Total:   4
  Passed:  4
  Failed:  0

  [PASS] cli-pypi
  [PASS] cli-git
  [PASS] cli-version
  [PASS] cli-local

[PASS] All tests passed!
```
