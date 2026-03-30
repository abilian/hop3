# Deploying with Nix

This guide explains how to deploy applications on Hop3 using Nix for deterministic, reproducible builds. It covers when to use Nix, how to write a `hop3.nix` file, and common patterns for different languages.

## When to Use Nix

Nix-based deployment is a good choice when you want:

- **Reproducible builds**: The exact same source always produces the exact same output
- **Precise dependency control**: Pin every dependency to an exact version, including system libraries
- **Cross-language builds**: A single build system for polyglot applications
- **Offline builds**: All dependencies fetched upfront, no network access during build

For most applications, Hop3's native buildpacks (auto-detected from `requirements.txt`, `package.json`, etc.) are simpler and faster. Use Nix when reproducibility or dependency precision matters more than convenience.

## Prerequisites

- A Hop3 server with Nix installed (the installer does this automatically)
- Familiarity with [Nix expressions](https://nixos.org/manual/nix/stable/language/)
- A working `nix-build` on your local machine for testing

## How It Works

1. You add a `hop3.nix` file to your project
2. Set `builder = "nix"` in `hop3.toml`
3. Deploy with `hop3 deploy` (or `git push hop3 main`)
4. Hop3 runs `nix-build`, reads the runtime config, and starts your app

The `hop3.nix` file defines both *how to build* and *how to run* your application. The build output goes into the Nix store (`/nix/store/...`), and Hop3 reads `runtime.json` from the output to know which workers to start.

## Quick Start

### Step 1: Create hop3.toml

```toml
[build]
builder = "nix"
```

### Step 2: Write hop3.nix

A minimal `hop3.nix` for a Python Flask app:

```nix
{ pkgs ? import <nixpkgs> {} }:

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

      # Copy application code
      cp -r *.py $out/app/

      # Create start script
      cat > $out/bin/start << 'WRAPPER'
#!/bin/sh
exec ${pythonEnv}/bin/python -m gunicorn app:app "$@"
WRAPPER
      chmod +x $out/bin/start

      # Tell Hop3 how to run the app
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

### Step 3: Test Locally

```bash
nix-build hop3.nix -A package --no-out-link
```

### Step 4: Deploy

```bash
hop3 deploy my-flask-app
```

## The runtime.json Contract

The key to Nix integration is the `$out/hop3/runtime.json` file generated during the build. This tells Hop3 how to run your application.

```json
{
  "workers": {
    "web": "/nix/store/.../bin/start --bind $BIND_ADDRESS:$PORT"
  },
  "env": {
    "PYTHONDONTWRITEBYTECODE": "1"
  },
  "path": [
    "/nix/store/.../bin"
  ]
}
```

**Workers**: The `web` worker must listen on `$BIND_ADDRESS:$PORT` (Hop3 injects these). For static sites, use `"static": "/path/to/public"` and Hop3 serves files directly via nginx.

**Environment**: Variables set here are merged with `[env]` from hop3.toml and addon-injected variables (like `DATABASE_URL`).

**Path**: Directories prepended to `PATH` so the worker process can find its binaries.

## Common Patterns

### Go Application

Go apps are straightforward — `buildGoModule` compiles to a static binary:

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.buildGoModule {
    pname = "my-go-app";
    version = "0.1.0";
    src = ./.;
    vendorHash = null;  # Set to actual hash if using external deps

    postInstall = ''
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": { "web": "$out/bin/my-go-app" },
  "env": {},
  "path": ["$out/bin"]
}
EOF
    '';
  };

in { package = app; }
```

The Go binary reads `PORT` from the environment directly — no wrapper script needed.

### Node.js Application

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.buildNpmPackage {
    pname = "my-node-app";
    version = "0.1.0";
    src = ./.;
    npmDepsHash = "sha256-...";  # Run: nix hash to-sri --type sha256 $(nix-prefetch-npm-deps .)

    postInstall = ''
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "${pkgs.nodejs}/bin/node $out/lib/node_modules/my-node-app/index.js"
  },
  "env": { "NODE_ENV": "production" },
  "path": ["${pkgs.nodejs}/bin"]
}
EOF
    '';
  };

in { package = app; }
```

### Ruby (Rack/Sinatra)

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  gems = pkgs.bundlerEnv {
    name = "my-ruby-app-gems";
    ruby = pkgs.ruby;
    gemdir = ./.;  # Requires Gemfile, Gemfile.lock, and gemset.nix
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "my-ruby-app";
    version = "0.1.0";
    src = ./.;
    buildInputs = [ gems pkgs.ruby ];
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cp -r . $out/app/
      cat > $out/bin/start << 'WRAPPER'
#!/bin/sh
exec ${gems}/bin/rackup -p $PORT -o $BIND_ADDRESS $out/app/config.ru
WRAPPER
      chmod +x $out/bin/start
      cat > $out/hop3/runtime.json << EOF
{
  "workers": { "web": "$out/bin/start" },
  "env": { "RACK_ENV": "production" },
  "path": ["$out/bin", "${gems}/bin", "${pkgs.ruby}/bin"]
}
EOF
    '';
  };

in { package = app; }
```

Generate `gemset.nix` from your `Gemfile.lock` using `bundix`:

```bash
nix-shell -p bundix --run "bundix"
```

### Static Site

For static sites, point the `static` worker at a directory:

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.stdenv.mkDerivation {
    pname = "my-site";
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

Hop3 detects the `static` worker and configures nginx to serve the directory directly.

## Using Addons with Nix Apps

Nix apps work with Hop3 addons (PostgreSQL, MySQL, Redis) just like native apps. Addon environment variables (`DATABASE_URL`, `PGHOST`, `REDIS_URL`, etc.) are injected at runtime and available to your worker process.

```toml
# hop3.toml
[build]
builder = "nix"

[[addons]]
type = "postgres"

[[addons]]
type = "redis"
```

Your application reads these from the environment as usual.

## Debugging

### Build fails

Test locally first:

```bash
nix-build hop3.nix -A package --no-out-link --show-trace
```

### App starts but doesn't respond

Inspect the runtime.json:

```bash
result=$(nix-build hop3.nix -A package --no-out-link)
cat "$result/hop3/runtime.json"
```

Check that the `web` worker command is correct and uses `$BIND_ADDRESS:$PORT`.

### Missing runtime.json

The build succeeds but Hop3 can't find runtime config. Ensure your `installPhase` creates `$out/hop3/runtime.json`.

## Examples

Working examples for all supported languages are in `apps/nix-apps/`:

| App | Language | Description |
|-----|----------|-------------|
| `flask-hello` | Python | Flask + Gunicorn |
| `flask-alt` | Python | Flask alternate config |
| `flask-gunicorn` | Python | Flask with explicit Gunicorn |
| `golang-minimal` | Go | stdlib HTTP server |
| `golang-gin` | Go | Gin framework |
| `nodejs-express` | Node.js | Express framework |
| `rack-hello` | Ruby | Rack middleware |
| `sinatra-hello` | Ruby | Sinatra framework |
| `clojure-hello` | Clojure | Ring/Jetty |
| `static-hello` | HTML | Static files |

## Related

- [Nix Integration Reference](../reference/nix.md) — Full technical reference
- [hop3.toml Reference](../reference/config.md) — Configuration options
- [User Guide](user-guide.md) — General deployment guide
