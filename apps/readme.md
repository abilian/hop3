# Apps

Sample applications used to test, validate, and demonstrate the Hop3 platform.

## Directory Structure

| Directory | Purpose | Count |
|-----------|---------|-------|
| `test-apps/` | Minimal "Hello World" apps for CI and development testing | 11 |
| `docker-apps/` | Production-ready Docker Compose deployments | 31 |
| `native-apps/` | Native uWSGI deployments using Hop3 toolchains | 30 |
| `docker-bad/` | Apps that cannot be supported (documented blockers) | 3 |
| `marketplace/` | Community app catalog (future marketplace) | 32 |
| `real-apps/` | Real-world apps for manual testing | 3 |
| `sandbox/` | Experimental configurations | 2 |

## test-apps/

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

## docker-apps/ (31 apps)

Production-ready Docker Compose configurations using `debian:trixie-slim` base images.

Applications: adminer, bookstack, cryptpad, dolibarr, easy-appointments, etherpad, focalboard, formbricks, ghost, gitea, grafana, hedgedoc, invoice-ninja, isso, jenkins, kanboard, limesurvey, mastodon, matomo, matrix-synapse, mattermost, miniflux, monica, nextcloud, radicale, searxng, sonarqube, umami, vikunja, wiki-js, wordpress, xwiki

## native-apps/ (30 apps)

Native deployments using Hop3's toolchain system (Python, Node.js, PHP, Java, Go).

Applications: adminer, bookstack, cryptpad, dolibarr, easy-appointments, etherpad, focalboard, ghost, gitea, grafana, hedgedoc, invoice-ninja, isso, jenkins, kanboard, limesurvey, listmonk, matomo, matrix-synapse, mattermost, miniflux, monica, nextcloud, radicale, searxng, sonarqube, vikunja, wiki-js, wordpress, xwiki

## docker-bad/ (3 apps - Unsupported)

Applications that cannot be supported due to technical constraints:

| App | Reason |
|-----|--------|
| `discourse` | Complex Ruby/Redis/Sidekiq setup |
| `taiga` | Multi-container architecture |
| `wekan` | Node.js 14 EOL + MongoDB requirement |

## marketplace/

Future marketplace catalog with 32 applications across categories:

**CMS/Blogs:** Ghost, DokuWiki, Moodle, Piwigo
**Collaboration:** Hedgedoc, Mattermost, OpenProject, Taiga, Weblate
**Analytics:** Ackee, Matomo, Umami
**Business:** Abilian SBE, Baserow, Cal.com, Dolibarr, Pretix
**DevOps:** Gitea, Redash, Redmine
**Media:** PeerTube, Penpot
**Other:** Filebrowser, Kanboard, LimeSurvey, Listmonk, Miniflux, MoinMoin, Nextcloud, OpenCloud, Radicale, RocketChat, VPN

## real-apps/

Real-world applications for manual integration testing.

- `ghost` - Ghost blogging platform
- `matomo` - Web analytics
- `moinmoin` - Wiki engine

## sandbox/

Experimental or work-in-progress configurations.

- `docker-flask-example` - Docker deployment example
- `mattermost` - Team collaboration (experimental)

## Running Tests

### Using hop3-test (recommended)

```bash
# Test all test-apps
uv run hop3-test apps

# Test specific app by path
uv run hop3-test apps apps/test-apps/010-flask-pip-wsgi

# Test against remote server
uv run hop3-test apps --target remote --host hop3.dev
```

### Using test-script.py (for docker-apps/native-apps)

```bash
# Test all Docker apps
python apps/test-script.py "docker-apps/*"

# Test specific app
python apps/test-script.py docker-apps/wordpress

# Test native apps
python apps/test-script.py "native-apps/*"

# Test with cleanup and debug
python apps/test-script.py --cleanup --debug docker-apps/ghost
```

### Using test-docker-local.py (local Docker builds only)

```bash
# Test Docker image builds locally (no deployment)
python apps/test-docker-local.py docker-apps/*

# Build without cache
python apps/test-docker-local.py --no-cache docker-apps/wordpress
```

### Using pytest

```bash
# System tests (Docker-based)
uv run pytest packages/hop3-server/tests/c_system/ -v

# E2E tests (full deployment)
uv run pytest packages/hop3-server/tests/d_e2e/ -v
```
