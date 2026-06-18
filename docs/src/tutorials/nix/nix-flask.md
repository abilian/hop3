# Tutorial: Deploy a Flask App with Nix

This tutorial walks you through deploying a Flask application on Hop3 using Nix for a fully reproducible build. By the end, you'll have a working web app where every dependency — from Python to Gunicorn — is pinned by Nix.

## Prerequisites

1. **A Hop3 server** with Nix installed (the installer does this automatically)
2. **The Hop3 CLI** installed on your local machine
3. **Nix** installed locally for testing (`curl -L https://nixos.org/nix/install | sh`)

Verify Nix is working:

```bash
nix --version
```

## Step 1: Create the Project

```bash
mkdir nix-flask-demo && cd nix-flask-demo
```

Create `app.py`:

```python
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return f"Hello from Nix! Running on port {os.environ.get('PORT', '?')}"

@app.route("/health")
def health():
    return "ok"
```

## Step 2: Write the Nix Expression

Create `hop3.nix`:

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  # Define our Python environment with exact packages
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    gunicorn
  ]);

  # Build the application package
  app = pkgs.stdenv.mkDerivation {
    pname = "nix-flask-demo";
    version = "0.1.0";
    src = ./.;

    buildInputs = [ pythonEnv ];

    # Pure Python app — no compilation needed
    dontBuild = true;

    installPhase = ''
      # Create directories
      mkdir -p $out/app $out/bin $out/hop3

      # Copy application code
      cp app.py $out/app/

      # Create a wrapper script
      cat > $out/bin/start << 'WRAPPER'
#!/bin/sh
exec ${pythonEnv}/bin/python -m gunicorn app:app "$@"
WRAPPER
      chmod +x $out/bin/start

      # Runtime configuration for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/start --bind \$BIND_ADDRESS:\$PORT --chdir $out/app"
  },
  "env": {
    "FLASK_ENV": "production",
    "PYTHONDONTWRITEBYTECODE": "1"
  },
  "path": [
    "$out/bin",
    "${pythonEnv}/bin"
  ]
}
EOF
    '';
  };

in {
  package = app;
}
```

**What this does:**

- `pythonEnv` creates a Python environment with Flask and Gunicorn from nixpkgs
- The derivation copies `app.py` to the Nix store and creates a wrapper script
- `runtime.json` tells Hop3 how to start the app: run Gunicorn on `$BIND_ADDRESS:$PORT`

## Step 3: Configure Hop3

Create `hop3.toml`:

```toml
[build]
builder = "nix"
```

That's it. Hop3 reads `hop3.nix` and handles the rest.

## Step 4: Test the Build Locally

```bash
nix-build hop3.nix -A package --no-out-link
```

You should see output like:

```
/nix/store/abc123...-nix-flask-demo-0.1.0
```

Inspect the output:

```bash
result=$(nix-build hop3.nix -A package --no-out-link)
cat "$result/hop3/runtime.json"
ls "$result/bin/"
ls "$result/app/"
```

Optionally, test it runs:

```bash
PORT=5000 BIND_ADDRESS=127.0.0.1 "$result/bin/start" --bind 127.0.0.1:5000 --chdir "$result/app"
```

Visit `http://localhost:5000` — you should see "Hello from Nix!".

## Step 5: Deploy to Hop3

```bash
hop3 deploy --app nix-flask-demo
```

Or via git push:

```bash
git init && git add -A && git commit -m "Initial commit"
git remote add hop3 ssh://hop3@your-server/home/hop3/repos/nix-flask-demo.git
git push hop3 main
```

Hop3 will:

1. Detect `hop3.nix` and select the NixBuilder
2. Run `nix-build` on the server
3. Read `runtime.json` from the build output
4. Start Gunicorn as a managed daemon
5. Configure nginx to proxy requests to the app

## Step 6: Verify

```bash
hop3 app status --app nix-flask-demo
curl http://your-server:PORT/
```

## Adding a Database

To add PostgreSQL, update `hop3.toml`:

```toml
[build]
builder = "nix"

[[addons]]
type = "postgres"
```

Hop3 provisions the database and injects `DATABASE_URL`, `PGHOST`, `PGPORT`, etc. into your app's environment. Use them in your Flask app:

```python
import os
database_url = os.environ.get("DATABASE_URL")
```

## What's Different from Native Deployment?

| Aspect | Native (buildpack) | Nix |
|--------|-------------------|-----|
| Dependencies | `requirements.txt` | `hop3.nix` (nixpkgs) |
| Build tool | pip in virtualenv | nix-build |
| Reproducibility | Depends on PyPI state | Fully deterministic |
| Build speed | Fast (pip cache) | Slower first build, cached after |
| Configuration | Automatic detection | Explicit `hop3.nix` |

## Next Steps

- See [Deploying with Nix](../../guides/nix-deployment.md) for patterns in Go, Node.js, Ruby, and static sites
- See [Nix Integration Reference](../../reference/nix.md) for the full `runtime.json` specification
- Browse working examples in `apps/nix-apps/` (10 apps across 6 languages)
