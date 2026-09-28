# Lessons Learned: E2E Test Infrastructure

Building Hop3's cloud-based E2E testing system taught these patterns and pitfalls.

## Suite Filtering Must Be Consistent

When a test runner displays "Tests to run: 10" but actually runs 78, the bug is that filtering was applied during planning but not during execution; the two code paths diverged.

**Corollary:** Don't maintain parallel data structures for the same concept. We had `SUITE_SCAN_PATHS`, `SUITE_RUNNER_TYPES`, and `_PATH_TO_SUITE` all mapping the same directory names, so a renamed directory needed updating in three places. The fix was to pass paths through directly with no mapping layer.

## Treat Suite Names as Paths

Pass the path directly:

```python
# BAD - indirection layer that rots
SUITE_SCAN_PATHS = {"test-apps": "apps/test-apps", ...}

# GOOD - paths are paths
config.suites = ["apps/test-apps-procfile"]
catalog.scan(paths=config.suites)
```

## Auto-Detect Infrastructure Needs

The test runner installs the addons the selected apps *declare*: the operator must not hand-pass `--with mysql`. Each app's `[[addons]].type` surfaces as `TestDefinition.requirements.services`; the runner unions those into the installer's `--with` features and passes them to the deploy. An addon that maps to no installer feature aborts the run with an error, so the operator never hits the opaque "Was the server installed with '--with s3'?" at deploy time.

```python
# catalog/features.py: single source of truth for addon → --with feature
required = required_features_from_tests(tests)   # from each app's [[addons]].type
validate_features(required)                      # loud on an unprovisionable addon
deploy_features = merge_features(explicit_with, required)
```

Explicit `--with` (e.g. builder-level features like `nix`) adds *extra* features on top; it never replaces the derived set.

## Runner Type Inference

Infer the runner type from the path:

```python
# If path contains "demos" → demo runner
# If path contains "tutorials" → tutorial runner
# Everything else → deployment runner
```

## Stop Early on Zero Tests

If the catalog loads 0 tests for the configured suites, fail immediately with a clear error. Don't waste 5 minutes rebuilding the server and deploying Hop3 only to report "0 tests passed":

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

Diagnostics must be collected BEFORE the app is destroyed. The test runner cleans up apps after each test, so any diagnostics collection that runs after cleanup finds empty log directories.

## Timeout Hierarchy

| Level | Default | Purpose |
|-------|---------|---------|
| Per-test deploy timeout | 30 min (flat) | Total deploy + start + verify (`_DEPLOY_TIMEOUT_SECONDS`) |
| App start timeout | 60s (override per app via `[run].start-timeout`) | Health check polling after uWSGI starts |
| Nix build timeout | 30 min | `nix-build --option build-timeout 1800` (`NIX_BUILD_TIMEOUT_SECONDS`) |
| Nix silence timeout | 5 min | `--option build-max-silent-time 300`: the real guard against lock waits / stalled downloads |
| Docker build timeout | 30 min (flat) | `BUILD_TIMEOUT_SECONDS`; applies only to the `docker build` step |
| SSH command timeout | 30s | Individual remote commands |

- **Build/deploy timeouts are a single flat 30 min, not tier-aware.** Per-app tier-driven build timeouts were removed: guessing a build's duration up front was error-prone and created two parallel timeout systems (build tier + test tier). A build that can't finish in 30 minutes is a design smell. Reach for a lighter packaging profile (docker-gen, nixpkgs-wrapper against a pre-built `pkgs.X`); raising the ceiling papers over the problem. `tier` in `[test]` is now only a report label.
- **Per-app `start-timeout` overrides the default 60s.** Apps with slow first-run migrations (Forgejo/Gitea on Postgres, HedgeDoc compile-on-first-run) need explicit overrides in their `hop3.toml`.
- **When a test times out, the error message should say which timeout was hit.** "Deploy timed out after 30 minutes" tells the operator more than "timed out".

## URL Preflighting: Upstream Moves and Asset Renames

Scaffolding a new app involves hardcoding a release URL. Upstreams *do* move:

- **GoToSocial** migrated from `github.com/superseriousbusiness/gotosocial` to `codeberg.org/superseriousbusiness/gotosocial`. The old URL now 404s.
- **Stirling-PDF** jumped from the 0.x line to the 2.x line (`v0.49.3` does not exist; latest is `v2.9.x`). A scaffold pinned at `v0.49.3` 404s.
- **Vaultwarden** ships no prebuilt binaries at all; only Docker images. A Dockerfile pointing at a community static-binary mirror 404'd on first run.

