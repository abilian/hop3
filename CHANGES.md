# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Addon passwords are no longer briefly world-readable while being written.** Hop3 keeps each addon's password in a file only its own account can read. It got there the long way: the file was created with the usual permissions, the password written into it, and only then locked down — so for the length of every write, and again on every rotation, any account on the server could read it. It is now created locked down. The same change fixes a way to lose a password outright: writing the file emptied it first, so a write that failed part-way left no password at all while the database went on expecting the old one, and the app could not reconnect. Affects PostgreSQL, MySQL, Redis and email addons.
- **Two Redis addons can no longer be handed the same database.** Each addon gets one of Redis's fifteen numbered databases, but the number was picked and then written down three Redis round trips later, so two `hop3 addon redis create` calls close together could both take the same one and silently share each other's keys. The number is now claimed and recorded in a single step. A create that fails afterwards gives its number back rather than holding it forever, and when all fifteen really are in use the error says which addon holds each.
- **Deploys no longer build all at once.** Each deploy used to get its own thread the moment it was asked for, so ten `hop3 deploy` calls became ten simultaneous builds competing for the CPU, memory and disk of the server that is also running your apps. Builds now run two at a time (`MAX_CONCURRENT_BUILDS`) and the rest queue, saying so in their own output and starting on their own. Past 32 waiting (`MAX_WAITING_BUILDS`) a deploy is refused with a message rather than queued.
- **`hop3 app create <repo_url>` now checks the URL and bounds the clone.** The URL went to `git clone` as it arrived, and a URL is not an inert string to git: `ext::sh -c …` runs its argument, `file:///…` reads any path the server can, and a value starting with `-` is an option rather than an address. Hop3 now accepts `https://`, `http://`, `ssh://`, `git://` and the `git@host:user/repo.git` form, and refuses the rest by name. The clone itself is shallow, single-branch, and stops at 10 minutes or 2 GiB, so a repository chosen by one account can no longer fill the disk and take every app on the host down with it. A clone that fails or is stopped leaves nothing behind — including the app row, which a failed create used to keep.

### Fixed

- **The terminal UI showed made-up logs and made-up system metrics.** Opening an app's logs in `hop3-tui` displayed eight invented lines — including `[ERROR] Failed to connect to redis` for an app that was fine — and added another invented line every few seconds so the pane looked live. It never asked the server for anything, and pressing `d` saved those invented lines to a file. It now shows your app's actual logs, and says plainly when there are none, when no app is selected, or when the server could not be reached. The system screen was the same story: CPU 42%, memory 63% and disk 81% were fixed numbers dressed up as live readings, the host was always `hop3.dev` running `v0.5.0`, and the service list always showed nginx, supervisor, PostgreSQL and Redis as running whatever their real state. Those panels now say the server has not reported a value, which is true, until the reporting is built.
- **A failed host-key scan in `hop3-test` said nothing.** Adding a server's SSH key discarded the error, so a scan that timed out looked the same as one that never ran. It now says which host it could not read and why.
- **A signing key too short to sign with is now refused.** `HOP3_SECRET_KEY` shorter than 32 bytes weakens every token the server issues (RFC 7518 §3.2). PyJWT warned and signed anyway, into a log nobody reads. Hop3 now stops with the length it found, the command to generate a good key, and the three places it looks — plus the warning that replacing it signs everyone out.
- **`APP_START_TIMEOUT` now does something.** The reconciler was constructed without it and kept its hardcoded 60 seconds, so an operator raising the setting changed nothing and a slow-starting app could be marked failed while it was still coming up.
- **Forgejo's licence is `GPL-3.0-or-later`, not `MIT`.** Forgejo relicensed at v9.0 and we package v14; the recipe still carried the pre-v9 value. Mattermost stays `MIT`, which is right for the compiled binary Mattermost, Inc. publishes and is now documented in the recipe so it does not get "corrected" to AGPL-3.0.

## [0.7.1] - 2026/08/02

### Security

Affects every release up to and including 0.7.0. **If your hop3-server is reachable from an untrusted network, upgrade.** Nothing to reconfigure and no credential to rotate, but weak account passwords are worth changing: until now they could be guessed far faster than intended.

