# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/abilian/hop3/compare/0.6.0...HEAD
[0.6.1]: https://github.com/abilian/hop3/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/abilian/hop3/compare/0.5.0...0.6.0
[0.5.0]: https://github.com/abilian/hop3/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/abilian/hop3/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/abilian/hop3/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/abilian/hop3/releases/tag/v0.1.0
