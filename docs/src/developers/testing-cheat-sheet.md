# Hop3 Testing Cheat Sheet

> **Updated by ADR 043.** The pytest pyramid is now **three** layers — `a_unit` (fast, no Docker) · `b_integration` (in-process, real in-memory DB, no Docker) · `c_e2e` (Docker/real-deploy, renamed from `d_e2e`). The old `c_system` layer is **dissolved**. A test's layer is decided by whether it needs Docker/root/host-mutation, not by complexity; coverage is measured on `a_unit` + `b_integration` only (e2e runs out-of-process). Markers (`fast`/`integration`/`e2e`/`needs_docker`) are stamped from the directory layer (root `conftest.py`), so `pytest -m fast` / `-m "not needs_docker"` work everywhere.

Quick reference for developers running tests.

## Quick Commands

| What | Command |
|------|---------|
| **Fast unit tests (< 1 min)** | `make test-fast` |
| **Check tier (unit + integration, no Docker)** | `make test` |
| **Docker e2e (real deploys, backups, git-push)** | `make test-e2e` |
| **App tests (Docker)** | `make test-apps` |
| **Lint & type check** | `make lint` |
| **System tests (Docker)** | `hop3-test run --docker` |
| **Upgrade chain (Docker)** | `hop3-test upgrade-chain --docker` |
| **Cloud test (single distro)** | `hop3-test run --provider hetzner --image ubuntu-24.04` |
| **Cloud test (multi-distro)** | `hop3-test run --provider hetzner --images ubuntu-24.04,debian-13` |

## hop3-test CLI

The unified test runner for Hop3 deployment testing.

### System Testing (Testing Hop3 Itself)

Deploys Hop3 using `hop3-deploy-server`, then runs tests against it.

```bash
# Deploy local code to Docker and test
hop3-test run --docker

# Deploy from git branch
hop3-test run --docker --from git --branch main

# Deploy from PyPI
hop3-test run --docker --from pypi

# Clean install (remove existing)
hop3-test run --docker --clean

# Reuse existing deployment (skip deploy)
hop3-test run --docker --reuse
# Or equivalently:
hop3-test run --docker --from none

# Remote server via SSH
hop3-test run --host server.example.com

# SSH using HOP3_TEST_HOST env var
export HOP3_TEST_HOST=server.example.com
hop3-test run

# Test profile: dev (fast P0 only) or ci (fast + medium P0)
hop3-test run --docker --mode ci

# Install extra server features/addons before testing
hop3-test run --docker --with nix
hop3-test run --docker --clean --with all

# Scan a directory or run a specific app (positional)
hop3-test run --docker apps/test-apps-procfile
hop3-test run --docker apps/test-apps-procfile/010-flask-pip-wsgi

# Run one app, reusing an existing deployment
hop3-test run --docker --reuse apps/real-apps-native/edrix

# Keep target running after tests
hop3-test run --docker --keep

# Generate HTML report
hop3-test run --docker --report html
```

The default `--mode` is `smoke` (the smallest sanity run). Available profiles: `smoke`, `ci`, `curated`, `tag-coverage`, `combo-coverage`, `nightly`, `full` (`dev` is an alias for `smoke`, `release` for `full`).

#### Deploy-from Options

| Option | Description |
|--------|-------------|
| `--from local` | Upload and install local code (default) |
| `--from git` | Clone and install from git branch |
| `--from pypi` | Install from PyPI |
| `--from none` | Skip deployment, use existing |
| `--reuse` | Alias for `--from none` |

### Upgrade Chain (Cross-Version Upgrades)

Install a baseline release on a **fresh** box, then upgrade in-place through a chain of versions — each installed by **its own** installer (checked out into a git worktree, run via `uv run`). Every hop after the first is an in-place update, asserted to come back healthy with a readable schema.

```bash
# Fresh Docker container: 0.6.2 -> current tree
hop3-test upgrade-chain --docker

# Custom chain (release tags + `local`)
hop3-test upgrade-chain --docker --chain 0.6.2,local

# Cheapest smoke: whole mechanism, no old-version/worktree variable
hop3-test upgrade-chain --docker --chain local,local

# Fresh Hetzner VPS (needs HETZNER_API_TOKEN + HETZNER_SERVER_ID)
hop3-test upgrade-chain --provider hetzner --image ubuntu-24.04
```

`--host <server>` is accepted but warns (existing server, not a clean slate). `0.6.0` is excluded from the default chain — its `hop3-rootd` can't start.

