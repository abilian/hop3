# TODO

Engineering tasks captured during day-to-day work live here. Move items out to plans / weeklies / commit messages as they are picked up. The first section runs the other way: work that plans and ADRs have already decided, written out in full because a reference by number tells a reader nothing.

## Next up: five tasks, decided and unstarted

Three of them come from an internal safe-defaults review. Two come from [ADR 050](adrs/050-waf-l7-lewaf.md) and [ADR 055](adrs/055-app-runtime-uid-separation.md). They are written out here because referring to them by number names nothing to anyone outside the review. Checked against the tree on 2026-09-22: none of the five has started.

### 1. An authenticated gate in front of apps

An app is public the moment it deploys. That is right for an application with its own accounts and wrong for the class people actually deploy: scripts with a web page, generated tools, admin dashboards, staging copies. The only access control today is `[waf]`, whose gate keys on named networks. `require = "auth"` is a hard validation error until forward-auth exists ([ADR 050](adrs/050-waf-l7-lewaf.md) §5).

Scoped on 2026-09-22 into two proposed ADRs and three pieces of work, in this order:

1. **Standard roles and control-plane authorization** ([ADR 061](adrs/061-standard-roles-and-rpc-authorization.md)). Prerequisite. Today any account can run any RPC command, so an account created to pass a gate could run `env show` on every app. Four fixed roles (`admin > deployer > viewer > member`), one per account, enforced in the RPC dispatcher and the dashboard, default-deny. Per-app grants are designed in and not built. No custom roles.
2. **Caddy and Traefik green in e2e.** Both exist as plugins and in the e2e image. No test has ever selected them. Parameterise the e2e container by `HOP3_PROXY_TYPE`; fix the two defects that surfaced (the e2e Caddyfile imports `*.caddyfile` while the plugin writes `<app>.caddy`; Traefik routes name a `hop3` certResolver defined nowhere); give both an admin-domain route; refuse `[waf]` on both at deploy, since today they silently ignore it. Teaching the installer to install them is a separate item.
3. **The gate** ([ADR 062](adrs/062-authenticated-access-gate.md)). `[access] require = "auth"`, a minimum `role`, `public-paths`. One `/auth/check` endpoint behind nginx `auth_request`, Caddy `forward_auth` and Traefik `ForwardAuth`; a per-app redirect handshake setting a host-only `__Host-hop3_gate` cookie, because the admin cookie never reaches an app's host; `X-Hop3-User`/`X-Hop3-Role` overwritten by the proxy; fail closed. `[[waf.gate]] require = "auth"` goes away in favour of `[access]`. `new-apps-private` is deferred, with `require = "none"` as its opt-out already.

**Acceptance bar** is ADR 062's eleven-point list, one e2e per proxy. It includes the case that motivates ADR 061: a `member` who passes the gate is refused by every mutating RPC command.

**Size:** L. It unblocks fourteen login-less applications identified in a migration study and three catalog candidates with no sign-in of their own (synapse-admin, Outline, Woodpecker), closes ADR 050's own deferral, and is the largest single unblock in the backlog. Displaced three weeks running.

### 2. No silent skips in the test suites

A skipped test in a standard target is a silent skip, which this project's own rules forbid. Every run of `make test-fast` reports `1 skipped` today. Seven sites:

| Where | Skips on |
|---|---|
| `hop3-server/tests/a_unit/waf/test_compiler_lewaf.py` | `lewaf` absent |
| `hop3-server/tests/b_integration/waf/test_proxy_integration.py` | `lewaf` absent |
| `hop3-server/tests/b_integration/plugins/test_s3_garage_integration.py` | `boto3` absent |
| `hop3-cli/tests/a_unit/core/test_app_scope_matches_server.py` | `hop3-server` not installed |
| `hop3-cli/tests/a_unit/commands/test_fallback_commands.py` | the RPC module absent |
| `hop3-rootd/tests/a_unit/test_exec.py` (×2) | `systemctl` absent |

`lewaf` is the `waf` extra. `make develop` already syncs `--all-packages --all-extras --all-groups`; the `test*` targets do not sync at all, so a venv synced any other way skips silently and reports green.

