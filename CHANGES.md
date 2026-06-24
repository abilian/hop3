# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **One context model (BREAKING, ADR 042 second revision)**: the two nouns from 0.5 — credentialed *servers* and project *contexts* — are consolidated into a single managed noun. A *context* is now a deploy environment (dev / staging / prod) declared in the app's committed `hop3.toml` under `[contexts.<name>]` (a non-secret bundle of server address, app, domains, and env). The `hop3 server` command and the `servers.toml` file are removed; credentials are invisible plumbing. Bearer tokens move to a per-server credential store (`~/.config/hop3-cli/credentials.toml`, mode `0600`), and `config.toml` becomes secret-free — keeping only local preferences and an optional default-server pointer. Existing `config.toml` connections are migrated to the credential store on first run.

### Security

- **`hop3.toml` holds zero secrets**: a committed-credential tripwire rejects secret-shaped values in committed `hop3.toml` env at validation time. Per-environment secrets are set server-side with `hop3 env set`; the per-server credential store is the only place bearer tokens are written.

## [0.6.0] - 2026-06-22

The 0.6 release builds on 0.5 with per-app resource limits and volumes, a much richer set of addon-management commands, a signed app catalog, and a published design record. Several commands were renamed for consistency, with the old names kept as aliases.

### Added

- **Resource limits (ADR 046)**: declare memory and CPU caps for an app under `[limits]`, enforced for both native and containerized apps. The server can set defaults and ceilings, and `hop3 app status` shows the caps and any out-of-memory kills.
- **Volumes (ADR 046)**: apps can mount persistent bind volumes and tmpfs, provisioned through the privileged daemon behind a default-deny allow-list and reconciled on startup.
- **Addon management commands**: a consistent `hop3 addon <type> <verb>` surface — ad-hoc queries (SQL / `redis-cli`), read-only diagnostics, clone, streaming a dump in or out (`export` / `import`), and `restore` / `flush` with confirmation. Plus `addon exists`, `addon promote` (per-addon variable namespacing), `addon endpoint`, `addon expose` / `unexpose`, and `hop3 tunnel` for reaching an addon from your own machine.
- **App catalog (ADR 049)**: Hop3 can load a signed, central catalog of installable apps (`hop3 catalog refresh`) and browse it from the dashboard; publishers get `hop3-catalog validate` / `publish` tooling. (The former "marketplace" is now the "catalog", ADR 031.)
- **Configurable backup contents**: choose which paths an app's backups include or exclude with `[backup].paths` / `[backup].exclude`.
- **Static sites without a Procfile**: serve a static app directly from `[build].static-dir`.
- **Fixed-port registry (ADR 045)**: non-HTTP apps (game servers, RTMP, and the like) can claim a stable host port from `hop3.toml`, optionally restricted to source CIDRs; `hop3 ports` lists the active claims. This replaces apps grabbing a fixed port outside Hop3's control.
- **Generated env secrets**: declare `SECRET_KEY = { generate = "urlsafe" }` under `[env]` and Hop3 provisions a stable, per-app secret instead of you hand-rolling one.

### Changed

- **App target is `--app` only (ADR 036)**: the deprecated positional app argument was removed; every app-scoped command takes `--app <name>`.
- **Minimum Python is now 3.12 (BREAKING)**: support for Python 3.11 was dropped.
- **Command renames (aliases kept)**: `launch` → `create`, `backup info` → `backup show`, `addon ps` → `addon activity`, `domains` → `domain`, the Procfile importer `env migrate` → `app migrate`, and account creation consolidated under `user add`. The old spellings still work as aliases.
- **Single source for the server secret (ADR 048)**: `HOP3_SECRET_KEY` now lives in one place, ending the environment-vs-config drift that could leave addon credentials unreadable after a restart.
- **Idempotent redeploys**: re-running the installer reuses existing database secrets and preserves operator configuration instead of regenerating them.
- **More detail in `hop3 system info`** for diagnostics.

### Fixed

- **Redeploy no longer kills its own push**: the process reaper no longer terminates the in-flight `git receive-pack`, so `git push` deploys complete reliably.
- **Stable app port across redeploys.**
- **Smaller deploy uploads**: build-output directories (Rust / Maven `target/`) are excluded from the upload.
- **Redis health check** authenticates correctly when no password is set in the environment.
- **Let's Encrypt email** is forwarded to the installer on the redeploy path.

