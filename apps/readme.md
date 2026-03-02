# Apps

Sample applications used to test, validate, and demonstrate the Hop3 platform.

## Directory Structure

| Directory | Purpose | Count |
|-----------|---------|-------|
| `test-apps/` | Minimal "Hello World" apps for CI and development testing | 11 |
| `test-apps-fail/` | Apps that need fixes (currently empty) | 0 |
| `real-apps/` | Real-world apps for manual testing | 3 |
| `sandbox/` | Experimental configurations | 2 |
| `marketplace/` | Community app catalog (future marketplace) | 32 |
| `ngi-apps/` | NGI project packaged applications | 30+ |

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

## real-apps/

Real-world applications for manual integration testing.

- `ghost` - Ghost blogging platform
- `matomo` - Web analytics
- `moinmoin` - Wiki engine

## sandbox/

Experimental or work-in-progress configurations.

- `docker-flask-example` - Docker deployment example
- `mattermost` - Team collaboration (experimental)

## marketplace/

Future marketplace catalog with 32 applications across categories:

**CMS/Blogs:** Ghost, DokuWiki, Moodle, Piwigo
**Collaboration:** Hedgedoc, Mattermost, OpenProject, Taiga, Weblate
**Analytics:** Ackee, Matomo, Umami
**Business:** Abilian SBE, Baserow, Cal.com, Dolibarr, Pretix
**DevOps:** Gitea (via ngi-apps), Redash, Redmine
**Media:** PeerTube, Penpot
**Other:** Filebrowser, Kanboard, LimeSurvey, Listmonk, Miniflux, MoinMoin, Nextcloud, OpenCloud, Radicale, RocketChat, VPN

## ngi-apps/

NGI (Next Generation Internet) project packaged applications. Primary focus for production-ready deployments.

### Structure

```
ngi-apps/
├── docker-based/     # 31 apps - Containerized deployments
├── native-based/     # 30 apps - Native uWSGI deployments
├── docker-bad/       # 3 apps  - Unsupported (documented blockers)
├── sandbox/          # 1 app   - Experimental
└── *.md              # Documentation
```

### docker-based/ (31 apps)

Production-ready Docker Compose configurations using `debian:trixie-slim` base images.

Applications: adminer, bookstack, cryptpad, dolibarr, easy-appointments, etherpad, focalboard, formbricks, ghost, gitea, grafana, hedgedoc, invoice-ninja, isso, jenkins, kanboard, limesurvey, mastodon, matomo, matrix-synapse, mattermost, miniflux, monica, nextcloud, radicale, searxng, sonarqube, umami, vikunja, wiki-js, wordpress, xwiki

### native-based/ (30 apps)

Native deployments using Hop3's toolchain system (Python, Node.js, PHP, Java, Go).

Applications: adminer, bookstack, cryptpad, dolibarr, easy-appointments, etherpad, focalboard, ghost, gitea, grafana, hedgedoc, invoice-ninja, isso, jenkins, kanboard, limesurvey, listmonk, matomo, matrix-synapse, mattermost, miniflux, monica, nextcloud, radicale, searxng, sonarqube, vikunja, wiki-js, wordpress, xwiki

### docker-bad/ (3 apps - Unsupported)

Applications that cannot be supported due to technical constraints:

| App | Reason |
|-----|--------|
| `discourse` | Complex Ruby/Redis/Sidekiq setup |
| `taiga` | Multi-container architecture |
| `wekan` | Node.js 14 EOL + MongoDB requirement |

See `NATIVE-DEPLOYMENT-BLOCKERS.md` for apps requiring Docker due to runtime constraints (umami, uptime-kuma, formbricks).

## Running Tests

```bash
# Test apps using hop3-test
uv run hop3-test apps

# System tests (Docker-based)
uv run pytest packages/hop3-server/tests/c_system/ -v

# E2E tests (full deployment)
uv run pytest packages/hop3-server/tests/d_e2e/ -v

# NGI apps testing
cd apps/ngi-apps && python test-script.py
```
