# hop3-tooling

Maintainer and operator tooling for Hop3 — the durable scripts that outgrew the
repo-root `scripts/` directory, given a real home with discovery, help, and
tests ([ADR 057](../../notes/adrs/057-hop3-tooling-package.md)).

This is a **maintainer** tool: it is not shipped to end users and never runs on
the app-runtime path. User-facing commands live in `hop3-cli`; the E2E test
framework is `hop3-testing`; installing the platform is `hop3-installer`.

## Command

```bash
uv run hop3-tools --help
```

### `catalog` — keep the catalog identical to its tested source

The catalog (`hop3-catalog`) ships each app's `hop3.toml` + `scripts/` as a
**verbatim copy** of its tested source in `apps/real-apps-native/<app>/`, plus a
catalog-only overlay (`catalog.toml`, readmes, icons). See plan
`local-notes/plans/11-catalog-acceptance.md`.

```bash
# Fail if any catalog recipe drifted from its tested source (CI gate)
uv run hop3-tools catalog drift

# Copy tested recipe(s) into the catalog (overlay untouched), then re-check
uv run hop3-tools catalog promote gitea forgejo
uv run hop3-tools catalog promote --all
uv run hop3-tools catalog drift

# Install catalog apps and functionally verify their admin bootstrap
uv run hop3-tools catalog verify --insecure --deploy --cleanup
uv run hop3-tools catalog verify --insecure --apps gitea,radicale
```

`verify` asserts, per app, that the old default credential is rejected, the
Hop3-generated one works, and registration/anonymous access is closed — through
the app's real auth surface, not a bare 200. The dev box serves self-signed
certs, so pass `--insecure` against it.

## Tests

```bash
uv run pytest packages/hop3-tooling/tests
```
