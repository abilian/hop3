# Nix Integration Reference

This document is the technical reference for deploying applications on Hop3 using Nix. For a tutorial-style introduction, see the [Nix deployment guide](../guides/nix-deployment.md).

## Overview

Hop3 supports Nix-based deployments as an alternative to native buildpacks and Docker. Two modes are supported:

1. **Generated mode (ADR 008).** Hop3 generates a `hop3.nix` file at
   build time from a `[nix]` section in `hop3.toml`, using one of the
   built-in templates. This is the preferred mode for most apps.
2. **Hand-crafted mode.** The user provides a `hop3.nix` file directly.
   Used when the templates don't fit, or when extracted via
   `hop3 nix eject`.

**The two modes are mutually exclusive.** If both a `hop3.nix` file and a `[nix].template` section in `hop3.toml` are present, NixBuilder raises `Abort` rather than silently picking one. The error message points the user to either delete `hop3.nix` or remove the `[nix]` section. To deliberately convert a template to a hand-crafted file, use `hop3 nix eject --app <app-name>`.

## Architecture

The NixBuilder is a Level 1 Builder in Hop3's two-level build architecture:

- **Level 1 (Builders)**: Orchestrate *how* to build (LocalBuilder,
  DockerBuilder, **NixBuilder**)
- **Level 2 (LanguageToolchains)**: Execute *what* to build (Python,
  Node, Ruby, etc.)

NixBuilder does **not** delegate to LanguageToolchains. All build logic is encapsulated in the `hop3.nix` expression — either hand-crafted or generated.

## hop3.toml configuration

To use the NixBuilder, set the builder in `hop3.toml`:

```toml
[build]
builder = "nix"
```