- **Password guessing over JSON-RPC was not rate limited.** The web login form has been capped at 5 attempts per IP per minute since 0.5, but `hop3 auth get-token` checks the same credentials and applied no limit, so an attacker could guess ~100x faster by choosing that path. Both now draw on one shared budget.
- **Login failures revealed which accounts exist.** A disabled account answered differently from a wrong password, and an unknown username answered faster than a real one. All three failures now return one identical response in the same time.
- **Signing in over plain HTTP looped instead of failing.** The session cookie is `Secure`, so a browser with no TLS discarded it and the login bounced back to the login page forever, with no error anywhere. It now refuses up front and says why. Local development over HTTP still works with `HOP3_DEBUG=true`.
- **Signing out was a link, so another site could sign you out.** `GET /auth/logout` is now a form POST. Minor by itself, but it was the only state-changing GET, and "every mutation is a POST" is what lets Hop3 ship without CSRF tokens.

Details, and the remaining open items, in `notes/security/`.

One behaviour that looks like a bug and is not: a magic link is spent the moment it is presented, even if the sign-in then fails because the account was deleted or disabled. A link that has been used cannot be replayed, whatever happened next. The one case where the link is *not* spent is a redemption that could never have worked for a reason you can fix — over plain HTTP, above, Hop3 refuses before touching the token, so the link still works once you reach the server over HTTPS.

### Fixed

- **Bugsink's Nix recipe runs its background worker.** The hand-written recipe deployed the web process alone, so the app signed in and then failed on any path that queues work: its "snappea" queue lives in a second database that was never migrated. Configuration and both migrations now run before any worker starts, and the queue worker is declared alongside the web one. The other two Bugsink variants were unaffected.

## [0.7.0] - 2026/07/31

### Changed

- **Consistent command-line names**: the developer deploy tool is now `hop3-deploy-server` (renamed from `hop3-deploy`), part of a pass to give every Hop3 tool one consistent set of flags and verbs.
- **Failed deploys show the real cause**: `hop3 deploy` now surfaces the actual error line once — not a repeated, buried backtrace — with a working pointer to the full log (`hop3 app logs --app <app> --build`).

### Added

