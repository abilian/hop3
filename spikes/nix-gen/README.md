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

| Template | Apps |
|----------|------|
| `prebuilt-binary` | miniflux, gitea |
| `prebuilt-archive` | focalboard, grafana, mattermost, vikunja |

6 apps covered, matching the `prebuilt-*` pattern in `apps/real-apps-nix/`.

## Validation Methodology

A generated Nix expression is considered valid if:

1. **Parses** — `nix-instantiate --parse` succeeds
2. **Builds** — `nix-build --no-out-link` produces a store path
3. **Wrapper is correct** — the generated wrapper script contains expected env var references
4. **Matches hand-written** — the diff against the existing `hop3.nix` contains no functional differences (cosmetic diffs are OK)

The `scripts/validate_all.py` script automates (1), (2), and (4).
