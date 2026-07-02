# Testing Hop3

> **Note**: For comprehensive testing documentation, see [Testing Strategy](testing-strategy.md).

## Overview

Hop3 uses a multi-layer testing approach across three complementary runners (pytest for platform code, `hop3-test` for applications, `validoc` for tutorials):

### Test Layers (pytest-based)

Three layers live under each package's `tests/`. The layer is decided by what a test *needs* (Docker, root, host-mutation), not by complexity — duplication across layers is allowed (see ADR 043).

1. **Unit Tests** (`tests/a_unit/`) - Individual components in isolation; no Docker; count toward coverage; tier `fast`
2. **Integration Tests** (`tests/b_integration/`) - Multiple components within a subsystem, in-process against a real in-memory DB; no Docker; count toward coverage; tier `check`
3. **E2E Tests** (`tests/c_e2e/`) - Full deployments with a real Docker target; no coverage; run in the check tier (Docker) and nightly

### Application Testing (hop3-test)

Beyond pytest, two more runners cover the other domains (only pytest produces coverage):

- **`hop3-test`** — applications: deploys real apps and demos to a `DeploymentTarget` (Docker, SSH, Hetzner) and verifies them.
- **`validoc`** — narratives: runs the tutorials as doc-as-tests.

## Quick Start

### Run Unit + Integration Tests

```bash
# Fast lane — unit only, all packages, no Docker (< 1 min)
make test-fast

# Check tier — unit + integration, all packages, no Docker
make test

# Or using pytest directly
pytest packages/hop3-server/tests/a_unit/ packages/hop3-server/tests/b_integration/
```

### Run E2E Tests (Docker-based)

```bash
# The Docker e2e layer (c_e2e): real deploys, backups, git-push
make test-e2e

# Or using pytest directly
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_e2e/
```

### Run Application Tests

```bash
# Deploy the real-app catalog on Docker via hop3-test
make test-apps

# Test a single app or path
make test-app APP=apps/real-apps-native/edrix
```

## Test Commands Reference

### Makefile Targets

| Command | Description | Duration |
|---------|-------------|----------|
| `make test-fast` | Unit only, all packages, no Docker | < 1min |
| `make test` | Check tier: unit + integration, all packages, no Docker | ~30s |
| `make test-e2e` | The Docker e2e layer (`c_e2e`): real deploys, backups, git-push | ~10min |
| `make test-cov` | Coverage on the in-process layers (unit + integration) | ~1min |
| `make test-apps` | Deploy the real-app catalog on Docker (`hop3-test`) | ~5min |
| `uv run hop3-test list` | List available app/demo/tutorial tests | instant |
| `uv run hop3-test run --docker --mode nightly` | Full app/demo/tutorial matrix on Docker + HTML report | long |
| `make test-installer` | Test the installers | ~5min |
| `make lint` | Linting and type checking | ~30s |

### Hetzner Cloud Testing

| Command | Description |
|---------|-------------|
| `hop3-test matrix --image ubuntu-24.04` | Run e2e/app tests on a cloud server (Hetzner) |
| `hop3-test matrix --images ubuntu-24.04,debian-13` | Test across multiple Linux distributions |

### hop3-test CLI

```bash
# System testing (deploys Hop3, then deploys + verifies apps)
hop3-test run --docker                       # Deploy + test defaults on Docker
hop3-test run --docker --clean --with all    # Clean install with all addons
hop3-test run --docker apps/real-apps-native # Scan a directory
hop3-test run --docker apps/real-apps-native/edrix  # One app or path
hop3-test run --host $HOP3_DEV_HOST    # Remote via SSH
hop3-test run --reuse --host $HOP3_DEV_HOST   # Skip deploy, test existing
hop3-test run --docker --from git --branch devel  # Deploy from git
hop3-test run --docker --mode nightly        # Wider matrix (smoke | ci | nightly | full | ...)

# List / inspect
hop3-test list                      # List available app/demo/tutorial tests
hop3-test why <run-id>              # Show the diagnostic bundle for a failed run
```

## Test Organization

A test's layer is decided by what it *needs*, not by complexity: if it needs Docker, root, or host-mutation it belongs in `c_e2e`; otherwise it stays in-process in `a_unit` or `b_integration`. The root `conftest.py` stamps a marker from the directory, so `-m fast`, `-m integration`, `-m e2e`, and `-m "not needs_docker"` select the right lane regardless of package.