- **Content-aware health checks**: set `[healthcheck].contains = "..."` and a deploy is only reported healthy when your app actually serves its own page — a bare `200` can be a placeholder or an error page.
- **Server-level email transport** *(experimental)*: set your SMTP submission credentials once with `hop3 server email set … --from-domain example.com`, and per-app email addons created without their own `--smtp-*` inherit them — no credentials repeated per app. An app can still override with its own provider, and rotating the server transport propagates to every inheriting app.
- **Unified email backend selection** *(experimental)*: `hop3 server email backend <relay|catch|direct>` names the backend every declaring app inherits — `relay` (a provider or corporate smarthost, also spelled `server email set`), `catch` (a dev sink that captures mail and never sends it), and `direct` (below).
- **Direct / self-hosted email backend** *(experimental)*: `hop3 server email backend direct --from-domain example.com` turns the box into its own MTA — Postfix delivers to recipients' MX and opendkim signs outbound mail, with no third party. Hop3 generates the DKIM keypair and prints the exact SPF/DKIM/DMARC records to publish (plus the PTR reminder), runs an SPF/DKIM/DMARC pre-flight, and probes outbound port 25 — never claiming "ready" over unpublished DNS or a blocked egress. Needs `--with email` (Postfix + opendkim).
- **Loopback email relay** *(experimental)*: selecting the relay backend now configures a queuing Postfix null-client on `127.0.0.1:25` (via hop3-rootd), and an app that attaches an inheriting email addon is injected `SMTP_HOST=127.0.0.1` — it sends over SMTP to the local relay, which forwards to the provider, so the provider credential never enters an app's environment and the backend is swappable without re-touching apps. Install Postfix with `hop3-install server --with email` (included in `--with all`).
- **Email provider profiles + DKIM auto-verify** *(experimental)*: `hop3 server email set --provider <name>` fills the SMTP host/port for a known provider (`--list-providers`: Resend, Postmark, Brevo, Mailgun/Mailgun-EU, Scaleway TEM — EU-hosted ones flagged). The deliverability pre-flight now also **verifies DKIM** once its selector is known (`--dkim-selector`, or automatically for Resend), instead of only SPF/DMARC.
- **Operator email alerts** *(experimental)*: `hop3 server email notifications on` opts in to being emailed (via the active email backend) when things break — TLS certificate-renewal failures (a cert that stops renewing reaches you before it expires) and **failed deploys** (best-effort, never masking the failure itself). `status` reports whether the channel is actually deliverable, and `test` sends a test message.
- **Safe app upgrades with automatic rollback**: `hop3 app upgrade --app <app>` snapshots the app, redeploys it (rebuilding and running its migrations), verifies it comes back healthy, and — if the build, a migration, or the health check fails — automatically restores the pre-upgrade snapshot instead of leaving you on a half-upgraded app. `hop3 app rollback --app <app>` restores a backup on demand (the most recent by default, `--to <backup-id>` for a specific one).
- **Install apps from the catalog, from the dashboard or the CLI**: 0.6 could browse the signed catalog; 0.7 installs and deploys from it. Twenty apps ship in the official catalog — BookStack, Bugsink, Dolibarr, Easy!Appointments, Forgejo, Gitea, Invoice Ninja, Isso, Kanboard, Keycloak, LimeSurvey, Matomo, Mattermost, Miniflux, Nextcloud, Paheko, Radicale, Uptime Kuma, Vikunja and WordPress — each with an admin account created for you at install time.
- **Every app is verified by signing in, not by returning a page**: each catalog app ships a smoke test that logs in through the app's own authentication with the credential Hop3 generated, and confirms a wrong password is refused. It runs at the end of every deploy (dashboard included), and on demand with `hop3 app check --app <app>`. A `200` from an app that nobody can log into no longer counts as working.
- **`[probe]` — a Hop3-owned account for verification**: an app can declare a non-privileged account whose password Hop3 owns and rotates, so its smoke test keeps working after you change the admin password. Apps that shouldn't have one can leave it out.
- **`hop3 scaffold`**: writes a starter `hop3.toml` for the project in the current directory, with a `#:schema` line so your editor completes and validates the file as you type.
- **Published `hop3.toml` JSON Schema**: at `https://hop3.cloud/schema/hop3.toml.json`, generated from the server's own validation models, so an editor with a TOML language server flags a typo as you type instead of at deploy time.
- **Every bundled app is verified under Nix too.** The two Nix build strategies are now held to the same sign-in bar as the native one: 16 of 16 hand-written recipes and 18 of 19 template-generated ones sign in and refuse a wrong password on a recorded run. Easy!Appointments is the exception — it builds its login form in JavaScript, which neither check can drive.
- **`hop3-deploy-server --provider hetzner --image <image>`**: rebuilds the target server from scratch before deploying, matching `hop3-test`. One command for a genuinely pristine box.

### Fixed

