# Lessons Learned: Nix Packaging for Hop3

Non-obvious facts and hard-won knowledge from building 40+ Nix app packages for Hop3.

## String Escaping in Nix `''` Strings

### The Core Rule

In Nix `''...''` (indented) strings, `${...}` is Nix interpolation. To produce a literal `${VAR}` in the output, write `''${VAR}`.

```nix
installPhase = ''
  # Nix interpolation (resolved at eval time):
  echo ${pkgs.nodejs}/bin/node

  # Literal shell variable (resolved at runtime):
  echo ''${PORT}
'';
```

This applies everywhere inside `''` strings, including inside heredocs, shell scripts, and config files. The `<< 'EOF'` single-quote trick that prevents shell expansion does NOT prevent Nix interpolation.

### The Regex Rule

Nix variables are lowercase (`${pkgs}`, `${nodejs}`, `${version}`, `$out`). Shell environment variables are UPPERCASE (`${PORT}`, `${PGHOST}`, `${BIND_ADDRESS}`). Use this to auto-detect unescaped shell vars:

```python
# Find unescaped shell vars in Nix '' strings
pattern = r"(?<!'')(\$\{[A-Z][A-Z0-9_]*(?::-[^}]*)?\})"
```

### Common Mistakes

```nix
# WRONG - Nix tries to interpolate PORT (undefined variable error)
cat > config << EOF
port = ${PORT}
EOF

# WRONG - backslash escape doesn't work in '' strings
port = \${PORT}

# RIGHT - double-single-quote escape
port = ''${PORT}

# RIGHT - including default values
port = ''${PORT:-8080}
host = ''${BIND_ADDRESS:-0.0.0.0}
```

### Wrapper Script Pattern

For wrapper scripts that need runtime variable expansion, use a placeholder + `sed` approach to avoid escaping hell:

```nix
cat > $out/bin/start << 'WRAPPER'
#!/bin/sh
exec BINDIR/myapp --port $PORT
WRAPPER
sed -i "s|BINDIR|$out/bin|g" $out/bin/start
chmod +x $out/bin/start
```

This keeps the wrapper as a single-quoted heredoc (no expansion at all), then patches in Nix store paths with `sed`. Shell variables like `$PORT` pass through unchanged.

## Binary Cache and Build Times

### The Channel Problem

> **Note (Hop3 0.7+):** the installer and code generator no longer use nix-channel; nixpkgs is pinned in-tree (`packages/hop3-server/.../gen/templates/base.py`, nixos-24.11). The channel steps below are kept for historical reference and for operators on pre-0.7 versions.

Nix's binary cache (`cache.nixos.org`) only caches packages from official release channels. If the server uses a rolling channel (`nixpkgs-unstable`) or no channel at all, packages like `nodejs_22` may not be cached and Nix builds them from source (~30 minutes for Node.js).

**Fix:** Pin the channel to a stable release during installation:

```bash
nix-channel --add https://nixos.org/channels/nixos-24.11 nixpkgs
nix-channel --update
```

### How to Tell if a Package is Cached

In the nix-build output:
- `copying path '...' from 'https://cache.nixos.org'` = fetched from cache (fast)
- `building '/nix/store/...-nodejs-22.22.2.drv'` = building from source (slow)

If you see `building` for a common package (Node.js, Python, GCC), the channel is wrong.

### Version Pinning

`pkgs.nodejs` resolves to the latest Node.js in the channel (may be v24, uncached). Use explicit LTS versions: `pkgs.nodejs_22` (LTS, always cached in stable channels).

## Sandbox and Network Access

### The `__noChroot` Problem

Apps that run `npm install`, `composer install`, `pip install`, or `lein uberjar` during build need network access. Nix's default sandbox blocks this.

```nix
app = pkgs.stdenv.mkDerivation {
  __noChroot = true;  # Allow network access during build
  # ...
};
```

But `__noChroot` only works when the Nix daemon is configured with `sandbox = relaxed` in `/etc/nix/nix.conf`. The default (`sandbox = true`) ignores `__noChroot` and the build silently fails or hangs.

**Fix in the installer:**

```
# /etc/nix/nix.conf
sandbox = relaxed
```

Then restart `nix-daemon`.

### SSL Certificates in Builds