```bash
pytest -m fast                 # a_unit (+ flat unit suites)
pytest -m "not needs_docker"   # everything except the Docker e2e layer
```

### Layer 1: Unit Tests

**Location**: `packages/hop3-server/tests/a_unit/`
**Speed**: < 1 second
**Requirements**: None — counts toward coverage
**Marker**: `fast`

```bash
pytest packages/hop3-server/tests/a_unit/ -v
```

### Layer 2: Integration Tests

**Location**: `packages/hop3-server/tests/b_integration/`
**Speed**: ~10 seconds
**Requirements**: None — in-process, real in-memory DB; counts toward coverage
**Marker**: `integration`

```bash
pytest packages/hop3-server/tests/b_integration/ -v
```

### Layer 3: E2E Tests

**Location**: `packages/hop3-server/tests/c_e2e/`
**Speed**: 10-20 minutes
**Requirements**: Docker (real deploy) — no coverage
**Marker**: `e2e` (+ `needs_docker`)

```bash
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_e2e/ -v
```

## Application Testing with hop3-test

### Test Apps Directory

Test applications live under several `apps/` directories (plus `demos/`):

```
apps/test-apps-procfile/   # Procfile-only fixtures (standalone test.toml)
apps/test-apps-nix/        # Nix fixtures
apps/real-apps-native/     # Real apps, native build
apps/real-apps-docker/     # Real apps, Docker build
apps/real-apps-nix/        # Real apps, Nix hand-crafted
apps/real-apps-nix-gen/    # Real apps, Nix from template
demos/                     # Demos (discovered via demo-script.py)
```

### Test Configuration (`[test]` in hop3.toml)

Test configuration lives in the app's `hop3.toml` file under a `[test]` section. Most apps keep all their test config there, with no separate `test.toml` file.

Most fields are *derived* from the rest of `hop3.toml`: the test name from `[metadata].id`, category from `[build].builder`, required services from `[[addons]]`, base healthcheck path from `[healthcheck]`. The `[test]` section only declares what's test-framework-specific.

```toml
[metadata]
id = "flask-hello"

[build]
builder = "nix"

[healthcheck]
path = "/"

# Test-harness metadata
[test]
priority = "P0"                        # P0 (critical), P1, P2
tier = "fast"                          # fast | medium | slow | very-slow (report label only)
targets = ["docker", "remote"]
covers = ["python", "flask", "pip", "uwsgi"]

[[test.validations]]
path = "/"
status = 200
contains = "Hello"
```