- **A failed server upgrade can no longer report success**: after installing the new code and migrating, the deployer now confirms hop3-server actually came back up before reporting the upgrade complete. If it didn't, the deploy fails loudly with the exact command to revert to the previous release — and a reminder that a forward-migrated schema may also need a pre-upgrade database backup — instead of leaving a silently dead server behind a "complete" message. The restart also picks the right mechanism for the target (systemd or supervisor), so it can't silently keep serving old code.
- **Admin-domain and TLS setup fail loud on a broken nginx reload**: configuring the server's admin domain or its certificate during a deploy now stops with a clear error when nginx can't be reloaded, instead of warning and carrying on — so a "complete" deploy never hides a domain that nginx never actually picked up.
- **Nix apps survive garbage collection**: a running Nix app no longer loses its files to a `nix` garbage-collect — new installs pin auto-GC off and rebuilds keep the previous version rooted — and if anything is ever missing the deploy fails fast with a clear message instead of a slow timeout. Apps that need a newer package set can pin their own nixpkgs revision.
- **`hop3 app restart` checks the Nix closure too**: the check above ran on deploy and start but not on restart, because a restart relaunches the worker from its existing config without going through the start path. A restart against a reclaimed closure therefore came up and died into a health-check timeout with nothing pointing at the cause. It now aborts with the same message naming the missing store path.
- **A fresh install no longer serves a stale configuration**: the installer now restarts hop3-server once its configuration file is written, so a first-time install picks up its operator email, database credentials and admin domain immediately. Previously, on a brand-new server the service started *before* that file existed and cached the empty values — so every app using the built-in admin account failed to deploy with "this server has no operator email", even though the setting was correct on disk. Redeploys were unaffected, which is what made it a fresh-install-only bug.
- **Build failures inside your Dockerfile are reported right away, not retried as phantom registry errors**: a step that fails in your own build (for example a truncated download surfacing as "tar: Error is not recoverable") is now surfaced immediately instead of being mistaken for a transient container-registry outage and retried three times. Genuine registry blips are still retried.
- **Apps are served over HTTPS by default**: plain HTTP now redirects. Apps that set `Secure` cookies — most of them — were unloggable over the HTTP vhost, because the browser correctly refused to send the session cookie back, and the login silently looped.
- **PHP's built-in server gets more than one worker**: it is single-threaded, so any app that makes a request to itself while installing — Nextcloud's installer does — deadlocked against its own only worker and never finished.
- **A failed install can be retried**: installing an app from the catalog recorded it before deploying, so if the deploy failed, every retry was refused with "already exists" — leaving an app you could neither use nor reinstall. A second install now resumes one whose deploy never completed.
- **`[build].build` runs in every language**: the setting was read and then ignored by seven of the twelve toolchains, so a project's declared build command silently never ran.
- **`--clean` reclaims addon databases**: a clean reinstall wiped Hop3's records but left the databases behind, so the next install found a populated database and adopted it. It now stops the apps, drops what it tracks, and sweeps databases it has lost track of. MySQL also refuses to adopt a populated database it holds no credentials for, instead of silently taking it over.
- **`hop3 app credentials` no longer shows a password for an account that was never created**: when an app's own bootstrap failed, the generated credential was still presented as if it worked. The failure is now named, and a bootstrap error includes the failing command's output instead of only an exit status.
- **`--app` works on `app check`, `app upgrade` and `app rollback`**: the three commands documented the flag and then rejected it.
- **Addon teardown reports what it could not remove** instead of leaving storage behind quietly.
- **More bundled apps deploy and verify correctly**, from packaging and content-check fixes across several apps.
- **Authentication hardening**: remediated the findings from the June 2026 auth audit.
- **DNS**: fixed some server-side DNS resolution issues.

### Security

These are defects in Hop3's own bundled application recipes, all found by the sign-in check described above and none visible to a deploy that returned HTTP 200. Anyone who deployed the affected Nix variants should redeploy.

- **Radicale served without authentication.** The Nix recipes set the calendar server's auth type from a variable that defaulted to `none` and was never set, so every calendar and address book was readable by anyone who asked. Authentication is now declared in the recipe where no environment can switch it off, and the config is rewritten on every start so a deployment that once ran open does not stay open.
- **Isso's moderation dashboard was served disabled.** Its config carried no administrator section, so `/admin/` never asked for a password. It is now enabled against the generated credential, comment moderation is on, and the app refuses to start without the credential rather than serving the dashboard open.
- **Published default passwords in three apps, under both Nix strategies.** Miniflux, Keycloak and LimeSurvey shipped literal credentials (`changeme`, `password123`), so the deployed instance had an administrator whose password is in this repository while the operator held a generated one that did not work. All six recipes now refuse to start unless Hop3's generated credential is injected.
- **Gitea and Forgejo deployed with open registration** under both Nix strategies, because the setting that disables it lived in a shell script only the native recipe carried — so the first visitor to a fresh forge could register an account.
- **Signing keys rotated on every restart.** The Gitea and Forgejo Nix recipes minted `SECRET_KEY`, `INTERNAL_TOKEN` and `JWT_SECRET` inside a config file rewritten at each start, which invalidates every session and makes 2FA secrets and stored credentials undecryptable. They are now generated once and re-injected unchanged.

## [0.6.2] - 2026-06-26

### Changed

- **The deploy host doubles as the admin domain**: `hop3-deploy --host h.example.com` now serves the Web UI at `https://h.example.com/` when no `--admin-domain` is given. IPs, `localhost`, or Docker targets keep the previous behavior (UI on port 8000).
- **Follow-up hints remember your selectors**: when a command suggests a next step, the CLI renders it with the `--context` / `--app` you typed. Copy-paste now stays on the right target.
- **Usage strings show `--app` as optional**: the app-scoped flag is now `[--app <app>]`, reflecting that the app is normally resolved implicitly.
- **`hop3 app env` removed**: the hidden duplicate of `hop3 env show --sources` is gone.

