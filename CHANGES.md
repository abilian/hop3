# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- **Mypy Errors**: Fixed type errors in schema.py, apps.py, and auth.py
- **Lint Errors**: Fixed TC001 imports with proper noqa comments for Dishka DI runtime requirements

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

[Unreleased]: https://github.com/abilian/hop3/compare/v0.4.0b7...HEAD
[0.4.0b7]: https://github.com/abilian/hop3/compare/v0.4.0b6...v0.4.0b7
[0.4.0b6]: https://github.com/abilian/hop3/compare/v0.4.0b5...v0.4.0b6
[0.4.0b5]: https://github.com/abilian/hop3/compare/v0.4.0b4...v0.4.0b5
[0.4.0b4]: https://github.com/abilian/hop3/compare/v0.4.0b3...v0.4.0b4
[0.4.0b3]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0b3
[0.4.0]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0
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
