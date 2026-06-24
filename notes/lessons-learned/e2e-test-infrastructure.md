# Lessons Learned: E2E Test Infrastructure

Patterns and pitfalls from building Hop3's cloud-based E2E testing system.

## Suite Filtering Must Be Consistent

When a test runner displays "Tests to run: 10" but actually runs 78, the bug is that filtering was applied during planning but not during execution. Both paths must use the same logic.

**Corollary:** Don't maintain parallel data structures for the same concept. We had `SUITE_SCAN_PATHS`, `SUITE_RUNNER_TYPES`, and `_PATH_TO_SUITE` all mapping the same directory names — when directories were renamed, 3+ places needed updating. The fix: pass paths through directly with no mapping layer.

## Treat Suite Names as Paths

Instead of mapping `"test-apps"` → `"apps/test-apps-procfile"` and back, just pass the path directly:

```python
# BAD — indirection layer that rots
SUITE_SCAN_PATHS = {"test-apps": "apps/test-apps", ...}

# GOOD — paths are paths
config.suites = ["apps/test-apps-procfile"]
catalog.scan(paths=config.suites)
```

## Auto-Detect Infrastructure Needs

When a user runs `--apps apps/real-apps-nix`, the test runner should automatically enable the `nix` feature in the deployment. Don't make users pass `--features nix` separately:

```python
if any("nix" in suite for suite in config.suites):
    deploy_config.features.append("nix")
```

Same principle for Docker apps needing `docker`, apps needing `mysql` or `postgresql`, etc.

## Runner Type Inference

Instead of maintaining a map of suite names to runner types, infer from the path:

```python
# If path contains "demos" → demo runner
# If path contains "tutorials" → tutorial runner
# Everything else → deployment runner
```

## Stop Early on Zero Tests

If the catalog loads 0 tests for the configured suites, fail immediately with a clear error — don't waste 5 minutes rebuilding the server and deploying Hop3 only to report "0 tests passed":

```python
if len(catalog) == 0:
    print(f"Error: No tests found for suites: {suites}")
    return
```

## Test Ordering Matters

Tests should run in alphabetical order by default. Without explicit sorting, the order depends on filesystem iteration order, which varies across platforms and runs. Alphabetical order makes failure reports reproducible and easier to compare.

```python
return sorted(tests, key=lambda t: t.name)
```

Random order (`--random` flag) is useful for finding order-dependent bugs but should be opt-in.

## The `test.toml` Enum Trap

When test.toml uses `tier = "heavy"` but the Tier enum only defines `fast`, `medium`, `slow`, `very-slow`, the test silently fails to load with "Failed to load app: 'heavy' is not a valid Tier". This looks like a file format error but is actually a schema mismatch.

**Lesson:** Validate test.toml against the schema and list valid values in the error message:

```
Failed to load: 'heavy' is not a valid Tier.
Valid values: fast, medium, slow, very-slow
```

## Diagnostic File Collection

### Use Basenames for Directory Names

Test names like `apps/real-apps-nix/cryptpad` contain slashes. Using them as directory names creates deeply nested empty directories. Always extract the basename:

```python
base_name = Path(test_name).name  # "cryptpad"
```

### Find Apps with Timestamp Suffixes

Deployed apps are named `<basename>-<timestamp>` (e.g., `cryptpad-1774987859`). Search with a glob:

```bash
find /home/hop3/apps -maxdepth 1 -name 'cryptpad*' -type d
```

### Collect Before Cleanup

Diagnostics must be collected BEFORE the app is destroyed. The test runner cleans up apps after each test — if diagnostics collection runs after cleanup, the logs are gone.

## Timeout Hierarchy