**Change:** the `make test*` targets sync every extra they test; `importorskip` and tool-absence skips become hard failures behind an explicit `--allow-missing=lewaf,systemctl` the Makefile never passes; a summary check fails the target when anything in the selected layer skipped for a missing dependency.

**Done when** `make test-fast` fails on a venv without `lewaf` with a one-line reason. The opt-out works and prints what it disabled. **Size:** under a day.

### 3. A dependency cooldown

`uv lock --upgrade` will take a version published minutes ago. A freshly-published compromised release is the common shape of a supply-chain attack. There is no `exclude-newer` anywhere in the workspace, so the only defence is that someone notices before the next sync.

**Change:** `[tool.uv] exclude-newer` at a week, refreshed by the lock workflow when it runs, and the same setting in the installer's bundled pins.

**Done when** a lock refresh cannot select a version younger than seven days, documented in the developer guide with the reason. **Size:** under a day.

### 4. Secret scanning before commit

`.pre-commit-config.yaml` runs `detect-private-key`, which catches PEM blocks and nothing else. An API token, a cloud credential or a webhook secret pasted into a test fixture, a note or a recipe passes through untouched. The recipes this project publishes are public the moment they are pushed.

**Change:** a pinned `gitleaks` hook with a repo-local allowlist for the deliberate fixtures, plus one scan over the full history.

**Done when** a commit containing a fabricated but well-formed token is refused locally and in CI. The historical scan comes back clean, or its findings are rotated. **Size:** under a day.

### 5. The Emperor capability experiment

Every native app runs as `hop3`, which is [plan-0.8](plans/plan-0.8.md) headline 1's subject and the platform's largest correctness gap. Before any of it can be built, one open question in [ADR 055](adrs/055-app-runtime-uid-separation.md) needs an answer that only a real box can give.

Switching a process to a *different* unprivileged UID requires `CAP_SETUID` and `CAP_SETGID`, which the `hop3` user does not hold. ADR 055 §4.1 selects a capability-scoped Emperor: `AmbientCapabilities=CAP_SETUID CAP_SETGID` on the unit, plus `CAP_CHOWN` and `CAP_DAC_OVERRIDE` **only if** uWSGI's socket and log chowning need them. Nobody has measured whether that minimal set covers what uWSGI actually does.

**Why it gates everything above it:** if the minimal set is not enough, the fallback is §4.2's root Emperor, which is a step back from [ADR 010](adrs/010-security-and-resilience.md)'s "no root control-plane process" and changes the shape of every increment built on top. The result belongs in the ADR either way.

**Size:** small. It unblocks the shared `hop3-apps` user: ADR 055's own named first increment, which closes the rootd escalation path and the control-plane secret exposure without solving inter-app interference. That increment is what 0.8 should carry; per-app UIDs come behind it.

## Dependency management

- **Pin runtime dependencies.** `hop3-server` (and the other workspace packages) still use loose floors like `litestar[standard]>=2.22.0`. Hop3 is an application. Applications pin their runtime deps to exact versions, with controlled bumps. This avoids two failure modes seen in production: (1) pip's `only-if-needed` upgrade strategy leaving stale transitive deps on the server (e.g. litestar 2.18 satisfying `>=2.18.0` while local code uses 2.22-only APIs), and (2) silent drift between developer machines and the production server.

  Likely shape: `requirements.lock`-style file generated by `uv pip compile` (or `uv lock` with `package = true` flipped), used by the installer's pip step and pinned at PR time.

  Scoped to 0.5 release prep originally and never done; carried as an open box in [`plans/plan-0.7.x.md`](plans/plan-0.7.x.md).

## CLI

- **Add `hop3 validate`.** A local, client-side lint of a project's `hop3.toml`: run the server's schema validation (`ContextSection`, the committed-credential tripwire, field/host-safety checks) on the file at/above the CWD and exit 0/non-zero with no server required, so it can gate CI. Top-level and project-rooted, the dry sibling of `hop3 deploy` (no `--app`; the app comes from `[metadata].id`). Renamed from the obsolete `hop3 config validate` idea, which clashed with the `config`→`env` alias (ADR 036 D17). Original intent: ADR 001 §Consequences, ADR 027 §Developer Experience. (ADR 027 also lists a stale `hop3 config show` / `config export` from the same wishlist. Revisit if those are still wanted.)

  A checker already exists. `hop3check`, shipped from the `letscode-plugins` repo, is the one the packaging skill tells people to run. It implements the same rules by hand. It reports clean on recipes the server then refuses at deploy time. Since the php-fpm migration it also reports `nothing-to-run` on every PHP recipe, which is now the correct shape for one. The drift runs both ways, so whichever side is right on a given rule, two hand-written implementations of one contract will keep disagreeing. Whatever ships here should validate against the published `schema/hop3.toml.schema.json`, so the file holds one implementation.