Network-accessing builds may fail with SSL errors because the Nix sandbox doesn't provide CA certificates. Set these in the build phase:

```nix
buildPhase = ''
  export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
  # For Rust/Cargo:
  export CARGO_HTTP_CAINFO=$SSL_CERT_FILE
  export CARGO_HOME=$TMPDIR/.cargo
  # For Java/Maven:
  export _JAVA_OPTIONS="-Duser.home=$TMPDIR"
'';
```

### HOME Directory

The Nix build user's HOME is `/var/empty` (read-only) or `/homeless-shelter` (doesn't exist). Tools that write to `~/.npm`, `~/.m2`, `~/.cargo`, `~/.lein` will fail.

**Always set:**

```nix
buildPhase = ''
  export HOME=$TMPDIR
'';
```

## Build Hangs and Stale Locks

### The Lock Wait Problem

If a previous `nix-build` was killed mid-build (Ctrl+C, deploy timeout, process kill), it may leave a lock on the Nix store path. A new `nix-build` for the same derivation will **silently wait for the lock forever** with zero output.

**Symptoms:** `nix-build` process running at 0% CPU, no stderr output, no network activity.

**Fix:** Kill stale processes before building:

```bash
pgrep -f "nix-build.*hop3.nix" | xargs kill -9
```

### Build Timeouts

Always set build timeouts to avoid infinite waits:

```bash
nix-build hop3.nix -A package --no-out-link \
  --option build-timeout 600 \
  --option build-max-silent-time 300
```

- `build-timeout`: Total wall-clock time limit (kills the build)
- `build-max-silent-time`: Kills if no output for this many seconds (detects lock waits and stalled downloads)

## Runtime Configuration

### The PORT Problem

Every Hop3 app must listen on `$PORT` (assigned dynamically). Most apps need a config file that includes the port. Since Nix store paths are read-only, the wrapper script must generate config at runtime:

```bash
#!/bin/sh
# Generate config with runtime PORT
cat > settings.json << EOF
{ "port": ${PORT:-8080} }
EOF
exec /nix/store/.../bin/myapp --config settings.json
```

The config file is written to the working directory (`/home/hop3/apps/<app>/src/`), which is writable.

### Working Directory

uWSGI daemons run in the app's `src/` directory. Relative paths in wrapper scripts resolve there. Nix store paths are absolute. Mix them intentionally:

- Config files: relative (written at runtime to writable `src/`)
- Binaries: absolute (`$out/bin/...` from Nix store)
- Data directories: relative (`mkdir -p data`)

### The `runtime.json` Contract

The Nix build must produce `$out/hop3/runtime.json`:

```json
{
  "workers": { "web": "/nix/store/.../bin/start" },
  "env": { "KEY": "value" },
  "path": ["/nix/store/.../bin"]
}
```

The `web` worker command must listen on `$BIND_ADDRESS:$PORT`. For static sites, give `workers` a single `static` entry instead: `"workers": { "static": "/nix/store/.../public" }` (the builder treats a lone `static` worker as a static-site artifact).

## Platform Differences

### macOS vs Linux

- `pkgs.matrix-synapse` is Linux-only in nixpkgs (fails eval on macOS)
- Node.js may segfault during `configure` on macOS ARM64 with certain nixpkgs versions
- `patchelf` warnings ("cannot find section '.dynamic'") are normal for statically-linked Go binaries on Linux - harmless

### The `dontFixup` Escape Hatch

npm/pnpm create symlinks between `node_modules/.pnpm/` entries. After `npm install`, dev dependencies may reference each other via broken symlinks (the target package was pruned in `--production` mode). Nix's `fixupPhase` checks for broken symlinks and fails the build.

```nix
# Skip broken symlink check for Node.js apps
dontFixup = true;
```

This is safe - the broken symlinks are dev dependencies that aren't used at runtime.

## Package Manager Specifics

### npm / Node.js

- `npm install --production --legacy-peer-deps` for production deps only
- Always set `export HOME=$TMPDIR` (npm writes to `~/.npm`)
- Large apps (CryptPad, HedgeDoc) take 5-10 minutes for `npm install`
- Prefer pre-built release tarballs when available (HedgeDoc publishes them)

### Composer / PHP

