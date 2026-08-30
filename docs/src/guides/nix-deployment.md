# Deploying with Nix

This guide explains how to deploy applications on Hop3 using Nix for reproducible builds and content-addressed dependency management.

## Two ways to use Nix

Hop3 supports two modes for Nix-based deployment, in order of preference:

1. **Template mode (recommended).** You declare what your app needs in
   `hop3.toml` (`[nix]` section), and Hop3 generates the Nix expression
   for you. No Nix knowledge required.
2. **Hand-crafted mode (escape hatch).** You provide your own
   `hop3.nix` file. Use this when the templates can't express what you
   need.

**Pick exactly one.** If both a `hop3.nix` file and a `[nix].template` section in `hop3.toml` are present, NixBuilder refuses to build and prints an error pointing you to either delete `hop3.nix` or remove the `[nix]` section. To convert a template to a hand-crafted file, run `hop3 nix eject <app>` (which writes the file and is the deliberate way to switch from generated to hand-crafted mode).

## When to use Nix

Nix-based deployment is a good choice when you want:

- **Reproducible builds**: the exact same source produces the exact
  same output (with caveats — see below)
- **Content-addressed closures**: precise dependency tracking, smaller
  diffs on updates
- **Multi-architecture support**: builds work on x86_64, aarch64,
  ARM, RISC-V, etc.
- **Cross-language builds**: a single build system for polyglot apps

For most simple applications, Hop3's native buildpacks (auto-detected from `requirements.txt`, `package.json`, etc.) are simpler and faster. Use Nix when reproducibility, dependency precision, or non-x86 support matters.

### Reproducibility tiers

Every template builds in a sealed sandbox against a hash-pinned dependency set, so all three tiers rebuild bit-for-bit. The tier tells you where the bytes came from:

| Tier | Method | Rebuilds identically | Auditable to source | Multi-arch |
|------|--------|--------------|-----------|------------|
| 1 | nixpkgs package (`pkgs.foo`) | Yes | Yes | Yes |
| 2 | Source build against a committed lockfile | Yes | Yes | One arch per lockfile |
| 3 | Pre-built upstream artefact (`fetchurl`) | Yes | No | Usually x86_64 only |

**Tier 1 is the goal.** When the upstream is in nixpkgs at a usable version, prefer the `nixpkgs-wrapper` template — you get the maintained nixpkgs build for free, including multi-arch support.

**Tier 2 is where most real apps land**, because nixpkgs either doesn't package them or packages a version you can't deploy. You commit the ecosystem's lockfile (`requirements.txt`, `composer.lock`, `pnpm-lock.yaml`, `go.sum`, `gemset.nix`, `deps.json`); Hop3 vendors it into a fixed-output derivation and builds offline against that. Same auditability as Tier 1, but the lockfile is yours to refresh.

**Tier 3 is a known compromise.** Pre-built artefact templates (`prebuilt-binary`, `prebuilt-archive`, `node-prebuilt`, `java-war`) are convenient for apps whose upstream ships no buildable source for the packaged version, but they sacrifice auditability: you are trusting the upstream release process. Treat them as a stepping stone toward a nixpkgs or source build.

Run `hop3-tools nix tiers <app-dir>` to see the tier of any app, and `make gate-nix` to check that the corpus both rebuilds identically and still deploys.

## Prerequisites

- A Hop3 server with Nix installed (the installer does this
  automatically when you pass `--with nix`)
- A working `nix-build` on your local machine for testing (optional
  but strongly recommended)

## Quick start: template mode

For an app that's already in nixpkgs, a few lines of `hop3.toml` are enough to deploy it. Here's Miniflux:

```toml
[metadata]
id = "miniflux"
description = "Minimalist RSS reader"

[build]
builder = "nix"

[nix]
template = "nixpkgs-wrapper"
nixpkgs-package = "miniflux"
exec-target = "miniflux"

[nix.env-exports]
LISTEN_ADDR = "0.0.0.0:${PORT:-8080}"

[[addons]]
type = "postgres"
```