### App Testing (Testing Apps, Not Hop3)

App testing runs through the same `run` command. Pass app directories or
specific app paths as positional arguments; combine with `--reuse` to skip the
Hop3 deployment and test against an already-running container.

```bash
# Test the default app catalog on Docker
hop3-test run --docker --clean --with all

# Scan a directory
hop3-test run --docker apps/test-apps-procfile

# Test a specific app
hop3-test run --docker apps/test-apps-procfile/010-flask-pip-wsgi

# Reuse an existing deployment for fast iteration on one app
hop3-test run --docker --reuse apps/real-apps-native/edrix

# Keep apps deployed after testing
hop3-test run --docker --keep apps/test-apps-procfile/010-flask-pip-wsgi

# Against a remote server
hop3-test run --host server.example.com apps/test-apps-procfile
```

### Listing and Inspecting Tests

```bash
# List all tests
hop3-test list

# Scan only specific directories
hop3-test list apps/test-apps-procfile demos

# Filter by tier or priority
hop3-test list --tier fast
hop3-test list --priority P0

# Show details of one test
hop3-test list --show 010-flask-pip-wsgi

# JSON output
hop3-test list --format json
```

### Cloud Testing

Run E2E tests on real cloud infrastructure (Hetzner by default). Requires
`HETZNER_API_TOKEN`.

```bash
# List available images
hop3-test run --list-images

# Single distribution test
hop3-test run --provider hetzner --image ubuntu-24.04

# Multi-distribution test
hop3-test run --provider hetzner --images ubuntu-24.04,debian-13,fedora-42

# All distributions
hop3-test run --provider hetzner --images all

# Test specific app directories (positional, like `run`)
hop3-test run --provider hetzner apps/test-apps-procfile demos

# Install source (default: local; --from pypi to install from PyPI)
hop3-test run --provider hetzner --from local --images all

# Test against an existing server (no rebuild, no deploy)
hop3-test run --host server.example.com --reuse
```

## Pytest Tests

### Run by Layer

There are three layers under each package's `tests/`. A test's layer is decided by what it *needs* (Docker / root / host-mutation), not by complexity; duplication across layers is allowed.

```bash
# Unit tests — no Docker, counts toward coverage (tier: fast)
uv run pytest packages/hop3-server/tests/a_unit

# Integration tests — in-process, real in-memory DB, no Docker, counts toward
# coverage (tier: check)
uv run pytest packages/hop3-server/tests/b_integration

# E2E tests — real Docker deploy, NO coverage (check (Docker) + nightly)
uv run pytest packages/hop3-server/tests/c_e2e

# CLI tests
uv run pytest packages/hop3-cli/tests
```

Markers are stamped from the directory by the root `conftest.py`, so you can select layers anywhere:

```bash
uv run pytest -m fast                  # a_unit + flat unit suites
uv run pytest -m "not needs_docker"    # everything except the Docker e2e layer
uv run pytest packages/hop3-server/tests/c_e2e   # the Docker e2e layer
```

### Run Specific Tests

```bash
# Single file
uv run pytest packages/hop3-server/tests/a_unit/test_app_config.py

# Single test
uv run pytest packages/hop3-server/tests/a_unit/test_app_config.py::test_function_name

# By keyword
uv run pytest -k "backup" packages/hop3-server/tests

# By marker (fast / integration / e2e / needs_docker)
uv run pytest -m "not needs_docker" packages/hop3-server/tests
```

### Useful Flags

```bash
# Verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Show print statements
uv run pytest -s

# Parallel execution (faster)
uv run pytest -n 4

# Show slowest tests
uv run pytest --durations=10

# Coverage report
uv run pytest --cov=hop3 --cov-report=term-missing
```

## Common Workflows

### Before Committing

```bash
make lint       # Check formatting and types
make test-fast  # Fast unit tests (the inner loop, < 1 min)
make test       # Check tier: unit + integration, all packages, no Docker
```

### Quick Validation (Developer)

```bash
# Fast tests against Docker
hop3-test run --docker --mode dev
```

### Full Validation

```bash
# Check tier (in-process, no Docker) plus the Docker e2e layer
make test
make test-e2e

# Deploy the real app catalog on Docker
make test-apps

# Or run the system suite manually
hop3-test run --docker --mode ci --report html
```

### Debug a Failing Test