- Include `pkgs.php82` with the right extensions for each app
- `composer install --no-dev --no-interaction` for production
- Set `COMPOSER_HOME=$TMPDIR/.composer`

### pip / Python

- Use `pkgs.python3.withPackages` for apps in nixpkgs
- Use `python -m venv $out/venv && $out/venv/bin/pip install ...` for apps NOT in nixpkgs
- Use `psycopg2-binary` instead of `psycopg2` (avoids needing `pg_config`)

### Maven / Leiningen (Java/Clojure)

- Set `_JAVA_OPTIONS="-Duser.home=$TMPDIR"` so Maven writes to a writable dir
- `LEIN_HOME=$TMPDIR/.lein` for Leiningen

### Go

- `pkgs.buildGoModule` with `vendorHash` for source builds
- Pre-built binaries via `fetchurl` for releases (faster, simpler)
- `patchelf` warnings about `.dynamic` section are harmless (Go binaries are static)

## Common Runtime Failure Patterns

Nix builds succeed but apps crash at startup. These are the most frequent causes.

### Wrong Port

The app listens on its default port (e.g., Gitea on 3000, Grafana on 3000) instead of `$PORT` assigned by Hop3. The wrapper script must pass `$PORT` to the app's config or command line.

**Symptom:** Build succeeds, "Deployment successful", then "App failed to start within 60.0s timeout". The app IS running but on the wrong port.

**Fix:** Generate config at runtime in the wrapper script, passing `$PORT` — see "The PORT Problem" above for the pattern.

### Working Directory vs Nix Store

Nix store paths are **read-only**. Apps that try to write config files, create data directories, or modify their own directory will crash.

- **Config files:** Write to the working directory (`src/`), not to `$out`
- **Data directories:** Create relative dirs (`mkdir -p data`), they land in `src/`
- **Gitea's `custom/conf/`:** Must be relative to working dir, not in the Nix store

**Symptom:** Gitea shows `WorkPath: /nix/store/.../bin` and `ConfigFile: /nix/store/.../bin/custom/conf/app.ini` - the config is in the read-only store.

**Fix:** The wrapper must `cd` to a writable directory before creating configs:

```bash
#!/bin/sh
cd "$PWD"  # Working dir set by uWSGI (writable src/)
mkdir -p custom/conf data
cat > custom/conf/app.ini << EOF
...
EOF
exec /nix/store/.../bin/gitea web
```

### Missing Entry Points

Pre-built release tarballs may have different directory layouts than source archives. HedgeDoc's release tarball doesn't have `app.js` at the root - it has a different entry point.

**Symptom:** `Cannot find module '/nix/store/.../app/app.js'`

**Fix:** Check the actual release tarball contents (`tar tzf` or `unzip -l`) and adjust the entry point in the wrapper.

### Permission Denied on System Paths

Apps like Radicale default to system paths (`/var/lib/radicale`) that don't exist or aren't writable by the hop3 user.

**Symptom:** `Permission denied: '/var/lib/radicale'`

**Fix:** Override storage paths via environment variables or config to use relative/writable paths:

```bash
#!/bin/sh
mkdir -p collections
exec radicale --storage-filesystem-folder ./collections
```

### Static Files and Relative Paths

Apps like Listmonk expect `static/`, `i18n/`, `config.toml.sample` in the working directory. When running from a Nix wrapper, the working directory is `src/`, not the Nix store.

**Fix:** Either symlink or copy static assets from the Nix store to the working directory:

```bash
#!/bin/sh
# Symlink static assets from Nix store to writable cwd
ln -sf /nix/store/.../static ./static 2>/dev/null
ln -sf /nix/store/.../i18n ./i18n 2>/dev/null
exec /nix/store/.../bin/listmonk
```

### nixpkgs Sometimes Ships Only the Binary

Some nixpkgs derivations package only the compiled binary and omit the runtime assets the binary expects. A concrete example: **WriteFreely 0.16.0** in nixpkgs installs only `$out/bin/writefreely`; the `templates/`, `pages/`, and `static/` directories the binary needs are absent. The binary searches `$exe_dir/../share/writefreely/...` by default, finds nothing, and fails at startup with `share/writefreely/templates: no such file or directory`.

Rather than reinvent packaging, combine the nixpkgs binary with the upstream release tarball for its asset directories:

