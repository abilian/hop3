---
tutorial:
  name: nix-gen-flask-hop3-tutorial
  teardown:
    - rm -rf hop3-tuto-nix-gen-flask 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-nix-gen-flask -y 2>/dev/null || true
---

# Tutorial: Your Own Flask App, Built Hermetically by Nix

[Deploy a Flask App with Nix](nix-flask.md) gets its reproducibility from a `hop3.nix` you write by hand. This tutorial deploys the same application with no Nix code at all. You describe the app in `hop3.toml` and Hop3 generates the expression on the server, from your own source directory.

What you get is the same guarantee: the build runs offline, inside the Nix sandbox, from a dependency set fixed by a hash. Deploy the same commit next month, or on another server, and you get the same application. You don't need Nix on your machine.

## Prerequisites

1. **A Hop3 server**, installed with Nix (`hop3-install server --with nix`)
2. **The Hop3 CLI** on your machine
3. **[uv](https://docs.astral.sh/uv/)**, to write the lockfile

```bash exec id=check-uv
uv --version
```

```output regex
uv [0-9]+\.[0-9]+
```

## Step 1: Create the Project

```bash exec id=create-project
mkdir -p hop3-tuto-nix-gen-flask
```

The application is the one from the hand-written tutorial:

```file path=hop3-tuto-nix-gen-flask/app.py
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

## Step 2: Pin the Dependencies

A hermetic build cannot resolve `flask>=3` against PyPI: the answer changes from week to week. It installs from a lockfile in which every package has an exact version and a hash. Name what the app needs:

```file path=hop3-tuto-nix-gen-flask/requirements.in
flask==3.1.2
gunicorn==23.0.0
```

and let uv resolve the rest:

```bash exec id=lock dir=hop3-tuto-nix-gen-flask timeout=120
uv pip compile --quiet --generate-hashes --python-version 3.12 \
  --exclude-newer 2026-09-01 requirements.in -o requirements.txt
grep -c -- "--hash=sha256" requirements.txt
```

```output regex
[0-9]+
```

`--exclude-newer` resolves as of a date, so the lockfile in this tutorial is the same for every reader. In your own project, drop it, or move it forward when you mean to upgrade.

## Step 3: Describe the Build

```file path=hop3-tuto-nix-gen-flask/hop3.toml
[metadata]
id = "hop3-tuto-nix-gen-flask"
version = "0.1.0"

[build]
builder = "nix"

[nix]
# Generate the Nix expression from a template: a Python virtualenv built
# from the lockfile, with this directory installed beside it.
template = "python-venv"
pip-local-source = true
pip-requirements = "requirements.txt"
# The hash of every file the lockfile names, once downloaded.
pip-deps-hash = "sha256-+ILV5A5KTzX5dXcJatxIDptExr6D/bmcDRaOUzudIfU="
# MarkupSafe ships compiled wheels, one per architecture; its source
# distribution is the same bytes everywhere, so it is built from source and
# the hash above holds on x86 and ARM servers alike. Building it needs its
# build backend, pinned like everything else.
pip-source-packages = ["markupsafe"]
pip-build-requires = ["setuptools==84.0.0"]
runtime-package = "python312"
exec-target = "gunicorn"
exec-args = ["app:app", "--bind", "0.0.0.0:${PORT:-8080}"]

[healthcheck]
path = "/health"
```

Compare it with `hop3.nix` in the hand-written tutorial:

- `exec-target` and `exec-args` replace the wrapper script and `runtime.json`;
- the lockfile replaces `python3.withPackages`. Your dependencies come from PyPI at the versions you pinned, rather than from whatever nixpkgs packages.

Only one step of the build can reach the network: it downloads the files the lockfile names, and Nix checks the result against `pip-deps-hash`. Everything after it, including compiling MarkupSafe, runs offline.

## Step 4: Deploy

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

From the project directory, bind this checkout to that server. Signing in recorded it as the context `default`; until a checkout is bound, commands that reach a server are refused inside it:

```bash skip
hop3 context use default   # bind this checkout to the server you logged into
```

### Deploy

```bash exec id=deploy dir=hop3-tuto-nix-gen-flask timeout=900
hop3 deploy --app hop3-tuto-nix-gen-flask
```

```output contains
deployed successfully
```

The first deploy builds Python and the virtualenv, which takes a few minutes. Later deploys reuse everything whose inputs did not change: a change to `app.py` rebuilds only the application, in seconds.

### Set a Hostname

```bash exec id=set-hostname timeout=30
hop3 env set --app hop3-tuto-nix-gen-flask HOST_NAME=hop3-tuto-nix-gen-flask.$HOP3_TEST_DOMAIN
```

```bash exec id=redeploy dir=hop3-tuto-nix-gen-flask timeout=300
hop3 deploy --app hop3-tuto-nix-gen-flask
```

```output contains
deployed successfully
```

### Verify

```bash exec id=check-page timeout=30
curl -s https://hop3-tuto-nix-gen-flask.$HOP3_TEST_DOMAIN/
```

```output contains
Hello from Nix!
```

`git push` works the same way. Add the remote that `hop3 init` printed, and every push builds the commit you pushed:

```bash skip
git init && git add -A && git commit -m "Initial commit"
git push hop3 main
```

## When the Dependencies Change

Change `requirements.in`, run `uv pip compile` again, and the downloaded set changes with it. The recorded `pip-deps-hash` no longer matches, and the deploy stops before anything is installed:

```text
error: hash mismatch in fixed-output derivation '/nix/store/...-python-deps-0.1.0.drv':
         specified: sha256-+ILV5A5KTzX5dXcJatxIDptExr6D/bmcDRaOUzudIfU=
            got:    sha256-...
```

That is the guarantee working: nothing the hash does not cover reaches the build. Check that the change is the one you made, put the `got:` value in `pip-deps-hash`, and deploy again.

To record a first hash for a new project, start with a placeholder (`sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=`) and do the same.

A package that ships compiled wheels makes the downloaded set, and its hash, depend on the server's architecture. If a hash recorded on one server fails on another, add that package to `pip-source-packages`, as this tutorial does for MarkupSafe.

## What Differs from the Hand-Written Expression

| | Hand-written `hop3.nix` | Generated from `hop3.toml` |
|---|---|---|
| Nix knowledge | Required | None |
| Python packages | From nixpkgs | From PyPI, pinned by your lockfile |
| Reproducibility | Pinned nixpkgs | Pinned nixpkgs, plus a hash over every downloaded file |
| Nix on your machine | To test the build | Not needed |
| To take over by hand | n/a | `hop3 nix eject --app hop3-tuto-nix-gen-flask > hop3.nix` |

## Next Steps

- [The `[nix]` section of hop3.toml](../../reference/config.md#nix-template-based-nix-builds): every template and its keys, including `node-pnpm-install` (Node, from a pnpm lockfile), `go-source` and `php-app`, which build your own directory the same way
- [Deploy a Flask App with Nix](nix-flask.md): the same application with a hand-written expression