### Fixed

- **Bare host no longer serves the wrong app**: the control-plane vhost claims `default_server`, so requests with no matching Host reach the Web UI, not a random app. Distro default sites are cleaned up on redeploy.
- **Admin-domain TLS fixed on rootd hosts**: `acme.sh` reloaded nginx as the `hop3` user (blocked by rootd). The deploy now reloads nginx itself and checks for the cert on disk instead of trusting acme.sh's exit code.
- **Self-signed cert upgraded to Let's Encrypt**: a previously-issued self-signed certificate is now replaced when `--acme-email` is added. When self-signed, the deploy tells you why.
- **Server knows its own admin domain**: `hop3-deploy` records `ADMIN_DOMAIN` so magic links and `addon expose` URLs use the right hostname.
- **Dashboard login survives redeploys**: web auth now uses a signed JWT cookie instead of a server-side session, matching the CLI credential. Stays valid across restarts.
- **`HOP3_UNSAFE` production override now works**: the auth guards re-read the env instead of caching an import-time snapshot.
- **Unknown CLI flags fail loud**: the RPC argument parser rejects unrecognized tokens with an error instead of silently dropping them. This also fixed `hop3 backup list --app X` ignoring the filter.
- **`hop3 context use` recognizes global contexts**: instead of "not found", it now points to the right mechanism (`hop3 login --context` or `--context` per command).

## [0.6.1] - 2026-06-24

A consolidation release: simpler context model, pinned nixpkgs for reproducible builds, experimental email addon, and a round of fixes.

### Added

- **Experimental email / SMTP relay addon**: provision an outbound relay as an addon, with environment injection following ADR 051 conventions.
- **Config-injection conventions (ADR 051)**: documented how Hop3 wires addon settings into apps; vikunja and monica now honor injected SMTP.
- **`hop3 auth get-token`**: print the current bearer token. `login` and `auth login` unified; `login --web` fixed.

### Changed

- **One context model (BREAKING, ADR 042)**: credentialed servers and project contexts are consolidated. A *context* is a deploy environment declared in `hop3.toml` under `[contexts.<name>]`. Credentials become invisible plumbing in `~/.config/hop3-cli/credentials.toml`; `config.toml` is secret-free. Existing connections are migrated on first run.
- **Reproducible Nix builds**: nixpkgs is now pinned to a specific commit across all recipes. Builds resolve the same toolchain regardless of the host's `nix-channel`.

### Fixed

- **`--context` resolution fails loud**: the CLI shows the full resolution chain instead of silently falling back.
- **Nix GC root retained across rebuilds**: prevents a running worker's closure from being garbage-collected mid-deploy.
- **Elixir runtime env**: `MIX_HOME` no longer clobbered.
- **Discourse**: assets precompiled at build time so the container binds `$PORT` within the health-check window.
- **Kanboard**: schema migrations finish before the readiness probe runs.
- **Addon `create`**: edge case that could report success when the addon wasn't created.
- **Nix flake builds and NixOS CI**: repaired and re-enabled.
- **App packaging**: archived Focalboard dropped; shlink/piwigo validations corrected; bugsink start-timeout raised; native Monica marked expects-failure.
- **Test Lab reporting**: completed-with-failures runs are recorded as *failed*; variant and demo name show correctly; quieter scheduler logs; queue details expanded.

### Security

- **`hop3.toml` holds zero secrets**: a committed-credential tripwire rejects secret-shaped values in committed env. Per-environment secrets are set server-side with `hop3 env set`.

## [0.6.0] - 2026-06-22

Per-app resource limits and volumes, richer addon commands, a signed app catalog, and a published ADR collection.

### Added

