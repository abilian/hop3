# Testing the Hop3 Installers

This document explains how to test the Hop3 installers (`install-cli.py` and `install-server.py`) using the end-to-end test suite in the `hop3-installer` package.

## Overview

Installer testing is a pytest E2E suite living in `packages/hop3-installer/tests/c_e2e/`. It bundles the single-file installers with `hop3-install bundle`, then runs them against a fresh target and validates the result. The suite supports three backends, selected by command-line options:

| Backend | Option | Use Case |
|---------|--------|----------|
| Docker | `--docker` (default) | Quick iteration, CI/CD pipelines |
| SSH | `--ssh` / `--ssh-host HOST` | Production-like testing on real servers |
| Vagrant | `--vagrant` | Full system testing with systemd in a VM |

If no backend option is given, the suite defaults to Docker (plus SSH when `HOP3_TEST_HOST` is configured). When any backend option is given, only the requested backends run.

## Quick Start

```bash
# Run installer E2E tests on Docker (default backend)
uv run pytest packages/hop3-installer/tests/c_e2e --docker

# Run against a remote server via SSH
uv run pytest packages/hop3-installer/tests/c_e2e --ssh-host root@server.example.com

# Run in a Vagrant VM (slow; full systemd)
uv run pytest packages/hop3-installer/tests/c_e2e --vagrant
```

A `make` shortcut builds the bundles and runs the installer tests:

```bash
make test-installer
```

## Test Layers

Installer tests follow the three-layer model from [ADR 043](/developers/adrs/043-unified-testing-architecture/). Each layer is decided by what a test needs (Docker, root, host mutation), and lives in its own directory under `packages/hop3-installer/tests/`:

| Layer | Location | Docker / VM? | What it covers |
|-------|----------|--------------|----------------|
| Unit | `a_unit/` | no | Bundler, common helpers, per-toolchain install logic |
| Integration | `b_integration/` | no | Bundler integration (validates the generated single-file scripts) |
| E2E | `c_e2e/` | yes | Full installer runs against Docker, SSH, or Vagrant targets |

The `a_unit` and `b_integration` layers run as part of `make test` and `make test-fast`; the `c_e2e` layer needs Docker (or an SSH/Vagrant target) and is the subject of this page.

## Backend Options

These options are added by the E2E suite's `conftest.py` and apply to the whole `c_e2e` directory:

| Option | Description |
|--------|-------------|
| `--docker` | Enable the Docker backend |
| `--ssh` | Enable the SSH backend (requires `HOP3_TEST_HOST` or `--ssh-host`) |
| `--ssh-host HOST` | SSH target in `user@hostname` form (implies `--ssh`) |
| `--vagrant` | Enable the Vagrant backend (slow; starts VMs) |

## Docker Backend

The Docker backend starts a throwaway container, uploads the bundled installer, runs it, and validates the result. It is the default and the right choice for fast, isolated iteration and CI.

### Prerequisites

- Docker installed and running locally

### Distros

The Docker backend can target several base images (`ubuntu` is the default):

| Distro | Image |
|--------|-------|
| `ubuntu` | `ubuntu:24.04` |
| `debian` | `debian:12` |
| `fedora` | `fedora:40` |

### Systemd tests

Service-level checks (PostgreSQL, nginx, the `hop3-server` systemd unit) require an init system. These tests use a `docker-systemd` backend variant and are marked `slow`. Plain Docker containers without systemd skip them.

## SSH Backend

The SSH backend runs the installer on a remote machine. This is the most production-like environment because it exercises a real init system and a real filesystem layout.

### Prerequisites

1. SSH access to a target server (key-based authentication recommended)
2. Python 3 installed on the target server
3. Root or passwordless-sudo access for server-installer tests

### Usage

```bash
# Provide the host on the command line
uv run pytest packages/hop3-installer/tests/c_e2e --ssh-host root@server.example.com

# Or set the environment variable and pass --ssh
export HOP3_TEST_HOST=root@server.example.com
uv run pytest packages/hop3-installer/tests/c_e2e --ssh
```

`HOP3_TEST_HOST` carries the hostname; `HOP3_SSH_USER` sets the user when the host has no `user@` prefix (it defaults to `root`).

## Vagrant Backend

The Vagrant backend provisions a VM, giving full systemd behavior without touching a remote server. It is slower than Docker and is never enabled by default — pass `--vagrant` explicitly.

### Prerequisites

- Vagrant installed
- A Vagrant provider (for example VirtualBox or libvirt)

### Usage

```bash
uv run pytest packages/hop3-installer/tests/c_e2e --vagrant
```

The Vagrantfiles used by the suite live under `packages/hop3-installer/tests/c_e2e/vagrant/`.

## Installation Methods