- **`--` does not survive flag parsing.** `parse_flags` consumes the POSIX end-of-options marker (`_END_OF_FLAGS` in `commands/flags.py`) and records nothing about where it was, so a later pass cannot tell an escaped flag from one of ours: `hop3 apps -- --help` still reads as a request for hop3's own help. The `run` boundary has the same shape and is handled (`app_scope.RunBoundary`, fed by both passes); `--` needs a change to what `parse_flags` returns, which is why it was not folded in with it.

- **`hop3 login --token <token>` puts a secret on argv**, where `ps` can read it for the length of the call. ADR 036 gives `user add`, `user set-password` and `auth get-token` the `KEY=-` / `KEY=@file` / hidden-prompt treatment; the `--token` path never got it. The deployer is a caller (`deployer/deploy.py`, whose own comment at the call notes there is no stdin form to use). Small, and the rewriting machinery already exists in `commands/arguments.py`.

## Testing

- **The Docker e2e target lets two sessions share one container without either knowing.** The target has a fixed container name (`hop3-server-test`) and fixed ports, so a second `pytest packages/hop3-server/tests/c_e2e/` started while one is running tears the container down and re-installs it under the first. Neither session is told. The result is a corrupt failure: each run sees the other's server restarts, addons and database rows.

  Observed 2026-09-11 with two sessions live at once. Seen from inside, every symptom had the same cause. `RemoteDisconnected` / `Connection refused` meant the other session was restarting hop3-server. `Authentication required` (exit 4) and `The server redirected the RPC call to /rpc/` meant a server had restarted under a live client. An nginx reload reported "no fresh worker processes appeared within 15s" because hop3-rootd, which performs that verification, was itself restarted mid-verify. `test_list_and_filter_backups` failed because `hop3 backup list` returned **the other session's app** and none of its own.

  `notes/lessons-learned/deployment-diagnostics.md` already says one e2e session per machine and that a failure seen while another session was active is not evidence. The harness does not enforce it. **Fix shape:** the Docker target should detect that the container is already owned by a live session (a lock file carrying the owning PID, or a label written at start and checked before teardown) and abort with a message naming the owner. A session that steals a running container breaks the "no silent fallback" rule, here in the test harness itself.

- **`--clean` does not clean the named volumes, so a poisoned download cache survives a blank-slate rebuild.** mediawiki failed nine times with `tar: Unexpected EOF`, identically across runs that were supposed to share no state, because `hop3-download-cache` held a 45 MB entry for a 116 MB tarball dating from 2026-08-24. `--clean` replaces the container and leaves the volumes, which is usually what you want and is exactly wrong for a cache. A truncated entry there is indistinguishable from an upstream fault. It is also the one piece of state that makes a failure look reproducible when it is not. mediawiki passes on a remote target, which finally separated the two. **Fix shape:** validate a cache entry on read (size against the recorded `Content-Length`, or a checksum when the recipe gives one) and evict a short file; separately, say in `--clean`'s own output which state it is not clearing.

- **The e2e image build fails intermittently on apt.** `E: Sub-process /usr/bin/dpkg returned an error code (1)` while installing the 25-package catalogue baseline, and `.NET SDK 9 installation failed` alongside it; the run dies in fixture setup before any test. Not disk (host and Docker VM both had >17 GiB free). Seen 2026-09-11, under the same two-session conditions as above, so re-confirm on a quiet machine before chasing it.

## Packaging