- **Resource limits (ADR 046)**: declare memory and CPU caps under `[limits]`, enforced for native and containerized apps. Server can set defaults and ceilings.
- **Volumes (ADR 046)**: persistent bind mounts and tmpfs, provisioned through rootd behind a default-deny allow-list.
- **Addon management**: `hop3 addon <type>` gains `query`, `clone`, `export`, `import`, `restore`, `flush`, `exists`, `promote`, `endpoint`, `expose`, and `tunnel`.
- **App catalog (ADR 049)**: load a signed catalog of installable apps; browse from the dashboard.
- **Configurable backup contents**: `[backup].paths` / `[backup].exclude`.
- **Static sites without a Procfile**: serve from `[build].static-dir`.
- **Fixed-port registry (ADR 045)**: non-HTTP apps claim a stable host port from `hop3.toml`, optionally with source CIDRs.
- **Generated env secrets**: `SECRET_KEY = { generate = "urlsafe" }` under `[env]`.

### Changed

- **`--app` flag only (ADR 036)**: deprecated positional argument removed.
- **Python 3.12+ required (BREAKING)**.
- **Command renames** (aliases kept): `launch` → `create`, `backup info` → `backup show`, `addon ps` → `addon activity`, `domains` → `domain`, `env migrate` → `app migrate`.
- **Single source for server secret (ADR 048)**.
- **Idempotent redeploys**: re-running the installer preserves existing secrets and operator config.

### Fixed

- **Redeploy no longer kills the git push**: the reaper leaves `git receive-pack` alone.
- **Stable app port across redeploys**.
- **Smaller deploy uploads**: build-output directories excluded.
- **Redis health check** fixed when no password is set.
- **Let's Encrypt email** forwarded to the installer on redeploy.

### Security

- **Hardened catalog dashboard**: untrusted catalog content sanitized.
- **Unavailable banner** when the catalog source is down.

### Documentation

- Full ADR collection published on the docs site.
- Guides, CLI reference, and tutorials reviewed and corrected.
- Testing walkthrough series and "Migrating from X" guides published.

## [0.5.0] - 2026-06-08

### Highlights

- **CLI server/context model (ADR 042)**: credentialed servers separated from per-project deploy contexts.
- **Unified testing architecture (ADR 043)**: one speed-tier taxonomy, shared diagnostic bundle.
- **Nightly Test Lab (ADR 044)**: web dashboard for run history and regressions.
- **Privileged-operations daemon (ADR 041)**: narrow root-boundary daemon replaces broad sudoers.
- **Security hardening**: RPC boundary, authentication, credential storage.

### Added

- **CLI ergonomics overhaul (ADR 036)**: a redesigned command surface — space-separated command names (`hop3 env set`), an implicit current app, a sticky working context (`hop3 use`), command aliases, did-you-mean suggestions, categorized help with an example on every command, scriptable confirmations and non-interactive flags, and secret inputs from a file or stdin.
- **Nix integration**: hermetic, reproducible builds from a `hop3.nix` file, a starter set of Nix-based application packages, and installer support for Nix on every supported distribution.
- **Computed environment variables**: interpolate values in `hop3.toml` with `${VAR}`, resolved after addon variables are injected, so platform variables can be mapped to the names an app expects.
- **WSGI auto-discovery**: Python web entry points are detected automatically when no worker is configured.
- **Servers and project contexts (ADR 042)**: manage credentialed hosts with `hop3 server` and per-project deploy targets with `hop3 context`.
- **Deploy preview and project-mismatch guard (ADR 042)**: `hop3 deploy` shows the resolved plan and confirms before acting; destructive commands refuse to run when the resolved app contradicts the current project.
- **Shared failure diagnosis (ADR 043)**: every deploy-and-verify path collects one diagnostic bundle on failure and classifies it into a one-line cause, closing the silent-502 gap.
- **Nightly dashboard `hop3-testlab` (ADR 044)**: run history, live progress, the regressions diff, and trends.
- **Privileged-operations daemon `rootd` (ADR 041)**: the operations that need root run through a small, audited daemon instead of sudoers.
- **App hostnames**: declare and manage an app's domains from `hop3.toml` and the CLI.
- **Cross-instance backup migration (ADR 024)**: restore a backup onto a different Hop3 server.
- **CLI ergonomics overhaul (ADR 036)**: space-separated commands, implicit app, sticky context, aliases, did-you-mean suggestions, categorized help, scriptable confirmations, secret inputs.
- **Nix integration**: hermetic builds from `hop3.nix`, starter app packages, Nix installer support.
- **Computed env variables**: `${VAR}` interpolation in `hop3.toml`.
- **WSGI auto-discovery**: detect Python entry points automatically.
- **Servers and project contexts (ADR 042)**: `hop3 server`, `hop3 context`.
- **Deploy preview and project-mismatch guard**.
- **Shared failure diagnosis**: every deploy collects a diagnostic bundle, classifying failures.
- **Nightly dashboard `hop3-testlab`**.
- **Privileged-operations daemon `rootd` (ADR 041)**.
- **App hostnames**: declare and manage domains from `hop3.toml` and CLI.
- **Cross-instance backup migration**.