### Security

- **Hardened catalog dashboard**: untrusted catalog content is sanitized — app READMEs render safely and only raster icons are accepted — and an "unavailable" banner is shown when the catalog source can't be reached.

### Documentation

- **Design record published**: the full set of Architecture Decision Records is now part of the documentation site, browsable alongside the guides.
- **Accuracy pass**: the guides, CLI reference, and tutorials were reviewed against the shipping behaviour and corrected.
- **Testing series**: a multi-part walkthrough of how Hop3 is tested.
- **"Migrating from X" series**: guides for moving to Hop3 from other platforms, starting with Heroku.
- **Second interim technical report** for the NGI project.

## [0.5.0] - 2026-06-08

### Highlights

- **CLI server/context model (ADR 042)**: credentialed *servers* are now separate from per-project deploy *contexts*, removing the sticky-global-default footgun; `hop3 deploy` previews the plan and asks for confirmation.
- **Unified testing architecture (ADR 043)**: one set of speed tiers across the test runners, and a shared diagnostic bundle (`hop3-test why`) that finally captures the "healthy app behind a 502" failure.
- **Nightly Test Lab (ADR 044)**: a `hop3-testlab` web dashboard with run history, a live run panel, the morning regressions diff, and trends.
- **Privileged-operations daemon `rootd` (ADR 041)**: a narrow root-boundary daemon replaces broad sudoers rules.
- **Security hardening**: several waves across the RPC boundary, authentication, and credential storage.

### Added

- **CLI ergonomics overhaul (ADR 036)**: a redesigned command surface — space-separated command names (`hop3 config set`), an implicit current app, a sticky working context (`hop3 use`), command aliases, did-you-mean suggestions, categorized help with an example on every command, scriptable confirmations and non-interactive flags, and secret inputs from a file or stdin.
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

### Changed

- **Command syntax (BREAKING, ADR 036)**: multi-word commands use spaces, not colons (`hop3 config set`, not `hop3 config:set`); the old colon form prints a migration hint.
- **Command names (BREAKING, ADR 036)**: user management moved under `user`, addon commands to the singular `addon`, and a few verbs were normalized.
- **Exit codes (ADR 036)**: the exit-code scheme was reorganized; scripts that branch on specific codes may need updating.
- **Server vs context vocabulary (BREAKING, ADR 042)**: the old global "context" is now a *server*, and "context" means a project deploy target; existing config is migrated on first run.
- **Testing layers (ADR 043)**: the test suite is three layers selected by speed tier; a plain `pytest` run never starts Docker.
- **More reliable deploys**: clearer messages about already-set env vars, IPv4 addon hosts to avoid IPv6 resolution issues, and assorted build and worker-precedence fixes.
- **Safer upgrades**: pending database migrations run on upgrade, and an existing virtualenv is no longer replaced.
- **Containerized app database access**: addons are reachable from apps on any private Docker network.

### Fixed

- Faster deploy log streaming (a cross-thread delay was removed).
- Numerous addon connection fixes (MySQL user creation and socket detection, addon host resolution).
- `--why` is now diagnostic-only, and the app name also resolves from `hop3.toml`.

### Security

- Untrusted RPC arguments are validated before use.
- Authentication hardening across the log and deploy streams; a pre-authentication admin-takeover path and a debug-info leak were closed.
- Addon credentials and secrets are re-encrypted with an automatic migration; stricter permissions on backup directories and defenses against decompression bombs.
- Closed injection and credential-leak vectors in addon provisioning.
- The privilege boundary moved from broad sudoers rules to the narrow, audited `rootd` daemon (ADR 041).

### Removed

- Dead CI workflows (SourceHut is the CI of record).

## [0.4.0] - 2026-03-27

This is a major release that transforms Hop3 from a deployment script into a complete self-hosted PaaS. It includes all changes from the 0.4.0 beta series plus significant testing and reliability improvements.

### Highlights