```nix
let
  writefreely = pkgs.writefreely;  # binary only
  wfRelease = pkgs.fetchurl {
    url = "https://github.com/writefreely/writefreely/releases/download/v${version}/writefreely_${version}_linux_amd64.tar.gz";
    sha256 = "…";
  };

  app = pkgs.stdenv.mkDerivation {
    ...
    installPhase = ''
      mkdir -p $out/share/writefreely
      tar xzf ${wfRelease} -C $out/share/writefreely --strip-components=1
      # wrapper points templates_parent_dir at $out/share/writefreely
      ...
      exec ${writefreely}/bin/writefreely
    '';
  };
```

This is a **hybrid**: Tier-1 binary (reproducible compile by nixpkgs), Tier-3 assets (sha256-pinned upstream tarball). Document the mix in the hop3.nix so the reproducibility posture is explicit. Consider upstreaming a nixpkgs fix; until it lands, the hybrid is the pragmatic path.

### Multi-Package Template Limitations

The `nixpkgs-wrapper` template (ADR 008) wires exactly one nixpkgs package: the one declared in `[nix].nixpkgs-package`. Applications whose nixpkgs derivation ships assets in a sibling package or a `passthru` attribute need to reference a second Nix store path. Known cases:

| App | Second artefact | What it needs |
|-----|-----------------|---------------|
| Vaultwarden | `vaultwarden.passthru.webvault` | `WEB_VAULT_FOLDER` set to that package's store path |
| GoToSocial | `$out/share/gotosocial/web` sibling to the binary | `GTS_WEB_ASSET_BASE_DIR` set to a Nix-interpolated path |
| WriteFreely | Upstream tarball for `templates/pages/static` (see above) | A hook to fetch a companion archive |

The extension for the first two has landed: `[nix].let-extra` binds extra packages into the generated `let` block (e.g. `webvault = pkgs.vaultwarden.webvault`), and `[nix].env-exports-raw` exports env vars whose values are Nix-interpolated at build time (bypassing `nix_escape`, so `${webvault}` resolves to the store path instead of being treated as a shell ref). `apps/real-apps-nix-gen/keycloak` is the reference user: `let-extra` binds `jdk = "pkgs.zulu21"`, then `env-exports-raw` exports `JAVA_HOME = "${jdk}"`. Vaultwarden and GoToSocial are now expressible via the template but not yet migrated — the hand-crafted `real-apps-nix/<app>/hop3.nix` variant is still current. WriteFreely stays deferred: the template has no hook for fetching a companion archive.

Future Outline, PeerTube, Funkwhale, and Chatwoot will hit the same pattern (S3 attachments, web assets, multiple worker binaries), and may need the companion-archive hook that WriteFreely still lacks.

### Deprecated Commands

Some apps deprecate their binary names between versions (Grafana: `grafana-server` → `grafana server`).

**Symptom:** `exec: "grafana": executable file not found in $PATH`

**Fix:** Check the current version's documentation for the correct command, and ensure PATH includes the Nix store bin directory.

## Testing

### Local Build Validation

```bash
# Build all nix apps
./apps/build-nix-apps.py test-apps-nix real-apps-nix --fix-hashes

# Single app with debug output
./apps/build-nix-apps.py real-apps-nix --app gitea --debug

# Auto-fix SHA256 placeholder hashes
./apps/build-nix-apps.py real-apps-nix --fix-hashes
```

The `--fix-hashes` flag detects `got: sha256-...` in nix-build errors, replaces the placeholder in `hop3.nix`, and retries. Handles multiple `fetchurl` calls (up to 3 retries).

### E2E Testing

```bash
# Test nix apps on a real server (suite paths are positional; --from local is the default)
hop3-test run apps/test-apps-nix
hop3-test run apps/real-apps-nix
```

The test runner auto-enables the `nix` feature when any suite path contains "nix", so `nix-build` is available on the server.

### Hash Placeholders

New apps start with placeholder hashes. Nix fails on first build and reports the correct hash. Use `--fix-hashes` to automate, or manually:

```nix
# Placeholder (fails on first build)
sha256 = "0000000000000000000000000000000000000000000000000000";

# After first build attempt, Nix reports:
#   got: sha256-abc123...=
# Replace with the reported hash
sha256 = "sha256-abc123...=";
```