### Changed

- **Command syntax (BREAKING, ADR 036)**: multi-word commands use spaces, not colons (`hop3 env set`, not `hop3 config:set`); the old colon form prints a migration hint.
- **Command names (BREAKING, ADR 036)**: user management moved under `user`, addon commands to the singular `addon`, and a few verbs were normalized.
- **Exit codes (ADR 036)**: the exit-code scheme was reorganized; scripts that branch on specific codes may need updating.
- **Server vs context vocabulary (BREAKING, ADR 042)**: the old global "context" is now a *server*, and "context" means a project deploy target; existing config is migrated on first run.
- **Testing layers (ADR 043)**: the test suite is three layers selected by speed tier; a plain `pytest` run never starts Docker.
- **More reliable deploys**: clearer messages about already-set env vars, IPv4 addon hosts to avoid IPv6 resolution issues, and assorted build and worker-precedence fixes.
- **Safer upgrades**: pending database migrations run on upgrade, and an existing virtualenv is no longer replaced.
- **Containerized app database access**: addons are reachable from apps on any private Docker network.
- **Space-separated commands (BREAKING, ADR 036)**: `hop3 config set` not `hop3 config:set`.
- **Exit codes reorganized (ADR 036)**.
- **Server vs context vocabulary (BREAKING, ADR 042)**: existing config migrated on first run.
- **Testing layers (ADR 043)**: plain `pytest` never starts Docker.
- **Addons reachable from Docker apps** on any private network.

### Fixed

- Faster deploy log streaming.
- Addon connection fixes (MySQL, host resolution).
- `--why` now diagnostic-only; app name resolves from `hop3.toml`.

### Security

- Untrusted RPC arguments validated.
- Auth hardening; admin-takeover path closed.
- Addon credentials re-encrypted with automatic migration.
- Privilege boundary moved from sudoers to rootd (ADR 041).

## [0.4.0] - 2026-03-27

Major release: Hop3 becomes a complete self-hosted PaaS.

### Highlights

- Client-server architecture (CLI on laptop, server on host)
- Ten language toolchains (Python, Node, Ruby, Go, Rust, PHP, Java, Clojure, Elixir) + static sites
- Database addons (PostgreSQL, MySQL, Redis) with encrypted credentials
- Automatic Let's Encrypt SSL with auto-renewal
- Multi-distribution: Ubuntu, Debian, Fedora, Rocky Linux, AlmaLinux
- Config validation with helpful error messages
- Security audit with command-injection fixes
- Comprehensive test suite

### Security

- Command injection fixes across OS plugins and utilities.
- Session lifetime reduced to 24 hours.
- JWT secrets enforced to 32-byte minimum.
- Authentication bypass in middleware closed.

## [0.3.0] - 2025-03-24

- First stable version for simple Python WSGI and static sites.
- Core internal API for app lifecycles.
- Stabilized installation for production-like environments.

## [0.2.0] - 2024-06-28

- Modernized Nginx setup, actor-based framework, major documentation and test improvements.

## [0.1.0] - 2024-04-11

Initial release: core architecture, app builders, addon support, SQLAlchemy models, first test runner.

[Unreleased]: https://github.com/abilian/hop3/compare/0.7.1...HEAD
[0.7.1]: https://github.com/abilian/hop3/compare/0.7.0...0.7.1
[0.7.0]: https://github.com/abilian/hop3/compare/0.6.2...0.7.0
[0.6.2]: https://github.com/abilian/hop3/compare/0.6.0...0.6.2
[0.6.1]: https://github.com/abilian/hop3/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/abilian/hop3/compare/0.5.0...0.6.0
[0.5.0]: https://github.com/abilian/hop3/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/abilian/hop3/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/abilian/hop3/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/abilian/hop3/releases/tag/v0.1.0