The bundled installers (`install-cli.py`, `install-server.py`) accept a few source-selection flags. The E2E tests exercise the `--git` and `--local-path` paths:

| Flag | What it tests |
|------|---------------|
| `--git --branch BRANCH` | Install from the git repository (default branch: `devel`) |
| `--local-path PATH` | Install from a local package directory uploaded to the target (used during development) |

Other installer flags used by the suite to keep runs fast and offline:

| Flag | Effect |
|------|--------|
| `--skip-acme` | Skip Let's Encrypt certificate issuance (avoids quota and external dependencies in tests) |
| `--skip-postgres` | Skip PostgreSQL setup to speed up the basic install test |
| `--no-modify-path` | Don't edit shell rc files (CLI installer) |
| `--verbose` | Show detailed installer output |

## What Gets Tested

**CLI installer (`test_cli_installer.py`):**

- Virtual environment creation at `~/.hop3-cli/venv`
- Package installation (`hop3-cli`)
- The `hop3` (or `hop`) command exists in the venv
- The command runs (`hop3 version`)

**Server installer (`test_server_installer.py`):**

- System user/group creation (`hop3`)
- Virtual environment at `/home/hop3/venv`
- Package installation (`hop3-server`) and a working `hop3-server` command
- Required directories (`/home/hop3/apps`)
- With systemd (the `slow` tests): PostgreSQL service and `hop3` role, nginx service and a valid config (`nginx -t`), and the `hop3-server` systemd unit being enabled

**Developer deploy tool (`test_deployer.py`):**

- `hop3-deploy-server --from local` against a Docker or SSH target, end to end

## Markers

Installer E2E tests carry the `e2e` marker (and `needs_docker` when stamped from the `c_e2e` layer; see the root `conftest.py`). The heavier systemd/service and deploy tests add the `slow` marker:

```bash
# Run only the faster E2E tests, skipping the slow service/deploy ones
uv run pytest packages/hop3-installer/tests/c_e2e --docker -m "not slow"
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_TEST_HOST` | SSH target for the SSH backend (`user@hostname` or bare hostname) |
| `HOP3_SSH_USER` | SSH user when `HOP3_TEST_HOST` has no `user@` prefix (default: `root`) |

## CI/CD Integration

For CI pipelines, use the Docker backend:

```yaml
# Example GitHub Actions
test-installers:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install dependencies
      run: uv sync
    - name: Test installers on Docker
      run: uv run pytest packages/hop3-installer/tests/c_e2e --docker
```

For more thorough coverage, run the same suite against a real SSH server:

```yaml
test-installers-e2e:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install dependencies
      run: uv sync
    - name: Test installers on a server
      env:
        HOP3_TEST_HOST: ${{ secrets.TEST_SERVER_HOST }}
      run: uv run pytest packages/hop3-installer/tests/c_e2e --ssh
```

## Troubleshooting

### Docker not available

If Docker isn't running, the E2E suite skips the Docker backend (and, with no other backend configured, reports "No backends available"). Verify Docker is up:

```bash
docker ps
```

### SSH connection failed

1. Verify SSH access: `ssh user@server echo ok`
2. Set up key-based auth: `ssh-copy-id user@server`
3. Check firewall rules and that `HOP3_TEST_HOST` is set or `--ssh-host` is passed

### Server tests need root

Server-installer tests run the installer with `sudo`. Use a `root` target or a user with passwordless sudo on the SSH backend.

### Vagrant VM won't start

1. Verify Vagrant and a provider are installed
2. Check the provider's settings
3. Inspect the Vagrantfiles under `packages/hop3-installer/tests/c_e2e/vagrant/`

## Architecture

The E2E suite is organized around a single `Backend` interface with one implementation per target:

```
packages/hop3-installer/tests/c_e2e/
├── conftest.py                 # CLI options (--docker/--ssh/--ssh-host/--vagrant), fixtures
├── test_cli_installer.py       # CLI installer tests
├── test_server_installer.py    # Server installer tests (incl. slow systemd/service tests)
├── test_deployer.py            # hop3-deploy-server tests
├── utils/
│   ├── installers.py           # bundle_installers(), get_packages_dir()
│   └── backends/
│       ├── base.py             # Backend interface
│       ├── discovery.py        # get_backend(), availability probes
│       ├── docker.py           # DockerBackend (distro images)
│       ├── docker_systemd.py   # DockerSystemdBackend (systemd-in-Docker)
│       ├── ssh.py              # SSHBackend
│       └── vagrant.py          # VagrantBackend
└── vagrant/                    # Vagrantfiles for the Vagrant backend
```

Each backend implements the same `setup`, `run`, `upload`, `upload_dir`, and cleanup methods, so adding a new target means adding one backend class and wiring it into `get_backend`.