Check URLs with `curl -sIL` before pushing scaffolding to CI. A 15-second check saves a 15-minute test cycle:

```bash
for url in \
  "https://codeberg.org/.../gotosocial_${VER}_linux_amd64.tar.gz" \
  "https://github.com/.../Stirling-PDF.jar" \
  ... ; do
  curl -sIL "$url" | head -1 | grep -q "200 OK" || echo "MISSING: $url"
done
```

When upstream has no prebuilt binary, document the constraint in a per-app `DEFERRED.md` under `apps/bad/`.

## Upstream Behaviour Change Between Major Versions

Stirling-PDF 2.x ships with the `security` Spring profile baked into the JAR at build time. Setting `DOCKER_ENABLE_SECURITY=false` at runtime (which worked on the 0.x line) no longer disables authentication. The Spring Boot log line `The following 1 profile is active: "security"` is the first signal; requests to `/` return HTTP 401.

**Fix in test infrastructure:** for apps where authentication is built in, point health checks at a public endpoint that exists regardless of auth state (Stirling-PDF: `/login`; Vaultwarden: `/alive`; Forgejo: `/api/healthz`; GoToSocial: `/api/v1/instance`). Use the endpoint the upstream project documents as a liveness probe.

**Fix in operator workflow:** when a major upstream version changes authentication defaults, the `[healthcheck].path` in `hop3.toml` is the lever. Record the reason in the weekly note so the next person knows why.

## Service Management Consistency

Docker service management must be consistent across entry points. When `hop3-deploy --docker` uses manual service starts but tests use supervisor, the result is double-starts, in-memory state loss, and "stream not found" errors caused by the divergence.

## Non-UTF-8 Build Output

pip, npm, and other tools may emit non-UTF-8 bytes in their output (progress bars, ANSI codes). Decode with `errors="replace"`:

```python
# BAD - crashes on pip output
result = subprocess.run(cmd, text=True)

# GOOD - handles any encoding
result = subprocess.run(cmd, capture_output=True)
stdout = result.stdout.decode("utf-8", errors="replace")
```

## Testing Upgrades: Own Installer, Fresh Box

Testing that a server upgrades has two requirements, surfaced while building `hop3-test upgrade-chain`.

**Each version must be installed by its own installer.** Driving the *current* installer to install an old version (`--from pypi --version 0.6.0`) is doubly wrong. It pairs the current installer's expectations (today's systemd unit, today's strict "rootd must start" check) with *old* binaries, while the stricter current installer rejects a state that an older, looser installer once shipped as valid. Check each version's tag out into a git worktree and run *that* checkout's `hop3-deploy-server` (`uv run … --local`). Use the stable `--local`/`--git`/`--pypi` source flags, which every release accepts, unlike the newer `--from`.

**The box must be fresh.** Start each chain from a clean slate (a fresh Docker container or a rebuilt cloud VPS), because an old release expects the toolchain/OS state of its era and an existing server carries state that masks migration bugs.

