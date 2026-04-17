# App Porting Tips for Hop3

*A practical cookbook for packaging a self-hosted open-source application as a Hop3 app. Distilled from ~30 real apps packaged between late 2025 and April 2026. Paired with [`notes/lessons-learned/`](./lessons-learned/) (topic-specific deep dives) and the [ADR index](./adrs/).*

## 1. Before you start

### 1.1 The four-variant standard

Each packaged app should ship in four parallel variants under `apps/real-apps-*/<app>/`:

| Variant | Directory | Role |
|---------|-----------|------|
| **native** | `real-apps-native/` | Built with Hop3's language toolchains (Python venv, npm, composer, Go, Cargo). Uses host PostgreSQL/Redis via the addon. |
| **docker** | `real-apps-docker/` | Self-contained `Dockerfile` built from `debian:trixie-slim`. No official upstream images. |
| **nix hand-crafted** | `real-apps-nix/` | Operator-written `hop3.nix`. Maximum flexibility. |
| **nix from template** | `real-apps-nix-gen/` | Generated from one of the eight templates via `[nix]` in `hop3.toml`. |

When a variant is genuinely infeasible, defer it to `apps/bad/real-apps-*-bad/<app>/` with a `DEFERRED.md` naming the blocker and the unblocker. Silent gaps are worse than explicit ones.

### 1.2 URL preflight

Upstream repos move. Upstream release assets change shape. Three real cases from this catalogue:

- **GoToSocial** migrated GitHub → Codeberg; old URL 404s.
- **Stirling-PDF** jumped from the 0.x line to the 2.x line with asset renames.
- **Vaultwarden** ships *no* prebuilt binaries at all — only Docker images.

Preflight every URL with `curl -sIL` before scaffolding; a 15-second check saves a 15-minute test cycle. When upstream has no prebuilt binary, choose between compiling from source (long builds, 10-min docker-build cap applies) or deferring.

### 1.3 Major-version behaviour changes

A version bump can flip runtime defaults. Stirling-PDF 2.x bakes the `security` Spring profile into the JAR at build time: `DOCKER_ENABLE_SECURITY=false` — which worked on 0.x — no longer disables authentication. Diagnose via "what profile is active in the startup logs"; fix at the health-check path (use a public endpoint like `/login` rather than `/`).

### 1.4 Package format = `sovereign_name+version` pinning

Pin versions explicitly in `hop3.toml`, `Dockerfile`, and download scripts. Moving-target references (`latest`, default branches, abstract ranges) mean two deploys from the same source tree produce different closures. Hop3 is a deployment system, not a continuous-build system.

## 2. Python apps

### 2.1 Dependency format: know what you have

Five possibilities, in decreasing order of preference (and per ADR 039):

1. **`uv.lock`** (uv-managed, fully pinned). Best case. Hop3's Python toolchain runs `uv sync --frozen --reinstall` directly.
2. **`pyproject.toml` with PEP-621 `[project].dependencies`**. Works via `pip install .`. No lockfile, but deps resolve.
3. **`requirements.txt` (fully frozen with `==`)**. Works fine. Prefer this over abstract requirements.
4. **`pyproject.toml` with PEP-735 `[dependency-groups]` only** (no `[project]`). Toolchain can't consume directly. **Convert at packaging time** — see 2.3.
5. **Poetry-native `pyproject.toml` with `[tool.poetry.dependencies]` only**. Same story — convert at packaging time.

### 2.2 Packaging-time freeze (pattern)

When the upstream doesn't ship a format the toolchain can use directly, convert in `scripts/download.sh` and commit the output. Per ADR 039, the deployer's job is to install what's declared — conversion is a packaging activity.

**From PEP-735 groups to requirements.txt** (pure-Python, no external tooling needed):

```python
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
deps = data.get("dependency-groups", {}).get("main", [])
with open("requirements.txt", "w") as out:
    for dep in deps:
        if isinstance(dep, str):
            out.write(dep + "\n")
```