| Level | Default | Purpose |
|-------|---------|---------|
| Per-test deploy timeout | **tier-aware**: fast=5m / medium=10m / slow=20m / very-slow=30m | Total deploy + start + verify; driven by `tier` in `test.toml` |
| App start timeout | 60s (override per app via `[run].start-timeout`) | Health check polling after uWSGI starts |
| Nix build timeout | 10 min | `nix-build --option build-timeout 600` |
| Nix silence timeout | 5 min | `--option build-max-silent-time 300` |
| Docker build timeout | **10 min (hardcoded; not tier-aware)** | Separate from the deploy timeout — applies only to the `docker build` step |
| SSH command timeout | 30s | Individual remote commands |

Three subtleties worth knowing:

- **The deploy timeout is tier-aware; the Docker-build timeout is not.** An app whose Docker image takes longer than 10 minutes to build (typically: compiling Rust or a JVM toolchain from source inside the Dockerfile) will fail even if its `tier = "very-slow"`. Making the Docker-build timeout tier-aware is tracked as a post-0.6 improvement in ADR 033.
- **Per-app `start-timeout` overrides the default 60s.** Apps with slow first-run migrations (Forgejo/Gitea on Postgres, HedgeDoc compile-on-first-run) need explicit overrides in their `hop3.toml`.
- **When a test times out, the error message should say which timeout was hit.** "Deploy timed out after 20 minutes" tells the operator more than "timed out".

## URL Preflighting: Upstream Moves and Asset Renames

Scaffolding a new app involves hardcoding a release URL. Upstreams *do* move:

- **GoToSocial** migrated from `github.com/superseriousbusiness/gotosocial` to `codeberg.org/superseriousbusiness/gotosocial`. The old URL now 404s.
- **Stirling-PDF** jumped from the 0.x line to the 2.x line (`v0.49.3` does not exist; latest is `v2.9.x`). A scaffold pinned at `v0.49.3` 404s.
- **Vaultwarden** ships no prebuilt binaries at all; only Docker images. A Dockerfile pointing at a community static-binary mirror 404'd on first run.

Preflight URLs with `curl -sIL` before pushing scaffolding to CI. A 15-second check saves a 15-minute test cycle:

```bash
for url in \
  "https://codeberg.org/.../gotosocial_${VER}_linux_amd64.tar.gz" \
  "https://github.com/.../Stirling-PDF.jar" \
  ... ; do
  curl -sIL "$url" | head -1 | grep -q "200 OK" || echo "MISSING: $url"
done
```

When upstream has no prebuilt binary, document the constraint in a per-app `DEFERRED.md` under `apps/bad/` rather than silently skipping.

## Upstream Behaviour Change Between Major Versions

Stirling-PDF 2.x ships with the `security` Spring profile baked into the JAR at build time. Setting `DOCKER_ENABLE_SECURITY=false` at runtime — which worked on the 0.x line — no longer disables authentication. The Spring Boot log line `The following 1 profile is active: "security"` is the first signal; requests to `/` return HTTP 401.

**Fix in test infrastructure:** for apps where authentication is built in, point health checks at a public endpoint that exists regardless of auth state (Stirling-PDF: `/login`; Vaultwarden: `/alive`; Forgejo: `/api/healthz`; GoToSocial: `/api/v1/instance`). Use the endpoint the upstream project documents as a liveness probe, not the root path.

**Fix in operator workflow:** when a major upstream version changes authentication defaults, the `[healthcheck].path` in `hop3.toml` is the lever. Record the reason in the weekly note so the next person knows why.

## Service Management Consistency

Docker service management must be consistent across entry points. When `hop3-deploy --docker` uses manual service starts but tests use supervisor, the result is double-starts, in-memory state loss, and "stream not found" errors.

**Rule:** Pick one service management approach and use it everywhere.

## Non-UTF-8 Build Output

pip, npm, and other tools may emit non-UTF-8 bytes in their output (progress bars, ANSI codes). Always decode with `errors="replace"`:

```python
# BAD — crashes on pip output
result = subprocess.run(cmd, text=True)

# GOOD — handles any encoding
result = subprocess.run(cmd, capture_output=True)
stdout = result.stdout.decode("utf-8", errors="replace")
```
