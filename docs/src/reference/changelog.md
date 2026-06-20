# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Generated secrets in `hop3.toml`**: declare an app-internal secret as `KEY = { generate = "hex" | "base64" | "urlsafe" | "password" | "uuid", length = N, prefix = "..." }` under `[env]`. Hop3 generates the value with a CSPRNG on the first deploy, persists it, and never rotates it (generated-once) — replacing the manual `hop3 config set KEY=$(...)` workaround and making first-boot reproducible for apps that require a secret at startup (Phoenix `SECRET_KEY_BASE`, Laravel `APP_KEY`, Rails `secret_key_base`, …). See [Generated secrets](config.md#generated-secrets) (ADR 046).
- **Dynamic `[env]` references**: `KEY = { from = "<addon>", key = "<VAR>" }` copies an attribute from an attached addon, and `KEY = { key = "domain" | "hostname" | "name" }` reads an app fact (ADR 046).
- **Persistent volumes (`[[volumes]]`)**: declare a directory that survives the source-replacing redeploy; Hop3 stores it outside `src/` and links it in on every deploy. Backups now include volume data, and restore round-trips it. See the Persistent Volumes section of [the config reference](config.md) (ADR 046).
- **Resource limits (`[limits]`)**: cap an app's `memory` / `cpu` / `processes`. Enforced for Docker-deployed apps (compose limits); declaring `[limits]` on a non-Docker app fails the deploy loudly until cgroup enforcement lands, so a limit is never silently un-applied. See the Resource Caps section of [the config reference](config.md) (ADR 046).

### Fixed

- **Backups now capture all app data**: volume data and the app `data/` directory are archived (previously volume data could be silently excluded), and restore no longer aborts for apps that use a volume.
- **`hop3 app destroy` is honest and loud**: it removes the app and all its data (a complete teardown) and warns about the data/volumes it deletes — the previous "preserves data" docstring and dead code did neither.

## [0.4.0] - TBD

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
- **Environment Variable Management**: `config set` and `config unset` commands for managing per-app configuration
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

[Unreleased]: https://github.com/abilian/hop3/compare/v0.3.0...HEAD
[0.4.0]: https://github.com/abilian/hop3/compare/v0.3.0...HEAD
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