**Watch for a backend that recreates state every deploy.** `DockerDeployBackend.setup()` unconditionally removed and recreated the container, so a second `--docker` deploy was *always* a fresh install. The in-place update path was unreachable, so an "upgrade" test on docker silently tested fresh-install-twice. The fix was to honour `--clean` (reuse a running container when it's absent). If a "passing" e2e can't actually reach the code path it names, the test is a no-op. (Related: the deployer's `systemctl restart` was a silent no-op under supervisor, faking success; service ops must be process-manager-aware.)

**Some releases are not viable baselines.** `hop3-rootd 0.6.0` imports a `__version__` that its `__init__` never defines, in the published wheel *and* the tag source, so it can't start. An upgrade chain excludes such a version. The exclusion is itself a data point about the release's quality.

## A skip is a hole until proven otherwise

**September 2026.** A default `c_e2e` run skipped 18 of 56 tests, one third of the suite, as it had for months. Five were legitimate: remote diagnostics that need a real box and are opt-in by design (ADR 043). The other thirteen were holes wearing a skip label:

- **Ten Nix tests had never run.** The e2e image had no Nix. The `--run-nix` option that promised to provision it was declared in a conftest and read by nothing. The closure-guard test among them, when it finally ran, found the guard silently returning on every static Nix site: a real platform bug, dormant behind a skip whose reason pointed at a flag that did not exist.
- **Two PostgreSQL backup tests carried a stale marker**, "not yet available in E2E tests", while PostgreSQL was installed on every target; their bodies still used the pre-ADR-036 colon spellings, so removing the marker alone would not have made them pass.
- **One integrity test was an empty body** with a skip on it: a to-do disguised as a test, counted in the total.
- **A deploy failure whose message contained ECONNREFUSED was reported as a skip**, a silent skip.

These rules came out of it:

- A skip's reason must name a resource the run cannot provide, on a target we provisioned for real (see "Auto-Detect Infrastructure Needs"). A fixture directory of Nix apps means the target gets `--with nix`.
- A missing prerequisite on a target the harness provisioned is a harness failure, reported under the test's name.
- The April 2026 precedent is the same rule from the other side: the Python toolchain's tests were skipped on macOS because `virtualenv` was not installed there. The fix was `python -m venv`, which removed the dependency for every platform. Before adding a skip, ask what code paths go untested and whether the failure is a platform gap in disguise.

## The sanitized Docker config must keep its contexts

The shared pytest plugin hands every subprocess a `DOCKER_CONFIG` copied from the developer's, minus the credential helpers that would pop a keychain prompt. The copy kept `currentContext: orbstack` without the `contexts/` directory the CLI resolves it through, so every `docker` the tests shelled out to (`hop3-deploy-server`, `docker build`) failed with "context not found", which the deployer summarized as "Docker is not available". The SDK-driven tests in the same session passed, because docker-py ignores contexts. OrbStack, Colima and Docker Desktop all run under a named context. The copy now symlinks `contexts/`. The deployer quotes the CLI's own error in place of the bare verdict.

## Two e2e sessions on one machine wreck each other

The Docker target uses one fixed container name and fixed host ports. It reuses a running container "because `--clean` was not asked for" without checking who started it, then its teardown stops that container. Two concurrent sessions in one afternoon produced a restore test that got connection refused while the other session restarted the server under it, then an install killed with exit 137 by the first session's teardown. Each failure read as an unrelated test bug. Until the target gets per-session names and ports, or a lock, one machine runs one e2e session at a time. A failure that appeared while another session was active is not evidence of anything.

## The image must carry what a real install carries

The e2e image lacked three things, each found by a test that had never run:

- **Nix.** It is baked now through the installer's own `install_nix()`, so the image gets it the way `hop3-install server --with nix` does and the build fails without `nix-build`. A bare Ubuntu image also lacks `xz`, which the Nix installer needs; the installer now provides it as the feature's prerequisite.
- **A key for root, plain.** The `hop3` account's key carries the forced command and `no-port-forwarding`, which forbids the `ssh -L` tunnel the CLI speaks JSON-RPC through. The production shape is the operator's key in root's `authorized_keys`, which is the only shape that lets the transport be tested.
- **The signing key at `/etc/hop3/secret-key`** (ADR 048), the one file both the service and the `su - hop3` CLI read. The image exported the key into supervisor's environment only, so `hop3-server setup` skipped writing it and `admin:ssh-token`, the `hop3 login --ssh` bootstrap, found none.

An image that installs the server by hand drifts from what the installer produces; every such gap shows up as an e2e that cannot run.

## Tests must not write the developer's known_hosts

The tunnel accepts new host keys, so a day of container runs wrote nine `[localhost]:<port>` keys into the maintainer's real `~/.ssh/known_hosts`. A rebuilt image on a reused port would later read as a changed host and fail every tunnel with a scary warning. Giving the CLI subprocess a private `HOME` does nothing: OpenSSH resolves `~` through the passwd entry. The test passes a private `UserKnownHostsFile` through the CLI's `ssh_options` setting, which every ssh the CLI spawns honours.

## Supervisor program names match the service names other tools expect

In the Docker test image, a supervisor program named `redis` while systemd and the health checks looked for `redis-server` meant a service that was up and reported down. Name the program after the service (`redis-server`, `mysql`, `postgresql`), so the process-manager-aware code paths (see "Service Management Consistency" above) find it under either manager.

A rename has the same failure the other way round. On 2026-09-25 the emperor's program went from `uwsgi` to `uwsgi-hop3` in the four supervisor configs. Two scripts that address it by name kept `uwsgi`: the restore script, whose supervisor branch set `UWSGI_SVC=uwsgi`, and the post-install check. The restore then stopped at "uwsgi did not start" after it had replaced the database and the apps tree. The configs were grepped; the callers were not. `test_supervisor_program_names.py` now reads the names the scripts start or check against the programs the configs define.

## An assert on a tuple always passes

`wait_for_http_ready` returned `(ok, message)`. Two calls in the snapshot test wrote `assert wait_for_http_ready(...)`. A non-empty tuple is true, so the test waited two minutes on a `301` to HTTPS, printed "Timeout", and went on: neither of its "the app serves its page" checks had verified anything since the proxies started redirecting plain HTTP by default. A readiness helper now fails the test itself (`pytest.fail`, naming the last answer it saw) and returns nothing, so there is no value to misread. When a helper reports failure through its return value, a truthiness check at the call site is the bug waiting.

## Test configuration differs from production defaults, explicitly

System tests failed because the server defaulted to `certbot`, which a test domain cannot satisfy. Safe defaults for a test run (self-signed certificates, offline-capable options) differ from production's, so the switch is explicit and documented.

## A harness that runs a tool by name runs whatever PATH has

The upgrade-chain test installs an old release by running that release's own deployer with `uv run` inside a git worktree of its tag. The deployer was renamed at 0.7.0, from `hop3-deploy` to `hop3-deploy-server`. The harness asked every worktree for the new name. `uv run` does not treat a script the environment lacks as an error: it falls through to `PATH`, where the developer's active virtualenv had the current deployer. The "fresh 0.6.2 install" therefore installed 0.7.3, and the "upgrade" reinstalled 0.7.3 over itself. The chain passed because it checked the schema and that a version was readable; it never checked that the version was the one the hop claimed.

Two repairs. The harness reads the script name from the checkout's own `pyproject.toml`, syncs the checkout's environment first and refuses to run when the script is not in it. Every hop also checks that the installed version equals the version the checkout carries; that assertion would have failed on the first run. As a general rule, when a test drives a tool from another version by name, resolve the name from that version's metadata and assert the version that ran. A name lookup that can silently pick a neighbour is a no-op wearing a pass.

## A unit test with ambient credentials is a live command

The dev server was found wiped, twice in one morning. The first suspect was the assistant session that had been running Docker e2e tests all day. Hetzner's action log settled it. It showed nine `rebuild_server` actions that day, each three to nine seconds after a launch of the **unit** suite of hop3-installer, and the same pattern on every `make test-fast` back to mid-August. The test was `test_docker_and_a_provider_are_refused`: it passed `--docker --provider hetzner` to the deployer's target logic to prove the combination is refused. It is refused, but the code provisioned first and validated second: with no `--server-id`, the provisioning took the id from `HETZNER_SERVER_ID` and the token from the shell. The test then passed on the rejection, every time, over a rebuilt server.

Three defences went in and each would have been enough. The deployer validates every target word before it acts on any of them (a destructive step never precedes argument validation, the same rule as `app destroy` prompting for the wrong app). The root conftest strips the cloud credentials for every pytest session, as it already stripped the dev-host variables, so no test layer can hold a token that rebuilds a machine. The rebuild itself then refuses a server that does not carry a `hop3-throwaway=true` label, set once by the operator, so an id that reaches the code from a config file or the environment cannot name a box anyone uses.

Two rules for the next reader: the environment a test inherits is part of its inputs, since a credential in it turns "exercise the refusal path" into "run the command"; the guard belongs in the conftest, not in each test's memory. When a machine is found reset, the first record to open is the provider's action log, which dates every rebuild to the second; the correlation with launch times found the test in minutes where reading code for a mechanism had not.


## Two runners of one check are two implementations of one contract

An app's `check.py` runs twice in a catalog run: at the end of the deploy, from the server, and again from hop3-testing, which uploads it and executes it on the box. Each built the check's environment its own way, and they disagreed twice.
The first time was the port. The harness passed 80 on the reasoning that loopback is the app's nginx and the `Host` header picks the vhost. That held until the check started building `https://` URLs unconditionally, after which it sent a TLS ClientHello to a plain-HTTP port and reported `[SSL: WRONG_VERSION_NUMBER]` as *the first step of the check failing*: "the admin credential signs in", pointing at the credential, the app and the recipe, none of which were involved.

The second was the credential, which had been wrong the whole time. The harness read the encrypted credential store and exported `HOP3_ADMIN_*` alone, so `Check.has_probe` was false for every app it ever tested and every check fell back silently to the operator's credential: a weaker claim, made without saying so. Piwigo turned weaker into wrong: on an empty gallery it serves an onboarding interstitial to a guest *or an administrator* on every page, and to an ordinary user it does not. The probe is an ordinary user. The deploy's smoke test passed and the harness's run of the same file failed one minute apart, and the failure named the application.

Which credentials a check may see is now one function on the server that both callers read. The rule is that when two places invoke the same artifact, the invocation itself is the contract. Put it in one place and have the second ask for it, because the drift is not detectable from either side. The tell that it has happened is a green result and a red result from the same file in the same minute; when you see that, stop looking at the app.