For template-generated mode, also add a `[nix]` section. See the [hop3.toml reference](config.md#nix-template-based-nix-builds) for the full schema.

## Build process

When Hop3 deploys a Nix app:

1. NixBuilder accepts the build if either condition holds:
   - A `hop3.nix` file exists in the source directory, **or**
   - The `[nix]` section in `hop3.toml` declares a `template`
2. Verifies `nix-build` is available
3. Resolves the Nix file:
   - **Hand-crafted mode**: uses the existing `hop3.nix`
   - **Generated mode**: generates a `hop3.nix` from the `[nix]`
     section using the appropriate template
4. Runs: `nix-build hop3.nix -A package --out-link .nix-result`
   (`--out-link` registers a GC root so nix's garbage collector can't
   delete a running app's closure).
5. Reads `$out/hop3/runtime.json` from the built store path
6. Produces a `BuildArtifact` with:
   - `kind="nix"` (or `kind="static"` for static-only apps)
   - `location` pointing to the Nix store path
   - `runtime` containing workers, env vars, and PATH from
     `runtime.json`
7. Hands off to the deployer (uWSGI for `kind="nix"`, StaticDeployer
   for `kind="static"`)

## hop3.nix file format

The `hop3.nix` file is a standard Nix expression that evaluates to an attribute set with:

| Attribute | Required | Description |
|-----------|----------|-------------|
| `package` | Yes | A Nix derivation that builds the application |
| `env` | No | Static environment variables (attribute set) |

## runtime.json contract

The built package **must** generate `$out/hop3/runtime.json` containing runtime configuration:

```json
{
  "workers": {
    "web": "/nix/store/.../bin/myapp --bind $BIND_ADDRESS:$PORT"
  },
  "env": {
    "VAR_NAME": "value"
  },
  "path": [
    "/nix/store/.../bin"
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `workers` | Yes | Map of worker name to command |
| `env` | No | Environment variables to set at runtime |
| `path` | No | Paths to prepend to `PATH` |

### Worker types

| Worker name | Behavior |
|-------------|----------|
| `web` | Spawned as a uWSGI daemon. Must listen on `$BIND_ADDRESS:$PORT`. |
| `static` | Value is a directory path. Hop3 serves it via nginx (StaticDeployer). |
| Other names | Spawned as generic uWSGI daemons. |

If `workers` contains **only** the key `"static"`, Hop3 produces a `BuildArtifact` with `kind="static"` and the StaticDeployer takes over. Otherwise the artifact has `kind="nix"` and uWSGI manages all workers.

### Variable substitution

Worker commands support shell variable expansion at runtime. The following variables are available:

- `$PORT` — Port assigned by Hop3
- `$BIND_ADDRESS` — Bind address (default `127.0.0.1`)
- All environment variables from `[env]`, addons, and `runtime.json`

Note: Nix `${...}` interpolations in `hop3.nix` are evaluated by Nix at build time and produce store paths. Shell `$VAR` expansions are evaluated at runtime by the wrapper. To produce a literal `${VAR}` in the generated wrapper script, escape it as `''${VAR}` inside Nix `''` strings.

## Templates (generated mode)

Eleven built-in templates cover common deployment patterns. Templates are selected by setting `template = "<name>"` in the `[nix]` section of `hop3.toml`.

| Template | Use case | Reproducibility tier |
|----------|----------|----------------------|
| `nixpkgs-wrapper` | Apps already in nixpkgs | 1 (best) |
| `python-venv` | Python apps built from a hash-pinned `requirements.txt` | 2 |
| `php-app` | PHP apps built from `composer.lock` + extensions | 2 |
| `go-source` | Go apps built from source with `buildGoModule` | 2 |
| `node-pnpm-install` | Node.js apps built from a committed `pnpm-lock.yaml` | 2 |
| `ruby-bundler` | Ruby apps using `bundlerEnv` from `gemset.nix` | 2 |
| `java-gradle` | Java apps built with Gradle from a committed `deps.json` | 2 |
| `java-war` | Java WAR files served with a JDK | 3 (WAR from upstream) |
| `node-prebuilt` | Node.js apps shipped as a pre-built tarball | 3 (compromise) |
| `prebuilt-binary` | Single binary from upstream releases | 3 (compromise) |
| `prebuilt-archive` | Multi-file archive from upstream releases | 3 (compromise) |

For the full field reference per template, see the [hop3.toml `[nix]` section](config.md#nix-template-based-nix-builds).

### Reproducibility tiers

Every template builds in the Nix sandbox with no network access, against a hash-pinned dependency set, so all three tiers rebuild bit-for-bit. What the tier tells you is where the running bytes came from:

| Tier | Method | Rebuilds identically | Auditable to source | Multi-arch |
|------|--------|--------------|-----------|------------|
| 1 | nixpkgs package (`pkgs.foo`) | Yes | Yes | Yes |
| 2 | Source build against a committed lockfile (pip, composer, pnpm, go, bundler, gradle) | Yes | Yes | One arch per lockfile |
| 3 | Pre-built upstream artefact (`fetchurl`) | Yes | No — the binary is taken on trust | Usually x86_64-linux only |

Tier 1 is the goal: you inherit nixpkgs' build, its architectures and its security updates for free. Tier 2 is where most real apps land, because nixpkgs either doesn't package them or packages a version you can't deploy; you get the same auditability, but the lockfile is yours to refresh. Tier 3 is a floor for apps whose upstream ships no buildable source for the packaged version.

To see the tier of every app in a checkout:

```bash
hop3-tools nix tiers apps/real-apps-nix-gen
```

A tier describes the *build*, never the running app. A bit-identical rebuild says nothing about whether the app starts — see [reproducibility checks](#checking-reproducibility) below.

### Checking reproducibility

```bash
make check-reproducible    # rebuild every nix-gen app, fail if any output drifts
make gate-nix              # the above, AND a clean deploy of the same corpus
```

`check-reproducible` builds each recipe and then rebuilds it with `nix build --rebuild`, which compares the second output against the first. Use `--ssh <host>` to build on a Linux box from a macOS checkout. An app is only advertise-ready when `gate-nix` passes: reproducible *and* running.

## The `nix eject` command

```bash
hop3 nix eject --app <app-name>
```

Materializes the auto-generated `hop3.nix` from the template into a real file in the app's source directory. After ejection:

- The committed `hop3.nix` is used directly by NixBuilder
- The `[nix]` section in `hop3.toml` is ignored
- You can edit the file freely

The ejected file includes a header noting which template it came from and the date of ejection.

Use `nix eject` when:

- You need to add custom build logic the templates don't support
- You want to pin the generated Nix expression for reproducibility
- You want to commit the exact build recipe to version control

## Nix installation

Nix is installed automatically by the Hop3 server installer when you pass `--with nix`. It supports:

- **Multi-user (daemon)**: Used when systemd is available. Provides
  better isolation.
- **Single-user**: Fallback for containers and non-systemd
  environments.

To manually install Nix on a Hop3 server:

```bash
hop3-install server --with nix
```

## Local development

### Validate a Nix build

```bash
cd apps/real-apps-nix-gen/miniflux
# For template mode, generate first:
uv run python -c "
from hop3.plugins.build.nix.gen import generate
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config
import tomllib
from pathlib import Path
config = tomllib.loads(Path('hop3.toml').read_text())
spec = app_spec_from_config(config['nix'], config.get('metadata', {}), 'miniflux')
print(generate(spec))
" > /tmp/hop3.nix
nix-build /tmp/hop3.nix --no-out-link

# For hand-crafted mode, just build directly:
cd apps/real-apps-nix/landing
nix-build hop3.nix --no-out-link
```

### Inspect runtime config

```bash
result=$(nix-build hop3.nix --no-out-link)
cat "$result/hop3/runtime.json" | python3 -m json.tool
```

### Validate all Nix apps

```bash
hop3-test run --docker --clean --with nix apps/real-apps-nix
hop3-test run --docker --clean --with nix apps/real-apps-nix-gen
```

## Limitations

- Nix must be installed on the server (`nix-build` must be in PATH).
  The installer handles this when `--with nix` is passed.
- First builds can be slow as the Nix store is populated. Subsequent
  builds and re-deploys are fast (Nix caches everything).
- No flake support yet. nixpkgs is pinned to a specific commit
  (nixos-24.11) via fetchTarball, not resolved through a channel /
  NIX_PATH.
- The `prebuilt-*` templates are x86_64-linux only and not
  reproducible from source. Use `nixpkgs-wrapper` when possible.
- Some apps in nixpkgs (e.g., Wiki.js) ship as a raw source tree
  without a `bin/<name>` wrapper, so the `nixpkgs-wrapper` template
  doesn't fit them directly. Hand-crafted mode is the workaround.

## Related

- [ADR 006: Nix Integration](/developers/adrs/006-nix-integration/)
  — Phase 1 architecture decision
- [ADR 008: Template-Based Nix Generation](/developers/adrs/008-nix-builders-2/)
  — Phase 3 template system
- [ADR 058: Build Reproducibility Model](/developers/adrs/058-build-reproducibility-model/)
  — what the tiers mean, how the claim is checked, and what it is scoped to
- [Nix Deployment Guide](../guides/nix-deployment.md) — Tutorial-style
  introduction
- [hop3.toml `[nix]` section](config.md#nix-template-based-nix-builds)
  — Field-by-field reference
- [`nix eject` command](cli.md#hop3-nix-eject)
