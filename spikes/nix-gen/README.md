# hop3-nix-gen (spike)

Template-based `hop3.nix` generator for Hop3.

**Status:** Spike / proof-of-concept, isolated from the main Hop3 codebase.
**Context:** See `local-notes/alternative-nix-expr-gen.md`.

## Why a Spike?

This package is intentionally standalone so it can iterate fast without
touching the main Hop3 build or test suite. Once the approach is validated,
the generator will be integrated into `packages/hop3-server/src/hop3/plugins/build/nix/`.

## Package Layout

```
spikes/nix-gen/
├── pyproject.toml
├── src/hop3_nix_gen/
│   ├── spec.py          # Dataclasses: AppSpec, Source, ConfigFile, ConditionalEnvVar
│   ├── escaping.py      # Nix string escaping
│   ├── registry.py      # Template registry + generate()
│   ├── templates/
│   │   ├── base.py              # Template protocol
│   │   ├── prebuilt_binary.py   # Single binary download (miniflux, gitea)
│   │   └── prebuilt_archive.py  # Tar/zip archive (focalboard, grafana, mattermost, vikunja)
│   ├── specs/
│   │   ├── miniflux.py
│   │   ├── gitea.py
│   │   ├── focalboard.py
│   │   ├── grafana.py
│   │   ├── mattermost.py
│   │   └── vikunja.py
│   └── cli.py
├── tests/
│   └── test_*.py
└── scripts/
    └── validate_all.py  # Generate all .nix and build them with nix-build
```

## Usage

```bash
# From spikes/nix-gen/
uv sync

# Generate a single app
uv run hop3-nix-gen miniflux > /tmp/miniflux.nix

# Generate all apps
uv run python scripts/validate_all.py --generate

# Generate + parse check (fast, no network)
uv run python scripts/validate_all.py --parse

# Generate + full nix-build (slow, needs network to fetch sources)
uv run python scripts/validate_all.py --build

# Run tests
uv run pytest
```

## Currently Supported

| Template | Count | Apps |
|----------|-------|------|
| `prebuilt-binary` | 2 | miniflux, gitea |
| `prebuilt-archive` | 4 | focalboard, grafana, mattermost, vikunja |
| `php-app` | 10 | adminer, bookstack, dolibarr, easy-appointments, invoice-ninja, kanboard, limesurvey, matomo, nextcloud, wordpress |
| `node-prebuilt` | 1 | wiki-js |
| `java-war` | 1 | jenkins |
| `python-venv` | 1 | isso |
| `nixpkgs-wrapper` | 1 | radicale |
| **Total** | **20** | |

**All 20 apps build successfully** with `nix-build` (out of 22 apps
in `apps/real-apps-nix/`). The remaining 2 apps (sinatra-hello,
rack-hello) are Ruby/bundlerEnv test apps — a `ruby-bundler` template
would cover them.

### PHP template variations validated

The `php-app` template covers a wide range of PHP app patterns:
- **Single file** (`adminer.php`)
- **Tarball with composer build** (bookstack, dolibarr, easy-appointments, invoice-ninja)
- **Tarball without build** (kanboard, matomo, wordpress)
- **tar.bz2 archive** (nextcloud)
- **Zip archive with wrapper directory** (limesurvey, via `source_root`)
- **Custom web root** (dolibarr serves from `htdocs` subdirectory)
- **Laravel artisan serve** (bookstack, invoice-ninja)
- **Composer with platform-reqs override** (invoice-ninja)
- **Extra native build inputs** (invoice-ninja needs nodejs)

### Currently in `apps/real-apps-nix-bad/` (not covered)

cryptpad, etherpad, hedgedoc, listmonk, matrix-synapse, searxng,
sonarqube, xwiki — these have known upstream packaging issues and
are stashed until fixed.

## Validation Methodology

A generated Nix expression is considered valid if:

1. **Parses** — `nix-instantiate --parse` succeeds
2. **Builds** — `nix-build --no-out-link` produces a store path
3. **Wrapper is correct** — the generated wrapper script contains expected env var references
4. **Matches hand-written** — the diff against the existing `hop3.nix` contains no functional differences (cosmetic diffs are OK)

The `scripts/validate_all.py` script automates (1), (2), and (4).
