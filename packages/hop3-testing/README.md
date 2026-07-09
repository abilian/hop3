# hop3-testing

Testing framework for Hop3 deployment validation.

## Overview

hop3-testing provides utilities and fixtures for testing Hop3 deployments. It supports running tests against Docker containers or remote servers, with a catalog of test applications covering various languages and frameworks.

## Features

- **Multiple targets**: Test against Docker containers or remote SSH servers
- **App catalog**: Pre-built test applications for various languages
- **Deployment sessions**: Automated deploy/verify/cleanup workflow
- **pytest fixtures**: Integration with pytest for E2E testing
- **Category filtering**: Run tests by language or framework

## Installation

```bash
pip install hop3-testing
```

## Quick Start

```bash
# List available tests
hop3-test list

# Run system tests on Docker
hop3-test run --docker

# Test specific apps
hop3-test apps 010-flask-pip-wsgi

# Test against remote server
hop3-test apps --host server.example.com

# Run CI tests
hop3-test ci
```

## Commands

| Command | Description |
|---------|-------------|
| `hop3-test run` | Deploy Hop3 and run the catalog (`system` is a deprecated alias) |
| `hop3-test run --reuse` | Test against an existing deployment (skip deploy) |
| `hop3-test list` | List available tests (`--show NAME` for one test's details) |
| `hop3-test run --provider hetzner --images ...` | E2E across cloud OS images (Hetzner) |
| `hop3-test upgrade-chain` | Install a baseline release on a fresh box, then upgrade in-place through a version chain |
| `hop3-test why <run-id>` | Replay a saved diagnostic bundle for a failed run |

Test profile (fast/CI/full) is selected with `--mode` on `run`, not a separate
subcommand: `hop3-test run --docker --mode ci`.

### Upgrade chain

`hop3-test upgrade-chain` validates that a running server survives a *chain* of in-place upgrades. Each hop is a git ref, installed by **that version's own** `hop3-deploy-server` (checked out into a worktree and run via `uv run`), on a **fresh** box; every hop after the first is an in-place update, and each is asserted to come back healthy with a readable schema.

```bash
# Fresh Docker container: 0.6.2 → current tree
hop3-test upgrade-chain --docker

# Fresh Hetzner VPS (needs HETZNER_API_TOKEN + HETZNER_SERVER_ID)
hop3-test upgrade-chain --provider hetzner --image ubuntu-24.04

# Custom chain (release tags + `local` for the current tree)
hop3-test upgrade-chain --docker --chain 0.6.2,local
```

Cheapest smoke — exercises the whole mechanism (fresh install → in-place
upgrade → assertions) with no old-version/worktree variable:

```bash
hop3-test upgrade-chain --docker --chain local,local
```

`--host <server>` is accepted but warns: it targets an existing server, not the clean slate an upgrade chain assumes. `0.6.0` is not a viable baseline (its `hop3-rootd` can't start) and is excluded from the default chain.

### Common Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Verbose output |
| `--fail-fast` | Stop on first failure |
| `--keep` | Keep apps deployed after testing |
| `--docker` | Use Docker target |
| `--host HOST` | Remote server hostname |

## Architecture

```
hop3-testing/
├── src/hop3_testing/
│   ├── cli/              # CLI commands
│   │   └── commands/     # Click command implementations
│   ├── catalog/          # Test discovery
│   │   ├── scanner.py    # Discovers test.toml files
│   │   └── models.py     # TestDefinition, Category
│   ├── apps/
│   │   ├── catalog.py    # AppSource dataclass
│   │   └── deployment.py # DeploymentSession
│   ├── targets/
│   │   ├── base.py       # DeploymentTarget ABC
│   │   ├── docker.py     # DockerTarget
│   │   └── remote.py     # RemoteTarget
│   └── results/          # Result storage and reporting
└── tests/
```

## Test Categories

| Category | Languages/Frameworks |
|----------|---------------------|
| `python` | Flask, FastAPI, Django |
| `nodejs` | Express, Fastify |
| `ruby` | Sinatra, Rails |
| `go` | Fiber, Gin |
| `rust` | Actix-web, Axum |
| `static` | HTML, Hugo, Jekyll |

## Cloud Runs & the Image Sweep

Run full E2E tests across cloud OS images with `hop3-test run --provider hetzner
--images ...`. Each image is a full `hop3-test run --provider hetzner` (provision a
fresh box → deploy → test → persist), so a cloud run shares `run`'s lexicon:
positional app names, `--from`, `--branch`, `--with`. Requires `HETZNER_API_TOKEN`
and `HETZNER_SERVER_ID` (a dedicated throwaway box).

```bash
# List available images
hop3-test run --list-images

# Single distribution (a sweep-of-one)
hop3-test run --provider hetzner --image ubuntu-24.04 apps/test-apps-procfile

# Across multiple distributions
hop3-test run --provider hetzner --images ubuntu-24.04,debian-13,fedora-42

# From PyPI instead of local code
hop3-test run --provider hetzner --from pypi --images all
```

### Cloud Run Options (`run --provider hetzner`)

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Single OS image — a sweep-of-one (e.g. ubuntu-24.04) |
| `--images LIST` | Comma-separated images or `all` |
| `--list-images` | List available OS images |
| `--from {local,git,pypi}` | Install source (same as `run`; default: local) |
| `--branch BRANCH` | Git branch (with `--from git`; default: devel) |
| `--with FEATURES` | Extra server features (repeatable or comma-separated) |
| `-x, --fail-fast` | Stop on the first failing image |
| `--continue-on-failure` | Don't stop on first failure (multi-distro) |

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [Testing Strategy](../../docs/src/dev/testing-strategy.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server being tested
- [hop3-cli](../hop3-cli/) - CLI used for deployments in tests

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