Note: `tier` is *only* a report-grouping label — all builds share a single 30-minute budget (see [config.md](../reference/config.md#test-test-harness-metadata)). The legacy `[build].tier` field no longer exists.

**Standalone `test.toml` files still exist for Procfile-only test apps** (`apps/test-apps-procfile/*/`), which don't pair with a `hop3.toml`. Two other kinds of test are configured differently:

- Negative-test cases live under `apps/bad/` (in `apps/bad/real-apps-native-bad/`, `apps/bad/real-apps-docker-bad/`, `apps/bad/real-apps-nix-bad/`). They carry a normal `hop3.toml`, and the runner treats any deploy under `apps/bad/` as expected-to-fail (a failed deploy counts as PASS). You can also opt any app in with `expects-failure = true` in `[test]`.
- Demos (`demos/*/`) and tutorials (`docs/tutorials/**/`) are discovered structurally — a demo by its `demo-script.py`, a tutorial by its `bash exec`/`output`/`file` markers — rather than from a `test.toml`.

### Test Modes

When no apps are named, `--mode` filters the catalog by tier/priority (default: `smoke`):

| Mode | Selection | Use Case |
|------|-----------|----------|
| `smoke` | fast + P0 deployment apps | Quick verification |
| `ci` | fast + medium, P0 | Pre-merge gate |
| `curated` | hand-picked diverse slice | Representative coverage |
| `tag-coverage` | smallest subset hitting every tag | Dimension coverage |
| `combo-coverage` | smallest subset hitting every tag combo | Combination coverage |
| `nightly` | all tiers except very-slow, P0 + P1 | Nightly builds |
| `full` | everything (all tiers + priorities) | Release validation |

The old names `dev` (→ `smoke`) and `release` (→ `full`) still work as aliases.

### Test Targets

The `run` command picks a target via a flag (the `DeploymentTarget` ABC covers Docker, SSH, and cloud):

| Target | Description | Flag |
|--------|-------------|------|
| Docker | Fresh Hop3 deployed into a local container | `--docker` |
| SSH    | Existing remote server | `--host X` |
| Cloud  | Provisioned cloud server(s) (Hetzner) | `hop3-test matrix` |

## Test Output

### Recap Summary

After tests complete, a recap shows what was tested:

```
============================================================
All 8 tests passed!
Total time: 148.55s
============================================================

Recap:
  ✓ deployment: 8/8 passed
  Tiers: fast=5, medium=3
  Covers: flask, go, golang, gunicorn, minimal, nginx, nodejs, pip, ...
  Avg time per test: 18.6s
```

Use `-q/--quiet` to suppress the recap.

### Diagnostic Logs

On failure of a Docker e2e or app test, a diagnostic bundle is collected for the run. Replay it with the run id printed in the failure headline:

```bash
hop3-test why <run-id>            # Show the full bundle
hop3-test why <run-id> --list     # List available sections
hop3-test why <run-id> --section nginx   # Replay one section
```

Per-app logs are also written under `test-logs/` (override with `--logs-dir`):

```
test-logs/
└── 20260110_155610/
    └── system-hop3-test-docker/
        ├── diagnostics.json
        ├── nginx-error.log
        ├── uwsgi.log
        └── hop3-server.log
```

## Continuous Integration

CI runs on **SourceHut** (build manifests live in `.builds/`). A typical pipeline runs:

```bash
make lint             # Linting and type checking
make test             # Check tier: unit + integration, no Docker
make test-e2e         # The Docker e2e layer (c_e2e)
```

The wider app/demo/tutorial matrix runs nightly:

```bash
uv run hop3-test run --docker --mode nightly --report html
```

See: <https://builds.sr.ht/~sfermigier/hop3/>

## Coverage

Coverage is measured on the in-process layers only (`a_unit` + `b_integration`) — the Docker e2e layer runs out-of-process and contributes nothing to coverage.

```bash
# Coverage on the in-process layers
make test-cov

# Or directly (HTML report)
pytest --cov=hop3 --cov-report=html \
  packages/hop3-server/tests/a_unit packages/hop3-server/tests/b_integration

# Open report
open htmlcov/index.html
```

## Cloud Testing

For E2E testing on real cloud infrastructure, use `hop3-test matrix`. Requires the `HETZNER_API_TOKEN` environment variable (Hetzner provider).

```bash
# List available images
hop3-test matrix --list-images

# Test on a single distribution
hop3-test matrix --image ubuntu-24.04

# Test across multiple distributions
hop3-test matrix --images ubuntu-24.04,debian-13

# Choose which app directories to test (positional, like `run`)
hop3-test matrix apps/real-apps-native demos

# Use local code (the default; --from pypi installs from PyPI instead)
hop3-test matrix --from local

# Test against an already-provisioned server (no rebuild, no deploy)
hop3-test run --host <server> --reuse
```

### Supported Images

- `ubuntu-24.04` - Ubuntu 24.04 LTS (default)
- `debian-13` - Debian 13 (trixie)
- `debian-12` - Debian 12 (bookworm)
- `fedora-42` - Fedora 42
- `rocky-9` - Rocky Linux 9
- `alma-9` - AlmaLinux 9

## Troubleshooting

### A Docker e2e or app test failed

Inspect the saved diagnostic bundle by run id (printed in the failure headline):
```bash
hop3-test why <run-id>
```

### Tests Hang

- Check Docker daemon: `docker ps`
- Use verbose mode: `-v -s`
- Check container logs: `docker logs hop3-app-test`

### Import Errors

```bash
uv sync
```

### Docker Issues

```bash
# Clean up containers
docker rm -f hop3-app-test hop3-system-test

# Force a rebuild of the cached e2e image (the next c_e2e run rebuilds it)
docker rmi hop3-e2e:test
```

For detailed information, see [Testing Strategy](testing-strategy.md).