```bash
# Run with verbose output
uv run pytest -v -s path/to/test.py::test_name

# Keep the target running for inspection
hop3-test run --docker --keep apps/test-apps-procfile/010-flask-pip-wsgi

# Run system tests and keep target
hop3-test run --docker --keep

# Reuse container for fast iteration
hop3-test run --docker --reuse --keep

# Generate HTML report for analysis
hop3-test run --docker --report html
```

### Test Coverage

```bash
make test-cov

# HTML report
uv run pytest --cov=hop3 --cov-report=html
open htmlcov/index.html
```

## Test Directory Structure

```
packages/hop3-server/tests/
├── a_unit/          # Unit; no Docker; counts toward coverage (tier: fast)
├── b_integration/   # In-process, real in-memory DB; no Docker; coverage (tier: check)
└── c_e2e/           # End-to-end; real Docker deploy; no coverage (check (Docker) + nightly)

packages/hop3-testing/    # Test framework
├── src/hop3_testing/
│   ├── catalog/          # Test catalog (reads [test] section from hop3.toml)
│   ├── cli/              # CLI commands
│   ├── runners/          # Test runners
│   ├── results/          # Result storage and reporting
│   ├── selector/         # Test selection logic
│   └── targets/          # Deployment targets

apps/                            # Test and demo applications
├── test-apps-procfile/          # Procfile-based test apps (standalone test.toml)
│   ├── 000-static/
│   ├── 010-flask-pip-wsgi/
│   ├── 020-nodejs-express/
│   └── ...
├── test-apps-nix/               # Nix-based test apps
├── real-apps-native/            # Real apps, native toolchains
├── real-apps-nix/               # Real apps, hand-crafted Nix
├── real-apps-nix-gen/           # Real apps, Nix from template
demos/                           # Educational demos
```

## Test Configuration (`[test]` in hop3.toml)

Tests are configured via a `[test]` section in the app's `hop3.toml`. Most fields are derived from other sections (metadata, build, addons, healthcheck); the `[test]` block only holds the test-framework-specific bits:

```toml
[test]
priority = "P0"                    # P0 | P1 | P2
tier = "fast"                      # report label only — no longer drives timeouts
targets = ["docker", "remote"]
covers = ["python", "flask", "pip", "uwsgi"]

[[test.validations]]
path = "/"
status = 200
```

Legacy standalone `test.toml` files are still used by procfile-only test apps (`apps/test-apps-procfile/*/`), negative-test cases, demos, and tutorials — anywhere there's no sibling `hop3.toml`. See [config.md](../reference/config.md#test-test-harness-metadata) for the full reference.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HOP3_DEV_HOST` | SSH target for deployment |
| `HOP3_TEST_HOST` | Remote target host when `--host` is omitted |
| `HOP3_TEST_SSH_KEY` | SSH key for remote tests |
| `HOP3_UNSAFE=true` | Disable auth in Docker tests |
| `HETZNER_API_TOKEN` | Hetzner Cloud API token (for `hop3-test run --provider hetzner`) |

## Troubleshooting

### Docker Tests Fail

```bash
# Check if the container is running
docker ps -a | grep hop3

# View container logs (system tests use the hop3-system-test container)
docker logs hop3-system-test

# Run again with a clean install and verbose output
hop3-test -v run --docker --clean
```

### App Tests Fail

```bash
# Re-run one app with verbose output
hop3-test -v run --docker apps/test-apps-procfile/010-flask-pip-wsgi

# Keep the target up and generate an HTML report
hop3-test run --docker --keep --report html apps/test-apps-procfile/010-flask-pip-wsgi
```

### System Tests Timeout

```bash
# Reuse existing container to debug
hop3-test run --docker --reuse --keep

# Inspect the diagnostic bundle collected on a failed Docker e2e/app run
hop3-test why <run-id>
```

### Remote Tests Fail

```bash
# Verify SSH connection
ssh hop3@$HOP3_TEST_HOST "hop3 --version"

# Check server status
ssh root@$HOP3_TEST_HOST "systemctl status hop3-server"
```

## Target Types

| Target | Use Case | Speed |
|--------|----------|-------|
| `--docker` | System tests with a fresh deploy | Slow (~5 min startup) |
| `--docker --reuse` | App tests against an existing container | Fast (skips deploy) |
| `--host X` | Tests against a real server | Variable |

### When to Use Each

- **`hop3-test run --docker`**: Testing Hop3 changes (deploys Hop3 first)
- **`hop3-test run --docker --reuse`**: Fast iteration on an existing container
- **`hop3-test run --host X`**: Testing against remote servers
- **`hop3-test run --docker <app-path>`**: Testing one app's configuration