- **Client-Server Architecture**: Manage servers remotely from your laptop or CI
- **Multi-Language Support**: Python, Node.js, Ruby, Go, Rust, PHP, Java, Clojure, Elixir, static sites
- **Database Addons**: PostgreSQL, MySQL, Redis with encrypted credentials
- **Automatic SSL**: Let's Encrypt integration with auto-renewal
- **Multi-Distribution**: Ubuntu, Debian, Fedora, Rocky Linux, AlmaLinux
- **Configuration Validation**: Catch typos in hop3.toml with helpful suggestions
- **Security Audit**: Command injection fixes, session hardening, token validation
- **Comprehensive Test Suite**: Unit tests, integration tests, e2e tests, 58 testable demos, deployment tests, docker-app tests

See beta release notes below for the complete changelog.

---

## [0.4.0b8] - 2026-03-23

### Added

- **Git Push Deployment (Preview)**: Initial support for `git push hop3 main` deployment workflow
- **Internal Security Audit**: Comprehensive audit with public report in `notes/security-audit-2026-03.md`

### Changed

- **Shell Command Execution**: Replaced `shell=True` with list-based subprocess calls for security
- **Session Lifetime**: Reduced default from 14 days to 24 hours
- **JWT Secrets**: Enforced minimum 32-byte key length per RFC 7518
- **Bearer Token**: Fixed case-sensitivity per RFC 7235

### Fixed

- **Command Injection**: Fixed critical vulnerability in OS plugins and platform utilities
- **Before-Build Parsing**: Commands with `&&` are now properly executed sequentially
- **Type Checker Compatibility**: Fixed errors across pyrefly, mypy, and ruff

## [0.4.0b7] - 2026-03-16

### Added

- **Multi-Distribution Support**: Fully tested and working on Ubuntu 24.04, Debian 12/13, Fedora 42, Rocky Linux 9, and AlmaLinux 9
- **Repository Pattern**: Migrated database access to Advanced Alchemy repository pattern for better testability and maintainability
- **Configuration Validation**: JSON Schema validation for hop3.toml with Pydantic models using `extra="forbid"` to catch typos
- **Decision Logging**: New DecisionLogger tracks implicit choices (builder, toolchain, deployer) for debugging
- **Procfile Optional**: New `[run.workers]` section in hop3.toml allows defining workers without a Procfile
- **Explicit Toolchain Override**: New `[build].toolchain` directive to force a specific toolchain
- **Inline Ignore Patterns**: New `[build].ignore` and `[build].ignore-file` in hop3.toml for deployment filtering
- **stdin Support for `hop run`**: New `--input` option to pass stdin data to commands
- **Lessons Learned Document**: New `notes/lessons-learned.md` capturing development insights

### Changed

- **uWSGI Installation**: Now installed via pip instead of distro packages for cross-platform consistency. Eliminates 70+ lines of plugin detection code
- **Debian 12 Backports**: Uses official bookworm-backports instead of mixing trixie packages
- **Python Version Detection**: Automatically selects best available Python (3.12 > 3.11 > 3.10) on RHEL 9 clones
- **Config Output**: `hop config:show` and `hop config:live` now output sorted alphabetically by key
- **uWSGI Strict Mode**: Enabled `strict = true` to catch invalid configuration directives early

### Fixed

- **uWSGI `project` Directive**: Removed invalid directive that was silently ignored (inherited from piku)
- **RHEL 9 Python**: Fixed virtualenv creation using Python 3.9 instead of 3.12 on Rocky/AlmaLinux
- **`hop run` PATH**: Command PATH now includes virtualenv bin directory

### Removed

- **uWSGI Distro Packages**: Removed uwsgi and uwsgi-plugin-* from all distribution package lists
- **Plugin Detection Code**: Removed `_needs_python_plugin()` function and related complexity

## [0.4.0b6] - 2026-03-12

### Added

- **Debian Variants Support**: Installer now properly handles multiple Debian-based distributions (Debian, Ubuntu, and derivatives)
- **Debian 13 Testing**: Added testing support for Debian 13 "Trixie"
- **Domain Documentation**: Comprehensive guide for virtual hostname and domain configuration
- **System Tests**: New system test infrastructure for testing full deployment workflows

### Changed

- **SQLAlchemy 2.0 Migration**: Migrated all database queries from legacy `session.query()` API to modern `select()` API
- **Controller Refactoring**: Split large controller modules for better maintainability