**From Poetry lockfile to requirements.txt** (needs Poetry on the packaging machine):

```bash
poetry export --only=main --without-hashes -f requirements.txt -o requirements.txt
```

### 2.3 Gunicorn isn't always available

Modern Django stacks sometimes don't depend on gunicorn. GlitchTip ships with **granian** (Rust-based WSGI/ASGI server); BookWyrm declares its own runtime. Use whatever the upstream declares:

```toml
# hop3.toml
[run]
start = "granian app.wsgi:application --interface wsgi --host 0.0.0.0 --port $PORT"
```

Append gunicorn to `requirements.txt` only if you need it and upstream doesn't ship an alternative.

### 2.4 Django `[env]` strict-load

Some Django apps use `environs` or `django-environ` with `env("FOO")` (no default) — at import time, these raise if `FOO` is unset. BookWyrm does this for the whole `EMAIL_*` group even when email is unused. **Provide stubs for every env var the app touches at import time**, even if they're functionally unused:

```bash
export EMAIL_HOST="localhost"
export EMAIL_HOST_USER="noreply"
export EMAIL_HOST_PASSWORD="changeme"
# ... the full group the app's settings.py reads unconditionally
```

If unsure, read the app's `settings.py` top-to-bottom looking for `env(...)` calls without defaults.

### 2.5 psycopg under Nix

Nix-built Python venvs break pip-installed binary wheels that reference system libs by content-hash filename. Three tiers of pain, in order:

1. `psycopg2-binary`'s `_psycopg.so` references `libkrb5-fcafa220.so.3.3` that isn't shipped alongside the wheel on Nix Python. Fails at runtime.
2. `psycopg[binary]` (v3) has the same class of issue on some systems.
3. Pure-Python `psycopg` works — IF `libpq.so.5` is on `LD_LIBRARY_PATH`.

**Current working pattern** for `apps/real-apps-nix/<app>/hop3.nix`:

```nix
cat > $out/bin/app-start << 'WRAPPER'
#!/bin/sh
export LD_LIBRARY_PATH="${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib:${pkgs.stdenv.cc.cc.lib}/lib:''${LD_LIBRARY_PATH:-}"
...
WRAPPER
```

Add `libstdc++.so.6` (`pkgs.stdenv.cc.cc.lib`) for any package that pulls a C++ native ext (`symbolic`, some ML libs, etc.). If pip-install of another C extension complains about a missing shared lib at runtime, add the nixpkgs package to LD_LIBRARY_PATH.

This is **not fixable from `real-apps-nix-gen/`** today — the `python-venv` template has no Nix-interpolation hook. See `notes/lessons-learned/nix-packaging.md` §Deferred limitations for the pattern.

### 2.6 Secret key persistence

