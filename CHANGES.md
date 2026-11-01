# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release below is a summary. The full notes, with what to do on upgrade and why each change was needed, are in the release notes for [0.8](https://hop3.cloud/reference/release-notes/0.8/), [0.7](https://hop3.cloud/reference/release-notes/0.7/), [0.6](https://hop3.cloud/reference/release-notes/0.6/) and [0.5](https://hop3.cloud/reference/release-notes/0.5/).

## [0.8.1] - Unreleased

See the [full notes](https://hop3.cloud/reference/release-notes/0.8/#081).

### Fixed

- **hop3-rootd runs from a root-owned venv in `/opt/hop3-rootd`**, and the installer and `hop3-deploy-server` no longer act as root on files the hop3 user controls. The next install or update moves an existing server over.
- **`HOP3_UNSAFE` in `hop3-server.toml` meets the same safety check as the environment variable.**
- **Upgrading with the install one-liner migrates the database.** A server upgraded to 0.8.0 that way is migrated by the next install.
- **A deploy over HTTPS accepts an archive up to 200 MB.**
- **`hop3 app restart` applies a changed environment.**
- **Destroy and `addon destroy` report what they could not remove.** Destroy no longer removes another app's containers; `addon destroy` no longer reports success when the database server is down.
- **Two addons can no longer share a database or a user**, and two PostgreSQL addons can be created at the same time.
- **The dashboard streams live logs as text, fixes the WCAG 2.2 AA failures an audit found, and no longer freezes the server.**
- **Apps with more than one language build.** An app with both a `Dockerfile` and a `hop3.nix` must name its builder.
- **`hop3 login` trusts a certificate you pinned with `hop3 settings set ssl_cert`.**

### Changed

- **`hop3 login --token` reads the token from stdin, a file or a hidden prompt.** The literal form still works, with a warning.
- **The JSON-RPC response includes a `Hop3-RPC-Protocol` header.** A client that sends another protocol version is refused.
- **Apps may be named `admin`, `api`, `app`, `apps`, `dashboard`, `hop3`, `static` or `www`.**

## [0.8.0] - 2026-10-27

See the [full notes](https://hop3.cloud/reference/release-notes/0.8/#080). Read [Upgrading from 0.7](https://hop3.cloud/reference/release-notes/0.8/#upgrading-from-07) first: each native app needs one redeploy, each project checkout one `hop3 context use <name>`.

### Highlights

- **Accounts have roles.** `[access]` puts an app behind a Hop3 sign-in (ADR 061, ADR 062).
- **An app keeps its state across a redeploy.** `[[volumes]]` gains a `scratch` type. Each app has a `HOME` and `TMPDIR` of its own.
- **Caddy and Traefik serve apps**, PHP apps included where the proxy can.
- **A Nix-built PHP app runs under php-fpm**, as a native one does since 0.7.5.
- **The catalog has a versioned address. Each entry names the server it needs.**
- **The installer aborts on a failure** with the command's output.
- **Each checkout names the server it deploys to. Commands print where they go** (ADR 042). A protected server accepts changes only when named on the command line.

### Security

- **App code can no longer reach root through hop3-rootd.**
- **An app's environment and database passwords are off the command line**, where other users on the server could read them.
- **A PHP app's hidden files are no longer served.**
- **A gated app's nginx include file cannot forward around the gate.**
- **A server installs no dependency released in the last seven days.**
- **The test harness no longer creates admin accounts or replaces a server's mail setup.** Remove the `hop3-harness` and `tutorial-runner` accounts from any server `hop3-test` ran against.

## [0.7.5] - 2026-09-21

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#075).

- **PHP apps are served by php-fpm behind nginx, and need no start command.** `[build].document-root` sets the web root.
- **`hop3 help` and `hop3 <command> --help` reach the server again.**
- **A worker command must be a single program.**
- **Nix apps built with `node-pnpm-install`, or from their own directory, build again.**

## [0.7.4] - 2026-09-15

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#074).

### Security

- **A test run can no longer rebuild a cloud server.**

### Added

- **The CLI talks HTTPS by default; SSH is for bootstrap and rescue.** Every target the CLI can reach has a name, and `hop3 login` takes it positionally.
- **`[proxy]` sets the reverse proxy's limits per app.**
- **Garage replaces MinIO behind the S3 addon.**
- **`hop3-backup-server` snapshots a whole server, and `hop3-restore-server` puts it back.**

### Fixed

- **Deploys are no longer refused at random for an nginx reload that worked.** A proxy configuration the server rejects is rolled back.
- **`hop3 run` streams its output and no longer times out.**
- **An in-place server upgrade upgrades rootd and the CLI too.**
- **A deploy no longer claims the CLI's `default` context.**

## [0.7.3] - 2026-09-08

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#073).

### Added

- **`hop3 app shell` opens a shell inside a deployed app.**
- **`hop3 env set` keeps secrets off the command line.**
- **`[admin].verify` and `[probe].verify` prove a bootstrap account exists.**
- **`hop3-tui` is rewritten on turbodesk and reaches `ssh://` servers.**
- **PHP applications get a production runtime.**

### Changed

- **PostgreSQL, Caddy and Traefik are reloaded through rootd.**
- **JSON-RPC errors have JSON-RPC codes.**

### Security

- **Stopping or destroying an app can no longer remove another app's worker configuration.**
- **A symlink inside an app's tree can no longer point a backup or a volume outside it.**
- **Login failures are indistinguishable, including in time.**
- **The PostgreSQL addon refuses a name that would derive a reserved role.**

### Fixed

- **Two apps can no longer share a name.**
- **`hop3 app destroy <name>` no longer asks you to confirm a different app.**
- **`--with nix` either installs Nix or aborts the install.**

## [0.7.2] - 2026-08-30

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#072).

### Added

- **The application gallery is live at `apps.hop3.cloud`**, with one entry per application, graded by how well the catalog knows it.

### Security

- **Addon passwords are no longer briefly world-readable.**
- **Two Redis addons can no longer be handed the same database.**
- **Deploys no longer all build at once.**
- **`hop3 app create <repo_url>` checks the URL and bounds the clone.**

### Fixed

- **A deploy can no longer report success for an app with a dead background worker.**
- **`APP_START_TIMEOUT` now does something.**
- **The terminal UI no longer shows invented logs and metrics.**
- **A signing key too short to sign with is refused.**

## [0.7.1] - 2026-08-02

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#071).

### Security

- **Password guessing over JSON-RPC is rate limited.**
- **Login failures no longer reveal which accounts exist.**
- **Signing in over plain HTTP no longer loops.**
- **Signing out is a form, so another site can no longer sign you out.**

## [0.7.0] - 2026-07-31

See the [full notes](https://hop3.cloud/reference/release-notes/0.7/#070).

### Changed

- **Command-line names are consistent.** A failed deploy shows the real cause.

### Added

- **Safe app upgrades with automatic rollback.**
- **Install apps from the catalog**, from the dashboard or the CLI.
- **Every app is verified by signing in**, with `[probe]`, a Hop3-owned account, and content-aware health checks.
- **Email**: a server-level transport, a choice of backends (direct, relay, provider profiles with DKIM) and operator alerts.
- **`hop3 scaffold`** and a published `hop3.toml` JSON Schema.

### Fixed

- **A failed server upgrade can no longer report success.**
- **Nix garbage collection no longer removes a running app's files.**
- **Apps are served over HTTPS by default.**

### Security

- **Bundled recipes:** Radicale was served without authentication, Isso's moderation dashboard was served disabled, three apps shipped published default passwords, and Gitea and Forgejo deployed with open registration.
- **Signing keys no longer rotate on every restart.**

## [0.6.2] - 2026-06-26

See the [full notes](https://hop3.cloud/reference/release-notes/0.6/#062).

- **The deploy host doubles as the admin domain**, and a bare host no longer serves the wrong app.
- **Admin-domain TLS works on rootd hosts.** A self-signed certificate is replaced by Let's Encrypt once `--acme-email` is given.
- **Dashboard sign-in lasts across redeploys.**
- **Unknown CLI flags fail loud.**
- **`hop3 app env` is removed**; use `hop3 env show --sources`.

## [0.6.1] - 2026-06-24

See the [full notes](https://hop3.cloud/reference/release-notes/0.6/#061).

- **One context model (BREAKING, ADR 042)**: a context is a deploy environment declared in `hop3.toml` under `[contexts.<name>]`.
- **nixpkgs is pinned** across all recipes, so Nix builds are reproducible.
- **An experimental email relay addon**, with the config-injection conventions of ADR 051.
- **`hop3 auth get-token`** prints the current bearer token.
- **`hop3.toml` holds no secrets**: secret-shaped values in committed env are refused.

## [0.6.0] - 2026-06-22

See the [full notes](https://hop3.cloud/reference/release-notes/0.6/#060).

- **Resource limits and volumes (ADR 046)**: `[limits]` caps memory and CPU; volumes are provisioned through rootd.
- **A signed app catalog (ADR 049)**, browsable from the dashboard.
- **`hop3 addon <type>` gains `query`, `clone`, `export`, `import`, `restore` and more.**
- **Static sites without a Procfile**, a fixed-port registry (ADR 045) and generated env secrets.
- **Python 3.12+ is required (BREAKING).** The app is given with `--app` only (ADR 036).
- **Redeploys are idempotent**: re-running the installer keeps existing secrets and operator config.

## [0.5.0] - 2026-06-08

See the [full notes](https://hop3.cloud/reference/release-notes/0.5/#050).

### Highlights

- **CLI server/context model (ADR 042)**: credentialed servers separated from per-project deploy contexts.
- **Unified testing architecture (ADR 043)**: one speed-tier taxonomy, shared diagnostic bundle.
- **Nightly Test Lab (ADR 044)**: web dashboard for run history and regressions.
- **Privileged-operations daemon (ADR 041)**: narrow root-boundary daemon replaces broad sudoers.
- **Security hardening**: RPC boundary, authentication, credential storage.

### Added

- **CLI ergonomics overhaul (ADR 036)**: space-separated commands, implicit app, sticky context, aliases, did-you-mean suggestions, categorized help, scriptable confirmations, secret inputs.
- **Nix integration**: hermetic builds from `hop3.nix`, starter app packages, Nix installer support.
- **Computed env variables**: `${VAR}` interpolation in `hop3.toml`.
- **WSGI auto-discovery**: detect Python entry points automatically.
- **App hostnames**: declare and manage domains from `hop3.toml` and CLI.
- **Cross-instance backup migration**.

### Changed

- **Space-separated commands (BREAKING, ADR 036)**: `hop3 config set` not `hop3 config:set`.
- **Exit codes reorganized (ADR 036)**.
- **Server vs context vocabulary (BREAKING, ADR 042)**: existing config migrated on first run.
- **Addons reachable from Docker apps** on any private network.

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

The initial release covers the core architecture, app builders, addon support, SQLAlchemy models and the first test runner.

[Unreleased]: https://github.com/abilian/hop3/compare/0.8.0...HEAD
[0.8.0]: https://github.com/abilian/hop3/compare/0.7.5...0.8.0
[0.7.5]: https://github.com/abilian/hop3/compare/0.7.4...0.7.5
[0.7.4]: https://github.com/abilian/hop3/compare/0.7.3...0.7.4
[0.7.3]: https://github.com/abilian/hop3/compare/0.7.2...0.7.3
[0.7.2]: https://github.com/abilian/hop3/compare/0.7.1...0.7.2
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