### Fixed

- **Destructive Commands**: Added confirmation prompts for destructive commands (destroy, etc.)
- **SSL Certificates**: Multiple fixes for certificate handling and ACME configuration
- **Dashboard**: Fixed dashboard rendering issues

## [0.4.0b5] - 2025-02-28

### Added

- **Magic Link Login**: Installer now supports magic link authentication for initial setup
- **TUI Development**: Initial Terminal UI interface (work in progress)

### Changed

- **Installer Defaults**: Changed installer default behavior for better user experience

### Fixed

- **Web Login**: Fixed login sequence in web interface
- **WebUI Templates**: Fixed template rendering errors
- **Pydantic Imports**: Fixed import issues with Pydantic models

## [0.4.0b4] - 2025-02-21

### Added

- **Shell Completion**: Dynamic shell completion with command caching for CLI
- **PyPI Deployment**: Added PyPI deployment support to hop3-deploy installer tool

### Changed

- **CQS Cleanup**: Refactored commands following Command-Query Separation principles
- **Code Quality**: Extensive ruff fixes and code cleanup

### Fixed

- **Environment Variables**: Fixed environment variable handling issues

## [0.4.0b3] - 2025-02-14

### Added

- **SSH Auto-Auth**: Automatic SSH authentication with improved error messages
- **Multi-Server Support**: Improved CLI context support for managing multiple servers
- **System Info**: Added hostname and IP addresses to `system:info` command

### Changed

- **CLI Help**: Significantly improved CLI help messages and documentation
- **Command Simplification**: Refactored and simplified all command implementations

### Fixed

- **ACME Support**: Fixed server configuration and ACME/Let's Encrypt certificate support
- **ORM Cascade**: Fixed cascade issues in ORM relationships
- **Procfile Location**: Fixed Procfile detection in subdirectories

## [0.4.0b1] - TBD

This is a major architectural release that restructures Hop3 into a modern client-server architecture with extensive new features.

### Added

- **Client-Server Architecture**: New `hop3-cli` client communicates with `hop3-server` via JSON-RPC over SSH or HTTP/HTTPS
- **JWT Authentication**: Secure user authentication with JWT tokens, bcrypt password hashing, and role-based access control
- **Configuration System**: Support for both Procfile (convention) and hop3.toml (configuration) with precedence rules
- **Service Framework**: Plugin-based service/addon system with PostgreSQL implementation for managed databases
- **Service Credential Persistence**: ⚠️ **BREAKING CHANGE** - Service credentials now encrypted and persisted to database using Fernet AEAD encryption with PBKDF2-HMAC-SHA256 key derivation. Requires `HOP3_SECRET_KEY` environment variable for production deployments. Credentials survive server restarts and are properly managed through the entire service lifecycle (attach, detach, destroy)
- **Git Push Deployment**: Support for `git push` deployment method using git hooks
- **OS Plugin System**: Pluggable OS abstraction layer with family-based plugins supporting all Debian-based (Debian, Ubuntu, derivatives) and Red Hat-based (RHEL, Rocky, Alma, Fedora, CentOS) distributions, plus Arch, BSD, and macOS
- **Web UI Scaffolding**: Initial structure for future web-based management interface
- **Backup System**: Basic application backup mechanism (WIP)
- **SBOM Generation**: Automatic Software Bill of Materials generation for supply chain security
- **Environment Variable Management**: `config:set` and `config:unset` commands for managing per-app configuration
- **HOP3_UNSAFE Mode**: Test-only configuration option to bypass authentication in Docker test environments (never use in production)

### Changed

- **Monorepo Structure**: Reorganized into workspace with `hop3-cli`, `hop3-server`, `hop3-testing`, and `hop3-agent` packages
- **Dependency Management**: Migrated from Poetry to `uv` with workspace support
- **Configuration Handling**: Moved from hardcoded constants to flexible class-based configuration system
- **Path Handling**: Modernized to use `pathlib.Path` objects throughout
- **Command Execution**: Updated to use `subprocess.run` instead of legacy methods
- **License**: Changed to Apache 2.0
- **Proxy Architecture**: Refactored Nginx, Caddy, and Traefik implementations to use abstract `BaseProxy` class, eliminating ~240 lines of code duplication. Standardized `HOST_NAME` environment variable across all proxy plugins (replaced `NGINX_HOST_NAME`, `CADDY_SERVER_NAME`, `TRAEFIK_SERVER_NAME`)