`SECRET_KEY = { random = true }` in hop3.toml's `[env]` is **not a real feature** — it's silently ignored. More importantly: env exports from `before-run` scripts **do not propagate** to the uWSGI daemon (uWSGI's `attach-daemon` re-exports PATH and overrides the env). Two working patterns:

**Pattern A: persist in a config file on first run**

```bash
# In before-run or equivalent
if [ ! -f secret_key.txt ]; then
    head -c 32 /dev/urandom | base64 > secret_key.txt
fi
export SECRET_KEY="$(cat secret_key.txt)"
```

**Pattern B: write into the app's settings file**

```bash
if [ ! -f app_config.py ]; then
    cat > app_config.py <<EOF
SECRET_KEY = "$(head -c 32 /dev/urandom | base64)"
ALLOWED_HOSTS = ["*"]
EOF
fi
```

Pattern B was necessary for Bugsink because Bugsink's `docker.py.template` expects `SECRET_KEY` to come from env, but env doesn't propagate. Writing directly to the generated `bugsink_conf.py` sidesteps the propagation problem entirely.

### 2.7 PostgreSQL extensions

Some apps want extensions: `pg_trgm` (full-text search), `bloom` (index type), `hstore`, `citext`, `pgvector`. Hop3's per-app PostgreSQL user currently **cannot create extensions** — migrations that run `CREATE EXTENSION bloom` fail with `permission denied`. Affects: BookWyrm, Funkwhale, Pretalx, Lemmy, Plausible (PG-only mode).

Until the PG addon is taught to grant CREATE on the per-app database, these apps are deferred. See `apps/bad/real-apps-*-bad/bookwyrm/DEFERRED.md`.

### 2.8 Django default settings vs apps that require their own

Some apps (Bugsink) require a user-provided settings module:

- Bugsink ships `bugsink-create-conf --template docker` — generates `bugsink_conf.py` which sets `DJANGO_SETTINGS_MODULE=bugsink_conf`. The file must be in the cwd (or on PYTHONPATH) for both `bugsink-manage` and `gunicorn`.
- When running gunicorn: pass `--pythonpath .` so the module is found in the working directory.

## 3. Node apps

### 3.1 npm vs pnpm

Some published npm packages ship built code that references `.pnpm/` layout:

- **Directus** — plain `npm install directus` produces a flat `node_modules/` tree where named ESM imports of CommonJS modules fail (`SyntaxError: Named export 'Type' not found`).
- Install with pnpm instead, OR use Docker (the Directus docker build works with npm).

### 3.2 Native-compile dependencies

Some Node packages (Directus via `undici` et al.) pull native extensions that link against system libraries at install time — `-lbrotlidec`, `-ljemalloc`, etc. On the Hop3 server (Debian) these dev-headers are not installed by default.

**Today**: `[build].packages = ["libbrotli-dev", "build-essential", "python3", "pkg-config"]` is declared in `hop3.toml` but **not consumed** by the builder. Native deploys of apps needing these fail. Hop3 gap G2 will unlock this; see the improvement plan.

Workaround: use the docker variant (Dockerfile installs its own system deps).

### 3.3 Runtime deps

Document runtime binary deps separately from build deps:

- Owncast needs `ffmpeg` at runtime.
- Stirling-PDF needs `libreoffice`, `tesseract-ocr`, `qpdf`, `poppler-utils` (dropped in our packaging for build-time reasons — document functionality trade-offs).

## 4. PHP apps

### 4.1 Webroot pattern

Most PHP apps have a clear webroot — usually `public/`, `www/`, or `htdocs/`. Paheko uses `src/www/`. Pass this to the PHP built-in server:

```toml
[run]
start = "php -S 0.0.0.0:${PORT:-8080} -t src/www"
```

For Apache-based deployments, set `DocumentRoot` to the same directory.

### 4.2 First-run installer

Many PHP apps have a first-run web installer (`/install.php`, `/admin/install.php`, `/setup/index.php`). Point the healthcheck there rather than `/` so it returns 200 even before initial setup:

```toml
[healthcheck]
path = "/admin/install.php"
```

### 4.3 Apache URL rewriting vs PHP built-in server

Apache reads `.htaccess` for URL rewriting. PHP's built-in server does **not**. If the app relies on rewriting (Paheko's `apache-htaccess.conf`, WordPress's permalinks), use Apache in the docker variant and either:

- Use a PHP router script (`php -S ... -t www router.php`) for native, OR
- Accept that `php -S` only handles direct file requests (fine for first-run install page; breaks nice URLs).

### 4.4 PHP extensions

Declare in `hop3.toml`:

```toml
[nix]
php-extensions = ['sqlite3', 'gd', 'mbstring', 'xml', 'curl', 'zip', 'intl']
```

For docker, install via apt:

```dockerfile
apt-get install -y php php-sqlite3 php-gd php-mbstring php-xml php-zip php-curl php-intl
```

## 5. Go apps

### 5.1 Source vs prebuilt

Go single-binary apps are usually the easiest:

- If upstream ships prebuilt tarballs → `prebuilt-archive` or `prebuilt-binary` template (Tier-3 reproducibility).
- If upstream is in nixpkgs → `nixpkgs-wrapper` template (Tier-1).
- If neither — Gatus — build from source: multi-stage `golang:1-trixie` → `debian:trixie-slim` docker; native `go build` step.

### 5.2 Embedded vs sibling assets

Modern Go apps tend to embed web assets via Go's `embed` package (Owncast). Older/mid apps ship web assets alongside the binary (GoToSocial, WriteFreely). For the latter, the binary's search path must include the assets directory. When packaging via Nix, the sibling-assets case currently can't use the `nixpkgs-wrapper` template (see template-limitations).

### 5.3 Forgejo/Gitea authorized_keys gotcha

Forgejo 14+ refuses to start if `~/.ssh/authorized_keys` contains keys it didn't create. Hop3 writes its own CLI keys there. Fix: always set `DISABLE_SSH = true` in the app's config.

## 6. Rust apps

### 6.1 The Vaultwarden problem

Rust-compile-from-source times exceed Hop3's 10-minute Docker-build cap. Hop3 server has no Rust toolchain for native variants. Hop3 gap G3 (tier-aware Docker timeout) and G4 (Rust toolchain provisioning) together would unlock.

For now: package via `pkgs.vaultwarden` from nixpkgs (already compiled), defer docker + native variants.

## 7. Nix packaging specifics

### 7.1 String escaping

Inside Nix `''` indented strings, `${...}` is Nix interpolation (substituted at build time); `''${...}` is a literal that ends up as `${...}` in the output (a shell variable reference at runtime).

Nix interpolation vs. shell variables — quick rule:

```nix
# Nix binding, interpolated at build:
echo ${pkgs.nodejs}/bin/node

# Shell variable, resolved at runtime:
echo ''${PORT}
```

### 7.2 fetchurl + URL without extension

If the URL doesn't end in `.tar.gz` / `.zip` / etc., stdenv's `unpackPhase` can't auto-detect the archive format:

```nix
src = pkgs.fetchurl {
  url = "https://codeload.github.com/foo/bar/tar.gz/refs/tags/${version}";
  name = "bar-${version}.tar.gz";  # explicit — unpacker reads the extension
  sha256 = "...";
};
```

### 7.3 `$out` is undefined at wrapper runtime

The `$out` variable is a Nix-build-time concept. Referencing `$out/venv/bin/...` in a wrapper script or `hop3.toml` `pre-exec` ends up as `/venv/bin/...` at runtime.

Two working mechanisms:

1. **VENVBIN sentinel** (python-venv template): write `VENVBIN/<binary>` in the wrapper; the installPhase runs `sed -i "s|VENVBIN|$out/venv/bin|g"` at build time.
2. **Nix interpolation in the hop3.nix body**: `${packageName}/bin/<binary>` resolves at Nix eval. Works directly inside the derivation's installPhase, fragile elsewhere.

### 7.4 `__noChroot = true`

When pip/npm/composer need network at build time, add `__noChroot = true` to the derivation. Requires `sandbox = relaxed` in `/etc/nix/nix.conf` on the server (Hop3 installer configures this).

### 7.5 nixpkgs sometimes ships only the binary

WriteFreely nixpkgs-build omits `templates/`, `pages/`, `static/`. Hybrid pattern: pull the upstream release tarball via `fetchurl` and mix-and-match:

```nix
let
  writefreely = pkgs.writefreely;  # binary only
  wfRelease = pkgs.fetchurl {
    url = "...release.tar.gz";
    sha256 = "...";
  };
in ...
  tar xzf ${wfRelease} -C $out/share/writefreely --strip-components=1
  # config points templates_parent_dir at $out/share/writefreely
```

## 8. uWSGI runtime

### 8.1 `attach-daemon` env inheritance

uWSGI's `attach-daemon` re-exports PATH and doesn't inherit the parent's env cleanly. Anything the daemon needs, put in `runtime.json`'s `env` block (for Nix apps) or in `[env]` (for non-Nix).

### 8.2 Start timeouts

Default health-check start-timeout is 60s. Many apps need longer on first deploy (first-run migrations, asset compilation, warm-up). Override per app:

```toml
[run]
start-timeout = 180    # Forgejo, GlitchTip
start-timeout = 300    # Directus (bootstrap + start)
```

For Docker apps with heavy-compile builds (Rust, JVM) the *deploy* timeout (tier-aware) is different from the Docker-build timeout (10-min hardcoded, see gap G3).

### 8.3 Multi-worker via `[run.workers]`

For apps that need a web process + a background worker sharing the same source tree:

```toml
[run]
start = "gunicorn app.wsgi:application --bind 0.0.0.0:$PORT"

[run.workers]
celery = "celery -A myapp worker --loglevel=info"
```

For multi-component apps (different source trees, different runtimes, different resource limits) see ADR 038.

## 9. Healthchecks

### 9.1 Use a path that doesn't redirect

Django's `/` often 302-redirects to `/login/` for unauthenticated users. Curl's default doesn't follow redirects, so tests see 302 instead of 200. Either:

- Point healthcheck at `/login/` (or `/accounts/login/` for Bugsink).
- Or pick a well-known public endpoint (`/api/v1/instance` for fediverse apps, `/alive` for Vaultwarden, `/api/healthz` for Forgejo).

### 9.2 Auth-protected roots

If the root is auth-protected (Stirling-PDF 2.x with security profile), use the login page. If even the login page is auth-protected, use a static asset path that's always public (`/static/<something>`, `/favicon.ico`).

## 10. Known Hop3 gaps — check before packaging

If your candidate app has any of these characteristics, expect pain:

| Characteristic | Gap | Mitigation |
|----------------|-----|------------|
| Uses PostgreSQL extensions (bloom, pg_trgm, hstore, vector) | G1 (addon doesn't grant CREATE) | Defer until the addon is fixed, OR have the operator pre-create extensions manually. |
| Needs system-package compile deps at native deploy time | G2 (`[build].packages` not consumed) | Pre-install on the server manually; defer native variant. |
| Full Rust/JVM compile from source in Docker build | G3 (10-min hardcoded build cap) | Use nixpkgs package if available; defer docker variant. |
| Needs Rust toolchain for native deploy | G4 | Defer native variant; use nix or docker. |
| Needs `LD_LIBRARY_PATH` pointing at Nix-store libs under a Nix-built Python venv | G5 | Use hand-crafted nix (not nix-gen) OR defer. |
| Published only on npm, needs pnpm-style layout | G6 | Use docker (which uses raw npm correctly for many); defer nix. |
| Poetry-managed with no PEP-621 | G7 (ADR 039) | Packaging-time `poetry export`; commit the result. |

## 11. Defer pattern

When an app can't be packaged in a given variant:

1. Move the variant to `apps/bad/real-apps-<variant>-bad/<app>/`.
2. Add `DEFERRED.md` with:
   - **Reason** — the specific error and where it comes from.
   - **Working variants (kept)** — which variants did succeed, with a note on why.
   - **Unblocker(s)** — what needs to change (app-side, Hop3-side, or upstream) to revive the deferred variant.
3. Reference any matching server-side gap from this doc so fixing a gap can revive multiple apps at once.

A deferred app is not a failed app — it's an explicit record of scope and work.

## 12. Further reading

- [ADR 039 — Python deploy strategies](./adrs/039-python-deploy-strategies.md): the plan for Poetry / pyproject / uv / requirements precedence.
- [ADR 038 — Multi-service applications](./adrs/038-multi-service-apps.md): the plan for apps with genuinely independent components.
- [ADR 008 — Template-based Nix generation](./adrs/008-nix-builders-2.md) and [Appendix B of TR-01](./reports/TR-01.md#appendix-b--nix-template-reference): the eight templates.
- [`lessons-learned/nix-packaging.md`](./lessons-learned/nix-packaging.md): deep dive on Nix-specific gotchas.
- [`lessons-learned/database-addon-portability.md`](./lessons-learned/database-addon-portability.md): deep dive on PostgreSQL and MySQL connectivity.