Hop3 will:
1. Generate a `hop3.nix` that wraps `pkgs.miniflux`
2. Run `nix-build` to fetch/build the source via nixpkgs
3. Create a startup wrapper that exports the env vars
4. Hand off to the deployer

No Nix code, no `fetchurl`, no hash to maintain.

## Available templates

| Template | When to use |
|----------|-------------|
| `nixpkgs-wrapper` | App is already in nixpkgs (preferred — Tier 1) |
| `python-venv` | Python apps installed via pip into a virtualenv |
| `php-app` | PHP apps (Composer + extensions + writable dirs) |
| `java-war` | Java WAR files served with a JDK |
| `ruby-bundler` | Ruby apps using `bundlerEnv` from `gemset.nix` |
| `prebuilt-binary` | Single binary from upstream releases (Tier 3) |
| `prebuilt-archive` | Multi-file archive from upstream releases (Tier 3) |
| `node-prebuilt` | Node.js apps shipped as a pre-built tarball (Tier 3) |

For full template field reference, see the [hop3.toml `[nix]` section](../reference/config.md#nix-template-based-nix-builds).

## Source builds vs pre-built binaries

The nixpkgs-wrapper template builds from source via nixpkgs. The `prebuilt-*` and `node-prebuilt` templates download a pre-compiled binary from upstream's release page.

**Pre-built has serious downsides:**

- **Not reproducible.** You can pin the SHA-256 hash, but you can't
  rebuild from source. You trust the upstream CI.
- **x86_64-linux only.** No ARM, RISC-V, PowerPC, etc. Blocks edge and
  IoT deployment.
- **Supply chain risk.** A compromised upstream release could
  distribute malicious binaries.

**Source builds via nixpkgs:**

- Built from source by nixpkgs maintainers
- Multi-arch (x86_64-linux, aarch64-linux, armv7l-linux, riscv64-linux,
  and more)
- Source hash and dependency closure tracked by Nix
- Reproducible via a pinned nixpkgs commit (nixos-24.11) — no per-app version maintenance

**The rule:** if `pkgs.<your-app>` exists in nixpkgs, use
`nixpkgs-wrapper`. Only fall back to a `prebuilt-*` template when there
is no nixpkgs alternative.

To check if your app is in nixpkgs:

```bash
nix-instantiate --eval -E '(import (builtins.fetchTarball "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz") {}).<name>.meta.description or "NOT FOUND"'
```

## Hand-crafted hop3.nix

When the templates don't fit, write a `hop3.nix` directly. Two cases where this is necessary:

1. The app needs custom build steps that no template covers
2. You need to combine nixpkgs sources with custom wrapping

When you `hop3 nix eject <app>`, Hop3 materializes the generated Nix expression as a real `hop3.nix` file you can edit (the `[nix]` section in `hop3.toml` is then ignored).

### Minimal hand-crafted example

A simple Python Flask app:

```nix
{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    gunicorn
  ]);

  app = pkgs.stdenv.mkDerivation {
    pname = "my-flask-app";
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

The `runtime.json` is the contract between your Nix derivation and Hop3's deployer. See the [Nix reference](../reference/nix.md) for the full schema.

### Wrapping a nixpkgs source build

A more advanced pattern: use `pkgs.<name>` for the actual application binary but customise the wrapper. This is what the `nixpkgs-wrapper` template does, but you can write it directly when you need full control:

```nix
{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  gitea = pkgs.gitea;

  app = pkgs.stdenv.mkDerivation {
    pname = "gitea";
    version = gitea.version;
    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/gitea-wrapper << 'WRAPPER'
      #!/bin/sh
      mkdir -p custom/conf data
      # ... generate app.ini from env vars ...
      exec ${gitea}/bin/gitea web
      WRAPPER
      chmod +x $out/bin/gitea-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": { "web": "$out/bin/gitea-wrapper" },
        "env": {},
        "path": ["$out/bin", "${gitea}/bin"]
      }
      EOF
    '';
  };

in { package = app; }
```

Notice: no `fetchurl`. The `${gitea}` interpolation is a reference to the nixpkgs-built source. Multi-arch and reproducible.

## Static sites

Static sites use a special `static` worker. Hop3 detects the `"static"` key in `runtime.json` and configures nginx to serve files directly — no backend process runs.

```nix
{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  app = pkgs.stdenv.mkDerivation {
    pname = "my-site";
    version = "0.1.0";
    src = ./.;
    dontBuild = true;
    installPhase = ''
      mkdir -p $out/public $out/hop3
      cp -r public/* $out/public/

      cat > $out/hop3/runtime.json <<EOF
      {
        "workers": { "static": "$out/public" },
        "env": {}
      }
      EOF
    '';
  };
in { package = app; }
```

## Using addons

Nix apps work with Hop3 addons (PostgreSQL, MySQL, Redis) just like native apps. Addon environment variables (`DATABASE_URL`, `PGHOST`, `REDIS_URL`, etc.) are injected at runtime and available to your worker process:

```toml
# hop3.toml
[build]
builder = "nix"

[nix]
template = "nixpkgs-wrapper"
nixpkgs-package = "miniflux"
exec-target = "miniflux"

[[addons]]
type = "postgres"

[[addons]]
type = "redis"
```

Your application reads `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, and `REDIS_URL` from the environment.

## The `nix eject` command

When you've outgrown the templates and need to customise the generated Nix expression, run:

```bash
hop3 nix eject <app-name>
```

This materializes the auto-generated Nix expression as a real `hop3.nix` file in your source directory. After ejection, the NixBuilder uses the committed `hop3.nix` and the `[nix]` section in `hop3.toml` is ignored.

The ejected file includes a header noting which template it came from and the date of ejection.

## Debugging

### Build fails

Test locally first:

```bash
nix-build hop3.nix --no-out-link --show-trace
```

### App starts but doesn't respond

Inspect the runtime.json:

```bash
result=$(nix-build hop3.nix --no-out-link)
cat "$result/hop3/runtime.json"
```

Check that the `web` worker command is correct and uses `$BIND_ADDRESS:$PORT` (or sets `LISTEN_ADDR` from `$PORT`).

### Missing runtime.json

The build succeeds but Hop3 can't find the runtime config. Ensure your `installPhase` creates `$out/hop3/runtime.json`.

### Generated Nix isn't what you expected

Run the generator manually to see what Hop3 would produce:

```bash
hop3 nix eject <app-name>
cat <app-source>/hop3.nix
```

The eject command writes the generated file but does not deploy. You can review, edit, or revert.

## Examples

Working examples organized by approach:

| Directory | Approach |
|-----------|----------|
| `../hop3-catalog/apps/<status>/<app>-nixgen/` | Template-based (preferred) |
| `../hop3-catalog/apps/<status>/<app>-nix/` | Hand-crafted `hop3.nix` files |
| `apps/test-apps-nix-gen/`, `apps/test-apps-nix/` | Small smoke-test fixtures |

Notable examples:

| App | Template / approach | Notes |
|-----|---------------------|-------|
| `beta/miniflux-nixgen` | nixpkgs-wrapper | Cleanest case — a short `[nix]` block over a nixpkgs package |
| `beta/gitea-nixgen` | nixpkgs-wrapper | INI config generation at startup |
| `alpha/grafana-nixgen` | nixpkgs-wrapper | PostgreSQL backend, env-driven homepath |
| `beta/wordpress-nixgen` | php-app | Composer + writable dir handling |
| `alpha/landing-nix` | hand-crafted | Minimal static site reference |
| `alpha/wiki-js-nix` | hand-crafted | Wraps nixpkgs source with `node` runtime |

## Related

- [Nix Integration Reference](../reference/nix.md) — Full technical
  reference, runtime.json schema
- [hop3.toml `[nix]` section](../reference/config.md#nix-template-based-nix-builds)
  — All template fields
- [`nix eject` command](../reference/cli.md#hop3-nix-eject) — CLI reference
- [User Guide](user-guide.md) — General deployment guide