### Removed

- **Legacy CLI**: Removed old monolithic CLI implementation in favor of client-server architecture

### Fixed

- **Security**: Fixed authentication bypass vulnerability in middleware
- **Nginx**: Fixed multiple nginx configuration issues including auto-reload, multi-app routing, and SSL certificate handling
- **E2E Tests**: Fixed socket permissions, SSH tunneling, and DNS resolution in end-to-end tests
- **Build System**: Fixed build strategy detection for Python applications
- **Installation**: Fixed missing python3-venv dependency and improved error messages

### Security

- **Authentication Middleware**: Fixed critical bug allowing bypass of authentication on non-public endpoints
- **Archive Security**: Enhanced deployment archive extraction with multiple security layers

## [0.3.0] - 2025-03-24

### Added

- First stable version for deploying simple web applications (Python WSGI and static sites)
- Core internal API for managing application lifecycles

### Fixed

- Stabilized installation script for production-like environments
- Numerous deployment reliability improvements

## [0.2.2] - 2024-07-15

### Added

- Initial development of web application and ORM model (WIP)
- Preliminary security features for web app

### Fixed

- Installer and static site deployment bugs
- Typing issues and broken web deployment mechanism

### Changed

- Refined uWSGI manager and actor framework

## [0.2.1] - 2024-07-04

### Added

- Initial actor-based framework

### Changed

- Improved certificate manager and proxy setup
- Major documentation updates including README, architecture, and core values

## [0.2.0] - 2024-06-28

### Changed

- Modernized Nginx setup with class-based implementation
- Major testing suite improvements

## [0.1.5] - 2024-06-27

### Added

- First version of CHANGES.md

### Fixed

- Temporarily disabled Nginx configuration checks

## [0.1.4] - 2024-06-27

### Fixed

- Static site deployment errors

### Changed

- Extensive README, metadata, and roadmap updates
- Added REUSE compliance logo

## [0.1.3] - 2024-06-07

### Changed

- Updated project dependencies

## [0.1.2] - 2024-04-19

### Changed

- Major code cleanup using `ruff`
- Modernized path handling with `pathlib`
- Improved docstrings throughout codebase

## [0.1.1] - 2024-04-18

### Added

- Application sorting capability

### Fixed

- Recent regression fix

## [0.1.0] - 2024-04-11

Initial release establishing Hop3's core architecture.

### Added

- Initial application builders and addon support
- SQL-based model with SQLAlchemy and PostgreSQL support
- First end-to-end test runner
- Initial README, roadmap, and compliance documentation

### Changed

- Established core class-based architecture
- Major refactoring for better structure and typing

[Unreleased]: https://github.com/abilian/hop3/compare/0.6.0...HEAD
[0.6.0]: https://github.com/abilian/hop3/compare/0.5.0...0.6.0
[0.5.0]: https://github.com/abilian/hop3/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abilian/hop3/compare/v0.4.0b8...v0.4.0
[0.4.0b8]: https://github.com/abilian/hop3/compare/v0.4.0b7...v0.4.0b8
[0.4.0b7]: https://github.com/abilian/hop3/compare/v0.4.0b6...v0.4.0b7
[0.4.0b6]: https://github.com/abilian/hop3/compare/v0.4.0b5...v0.4.0b6
[0.4.0b5]: https://github.com/abilian/hop3/compare/v0.4.0b4...v0.4.0b5
[0.4.0b4]: https://github.com/abilian/hop3/compare/v0.4.0b3...v0.4.0b4
[0.4.0b3]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0b3
[0.3.0]: https://github.com/abilian/hop3/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/abilian/hop3/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/abilian/hop3/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/abilian/hop3/compare/v0.1.5...v0.2.0
[0.1.5]: https://github.com/abilian/hop3/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/abilian/hop3/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/abilian/hop3/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/abilian/hop3/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/abilian/hop3/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/abilian/hop3/releases/tag/v0.1.0