- **A GitHub-generated tarball does not hash stably, and the Nix generator pins one anyway.** `Source.as_nix` always emits `pkgs.fetchurl`, so a recipe fetching `https://github.com/<owner>/<repo>/archive/refs/tags/<tag>.tar.gz` pins the bytes of an archive GitHub *generates on request*, and Nix says so during the build: `warning: archives from GitHub revisions should use fetchFromGitHub`. owncast-nixgen failed the 2026-09-12 catalog run exactly this way (`specified: sha256-ID9A…` / `got: sha256-nIsP…`) for a five-year-old tag that had not moved.

  **Three incidents in two weeks, three failure modes, one cause** (2026-09-22): owncast-nixgen's tag tarball was regenerated and its hash moved; mediawiki's download truncated; uptime-kuma's answered `504 Gateway Time-out` six times during the 0.7.5 gate. Every one of them is GitHub generating an archive on demand. Re-hashing repairs an instance. The class stays open: the same tag can move again tomorrow. `fetchFromGitHub` fetches via git and normalises, so its hash is stable. It hashes the *unpacked tree*, so switching the emitter invalidates every recorded hash for a GitHub source and needs a re-hash pass over the affected recipes. **Decision needed**: re-hash the one and carry on, or take the migration. The migration pairs with the nixpkgs pin bump, which wants a one-pass re-record of its own.

- **A recipe can pin its Node version but not its package manager.** `[build].node-version` installs an exact Node into the app's venv; pnpm was whatever the host happened to have. Etherpad's `download.sh` carries three separate workarounds for successive pnpm behaviour changes (`auto-install-peers` moving out of `.npmrc`, dependency build scripts needing `dangerouslyAllowAllBuilds`, and `pnpm ls --no-production` being removed, which is fatal at *startup* because upstream's plugin migration calls it). Each was written blind against whatever pnpm was current that week.

  **The server-wide half is done (2026-09-14):** the installer pins an exact pnpm and reconciles it on every run, so the version stops moving under deployed apps and two servers of the same Hop3 version agree. Two questions remain. An app needing a pnpm other than the server's still has no way to ask for one (the *per-app* pin). The package-manager *selection* question (dispatch from the lockfile) is separate. Both scheduled as sub-items under [`plans/plan-0.8.md`](plans/plan-0.8.md) headline 4; neither is urgent now that the drift is stopped.

  **A third axis, found on 2026-09-21: the Nix path uses neither.** `node-pnpm-install` runs whatever pnpm the recipe's pinned nixpkgs carries (9.15.9 for the one recipe on that template), so the installer's server-wide pin does not reach it and `[build].node-version` says nothing about it. The versions differ in behaviour that matters: pnpm 9's `fetch` compiles native addons while populating the store, 11's does not. Whatever answers the per-app question has to answer it for the Nix builder too, or the two builders will keep resolving the same recipe differently.

## Release tooling

- **`release.py` uploads whatever the tree says.** 0.7.5 went to PyPI with `CHANGES.md` still headed `## [Unreleased]`. Nothing objected. The script already refuses a workspace whose nine package versions disagree, so the place to add the check exists: refuse to upload when the changelog has no section matching the version being released. While there: the tag is still manual (0.7.2 through 0.7.4 each needed remembering, and the footer link list had gone three releases without an entry), and nothing verifies the built artifact came from the commit being tagged.

## Backlog now scheduled in the plans

The "After 0.7" wish-list that used to sit here is scheduled. The plans carry the reasoning. Kept as a one-line index because both plans cite this file as the source.

- **Per-app UID separation (ADR 055):** [`plan-0.8.md`](plans/plan-0.8.md) headline 1, shared `hop3-apps` user first; second increment in [`plan-0.9-plus.md`](plans/plan-0.9-plus.md). (The `audit` branch the old entry named no longer exists.)
- **Alternative backends:** nix+docker, docker without compose, podman, systemd-nspawn/bubblewrap isolation, lightweight VMs: all in `plan-0.9-plus.md`, all behind the isolation ADR that has to be written first.
- **IAM / centrally managed SSO:** `plan-0.9-plus.md`: Canaille evaluation and an OAuth2/OIDC gateway, alongside the MFA deferral in ADR 012.
- **Web analytics for deployed apps**, and **`sslip.io` as a default hostname**: `plan-0.9-plus.md`, smaller items.
- **Threat dashboard for active security management:** waits on the monitoring substrate in `plan-0.8.md`'s second tier (cgroup v2 tracking, metrics collection, `/metrics`).

## (other items as they come up)
