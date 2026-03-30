# Nix Integration Reference

This document provides a complete reference for deploying applications on Hop3 using Nix.

## Overview

Hop3 supports Nix-based deployments as an alternative to native buildpacks and Docker. When a `hop3.nix` file is present in the application source, Hop3 uses the NixBuilder to produce deterministic, reproducible builds.

Nix integration is currently in **Phase 1**: applications must provide their own `hop3.nix` file.

## Architecture

The NixBuilder is a Level 1 Builder in Hop3's two-level build architecture:

- **Level 1 (Builders)**: Orchestrate *how* to build (LocalBuilder, DockerBuilder, **NixBuilder**)
- **Level 2 (LanguageToolchains)**: Execute *what* to build (Python, Node, Ruby, etc.)

NixBuilder does **not** delegate to LanguageToolchains. All build logic is encapsulated in the `hop3.nix` expression.

## hop3.toml Configuration

To use the NixBuilder, set the builder in `hop3.toml`:

```toml
[build]
builder = "nix"
```

No other configuration is required. The NixBuilder reads everything it needs from `hop3.nix`.

## hop3.nix File Format

The `hop3.nix` file is a standard Nix expression that evaluates to an attribute set with:

| Attribute | Required | Description |
|-----------|----------|-------------|
| `package` | Yes | A Nix derivation that builds the application |
| `env` | No | Static environment variables (attribute set) |

### runtime.json

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
| `workers` | Yes | Map of worker name to command. Use `web` for HTTP workers, `static` for static file directories. |
| `env` | No | Environment variables to set at runtime |
| `path` | No | Paths to prepend to `PATH` |

### Worker Types

| Worker Name | Behavior |
|-------------|----------|
| `web` | Spawned as a uWSGI daemon. Must listen on `$BIND_ADDRESS:$PORT`. |
| `static` | Value is a directory path. Hop3 serves it via nginx. |
| Other names | Spawned as generic uWSGI daemons. |

### Variable Substitution

Worker commands support shell variable expansion at runtime. The following variables are available:

- `$PORT` — Port assigned by Hop3
- `$BIND_ADDRESS` — Bind address (default `127.0.0.1`)
- All environment variables from `[env]`, addons, and `runtime.json`

## Build Process

When Hop3 deploys a Nix app:

1. Detects `hop3.nix` in the source directory
2. Verifies `nix-build` is available
3. Runs: `nix-build hop3.nix -A package --no-out-link`
4. Reads `$out/hop3/runtime.json` from the built store path
5. Produces a `BuildArtifact` with:
   - `kind="nix"` (or `kind="static"` for static-only apps)
   - `location` pointing to the Nix store path
   - `runtime` containing workers, env vars, and PATH from `runtime.json`
6. Hands off to the deployer (uWSGI or static file server)

## Nix Installation

Nix is installed automatically by the Hop3 server installer. It supports:

- **Multi-user (daemon)**: Used when systemd is available. Provides better isolation.
- **Single-user**: Fallback for containers and non-systemd environments.

To manually install Nix on a Hop3 server:

```bash
hop3-install server --with nix
```

## Example: Minimal hop3.nix

### Python (Flask + Gunicorn)

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    gunicorn
  ]);

  app = pkgs.stdenv.mkDerivation {
    pname = "myapp";
    version = "0.1.0";
    src = ./.;
    buildInputs = [ pythonEnv ];
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cp -r *.py $out/app/
      cat > $out/bin/start << 'WRAPPER'
#!/bin/sh
exec ${pythonEnv}/bin/python -m gunicorn app:app "$@"
WRAPPER
      chmod +x $out/bin/start
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/start --bind \$BIND_ADDRESS:\$PORT --chdir $out/app"
  },
  "env": { "PYTHONDONTWRITEBYTECODE": "1" },
  "path": ["$out/bin", "${pythonEnv}/bin"]
}
EOF
    '';
  };
in { package = app; }
```

### Go

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.buildGoModule {
    pname = "myapp";
    version = "0.1.0";
    src = ./.;
    vendorHash = null;  # No external dependencies

    postInstall = ''
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": { "web": "$out/bin/myapp" },
  "env": {},
  "path": ["$out/bin"]
}
EOF
    '';
  };
in { package = app; }
```

### Static Site

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.stdenv.mkDerivation {
    pname = "mysite";
    version = "0.1.0";
    src = ./.;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/public $out/hop3
      cp -r public/* $out/public/
      cat > $out/hop3/runtime.json << EOF
{ "workers": { "static": "$out/public" }, "env": {} }
EOF
    '';
  };
in { package = app; }
```

## Local Development

### Validate a Nix Build

```bash
cd apps/nix-apps/flask-hello
nix-build hop3.nix -A package --no-out-link
```

### Validate All Nix Apps

```bash
./scripts/build-nix-apps.py
./scripts/build-nix-apps.py --app flask-hello  # Single app
./scripts/build-nix-apps.py --verbose           # Show store paths
```

### Inspect Runtime Config

```bash
result=$(nix-build hop3.nix -A package --no-out-link)
cat "$result/hop3/runtime.json" | python3 -m json.tool
```

## Limitations (Phase 1)

- Applications must provide their own `hop3.nix` file (no auto-generation)
- Nix must be installed on the server (`nix-build` must be in PATH)
- Build times can be longer on first build (Nix store is cached for subsequent builds)
- No flake support yet (standard `import <nixpkgs>` only)

## Related

- [ADR 006: Nix Integration](https://git.sr.ht/~sfermigier/hop3/tree/devel/notes/adrs/006-nix-integration.md) — Architecture decision
- [User Guide](../guides/user-guide.md) — General deployment guide
- [hop3.toml Reference](config.md) — Full configuration reference
