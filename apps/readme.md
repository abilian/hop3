# Apps

Sample applications used to test, validate, and demonstrate the Hop3 platform.

## Directory Structure

| Directory | Purpose | Deployment Method |
|-----------|---------|-------------------|
| `test-apps-procfile/` | Minimal "Hello World" apps for CI testing | Procfile / hop3.toml (native) |
| `test-apps-nix/` | Same minimal apps, built with Nix | hop3.nix |
| `real-apps/` | Real-world apps (manual testing) | Various |
| `real-apps-docker/` | Production apps via Docker Compose | Dockerfile |
| `real-apps-native/` | Production apps via Hop3 toolchains | download scripts + hop3.toml |
| `real-apps-nix/` | Production apps built with Nix | hop3.nix |
| `internal-apps/` | Hop3 internal apps (admin UI, etc.) | — |
| `bad/` | Apps that cannot be supported (documented blockers) | — |
| `sandbox/` | Experimental configurations | — |

## test-apps-procfile/

Minimal applications covering core language toolchains. Used in E2E tests.

| App | Stack | Description |
|-----|-------|-------------|
| `000-static` | Static | HTML/CSS served by nginx |
| `010-flask-pip-wsgi` | Python | Flask with pip, uWSGI |
| `020-nodejs-express` | Node.js | Express.js |
| `030-golang-gin` | Go | Gin framework |
| `030-rack` | Ruby | Rack with Puma server |
| `040-sinatra` | Ruby | Sinatra with Puma |
| `050-clojure` | Clojure | Aleph server via Leiningen uberjar |
| `100-flask-gunicorn-pip` | Python | Flask with Gunicorn |
| `110-flask-gunicorn-poetry` | Python | Flask with Poetry |
| `120-flask-pip-alt` | Python | Flask with config in hop3/ subdir |
| `130-golang-minimal` | Go | Minimal Go HTTP server |

## test-apps-nix/

The same minimal apps, but built using Nix instead of native toolchains. Each app has a `hop3.nix` file that defines the build derivation and a `hop3.toml` with `builder = "nix"`.

Apps: clojure-hello, flask-alt, flask-gunicorn, flask-hello, golang-gin, golang-minimal, nodejs-express, rack-hello, sinatra-hello, static-hello

## real-apps-nix/

Production-ready applications built with Nix. Each has a `hop3.nix` that downloads and packages the application using `fetchurl`, `buildGoModule`, or similar Nix builders.

Apps: adminer, bookstack, cryptpad, dolibarr, easy-appointments, etherpad, focalboard, gitea, grafana, hedgedoc, invoice-ninja, isso, jenkins, kanboard, limesurvey, listmonk, matomo, matrix-synapse, mattermost, miniflux, nextcloud, radicale, searxng, sonarqube, vikunja, wiki-js, wordpress, xwiki

## real-apps-docker/

Production-ready Docker Compose configurations using `debian:trixie-slim` base images.

## real-apps-native/

Native deployments using Hop3's toolchain system (Python, Node.js, PHP, Java, Go). Each app has a download script and hop3.toml configuration.

## bad/

Applications that cannot be supported due to technical constraints:

| App | Reason |
|-----|--------|
| `discourse` | Complex Ruby/Redis/Sidekiq setup |
| `taiga` | Multi-container architecture |
| `wekan` | Node.js 14 EOL + MongoDB requirement |

## Scripts

### build-nix-apps.py

Builds Nix apps locally by running `nix-build` on each `hop3.nix` file. Supports auto-fixing SHA256 hash mismatches.

```bash
# Build all nix apps (test + real)
./build-nix-apps.py

# Build only test apps
./build-nix-apps.py test-apps-nix

# Build only real apps
./build-nix-apps.py real-apps-nix

# Build a single app (searched in all dirs)
./build-nix-apps.py --app adminer

# Auto-fix placeholder SHA256 hashes
./build-nix-apps.py --fix-hashes

# Verbose output with build progress
./build-nix-apps.py -v --fix-hashes

# Debug failed builds (shows full nix stderr)
./build-nix-apps.py --debug

# Custom timeout per app (default: 300s)
./build-nix-apps.py --timeout 600
```

### test-script.py

Deploys and tests apps against a running Hop3 server.

```bash
python test-script.py "real-apps-docker/*"
python test-script.py real-apps-native/wordpress
python test-script.py --cleanup --debug real-apps-docker/ghost
```

### test-docker-local.py

Tests Docker image builds locally (no deployment).

```bash
python test-docker-local.py real-apps-docker/*
python test-docker-local.py --no-cache real-apps-docker/wordpress
```

## Running Tests

### Using hop3-test (recommended)

```bash
# Test all test-apps
uv run hop3-test apps

# Test specific app by path
uv run hop3-test apps apps/test-apps-procfile/010-flask-pip-wsgi

# Test against remote server
uv run hop3-test apps --target remote --host hop3.dev

# Test nix apps on remote server
uv run hop3-test cloud --suites nix-apps
```

### Using pytest

```bash
# System tests (Docker-based)
uv run pytest packages/hop3-server/tests/c_system/ -v

# E2E tests (full deployment)
uv run pytest packages/hop3-server/tests/d_e2e/ -v
```
