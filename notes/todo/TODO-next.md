# Next Development Steps for Hop3

## TOC

<!-- toc -->

- [Current Status](#current-status)
- [High Priority Tasks (Phase 3 - Immediate)](#high-priority-tasks-phase-3---immediate)
  * [1. Full-Featured Web UI Management (Step 3.1)](#1-full-featured-web-ui-management-step-31)
  * [2. Maintain Test Excellence](#2-maintain-test-excellence)
  * [3. Advanced Security Features (Step 3.2)](#3-advanced-security-features-step-32)
- [Medium Priority Tasks (Phase 3)](#medium-priority-tasks-phase-3)
  * [4. Monitoring, Logging, and Alerting (Step 3.3)](#4-monitoring-logging-and-alerting-step-33)
  * [5. Resolve Type Checking Issues](#5-resolve-type-checking-issues)
  * [6. Multi-Process App Support](#6-multi-process-app-support)
  * [7. Zero-Downtime Deployments](#7-zero-downtime-deployments)
- [Completed Feature Development Tasks (Phase 2)](#completed-feature-development-tasks-phase-2)
  * [8. Web UI Implementation ✅ COMPLETED (2025-11-13)](#8-web-ui-implementation-%E2%9C%85-completed-2025-11-13)
  * [9. Database Service Plugins ✅ COMPLETED (2025-11-12)](#9-database-service-plugins-%E2%9C%85-completed-2025-11-12)
  * [10. Backup/Restore Enhancement ✅ COMPLETED (2025-11-13)](#10-backuprestore-enhancement-%E2%9C%85-completed-2025-11-13)
- [Quality & Infrastructure Tasks](#quality--infrastructure-tasks)
  * [11. Test Coverage Expansion](#11-test-coverage-expansion)
  * [12. Docker Runtime Fixes](#12-docker-runtime-fixes)
  * [13. Multi-OS Support](#13-multi-os-support)
- [Code Cleanup Tasks](#code-cleanup-tasks)
  * [14. Remove Legacy Code](#14-remove-legacy-code)
  * [15. Documentation Updates](#15-documentation-updates)
  * [16. Replace Paramiko with Native SSH](#16-replace-paramiko-with-native-ssh)
  * [17. Migrate MySQL Addon to Database-Stored Credentials](#17-migrate-mysql-addon-to-database-stored-credentials)
- [Development Workflow](#development-workflow)
- [Phase 2 Completed Items ✅](#phase-2-completed-items-%E2%9C%85)
  * [Litestar Phase 2 Migration ✅ COMPLETED (2025-11-24)](#litestar-phase-2-migration-%E2%9C%85-completed-2025-11-24)
  * [Critical Technical Debt Resolved ✅ COMPLETED (2025-11-13)](#critical-technical-debt-resolved-%E2%9C%85-completed-2025-11-13)
  * [DI Integration ✅ COMPLETED (2025-11-22)](#di-integration-%E2%9C%85-completed-2025-11-22)
- [Success Metrics](#success-metrics)
  * [Phase 2 Metrics (Complete)](#phase-2-metrics-complete)
  * [Phase 3 Metrics (In Progress)](#phase-3-metrics-in-progress)

<!-- tocstop -->

## Current Status

**Updated: 2026-01-04**

- **Development Status**: Phase 2 Complete (100%) - Phase 3 Ready to Start
- **Version**: 0.4.0 development branch
- **Architecture**: Monorepo with Pluggy+Dishka DI, Pure Litestar stack
- **Production Readiness**: ~80% (all core PaaS features implemented)
- **Test Coverage**: 435 tests passing across 4 layers (232 unit, 128 integration, 14 system, 21 E2E, 40 dashboard)
- **Demo Testing**: 25 passed, 7 failed, 32 skipped (Docker backend)

## High Priority Tasks (Phase 3 - Immediate)

### 1. Full-Featured Web UI Management (Step 3.1)
- **Priority**: HIGHEST - Next major feature
- **Status**: App creation UI complete, need remaining CRUD operations
- **Tasks**:
  - [ ] App editing/configuration UI
  - [ ] App deletion with confirmation dialog
  - [ ] Service management UI (create, delete, attach/detach)
  - [ ] User management UI for admins
  - [ ] Environment variable management UI
- **Impact**: Complete read-write dashboard for full management

### 2. Maintain Test Excellence
- **Status**: All 435 tests passing (2 integration tests skipped due to known Starlette test client limitations)
- **Files**: `packages/hop3-server/tests/`
- **Action**: Continue comprehensive testing before major changes
- **Impact**: Ensures production readiness and code quality

### 3. Advanced Security Features (Step 3.2)
- **Priority**: HIGH - Security hardening for production
- **Tasks**:
  - [ ] Role-Based Access Control (RBAC) system
  - [ ] Audit logging for all user actions
  - [ ] Complete SBOM generation
  - [ ] Security scanning integration
  - [ ] Enhanced password policies
- **Impact**: Production-grade security posture

## Medium Priority Tasks (Phase 3)

### 4. Monitoring, Logging, and Alerting (Step 3.3)
- **Priority**: MEDIUM - Observability for production
- **Tasks**:
  - [ ] Centralized log aggregation (beyond SSE streaming)
  - [ ] Metrics collection (resource usage, app performance)
  - [ ] Alerting system (email, webhooks)
  - [ ] Health check monitoring
  - [ ] Dashboard for metrics visualization
- **Impact**: Production observability and incident response

### 5. Resolve Type Checking Issues
- **Issue**: Multiple typing problems throughout codebase
- **Action**: Fix mypy/pyright compliance as noted in roadmap
- **Benefit**: Improved code quality and IDE support
- **Priority**: MEDIUM - Code quality improvement

### 6. Multi-Process App Support
- **Priority**: MEDIUM - Advanced deployment features
- **Tasks**:
  - [ ] Support web + worker processes
  - [ ] Process orchestration and management
  - [ ] Inter-process communication
  - [ ] Resource allocation per process type
- **Impact**: Support for complex application architectures

### 7. Zero-Downtime Deployments
- **Priority**: MEDIUM - Production feature
- **Tasks**:
  - [ ] Blue-green deployment strategy
  - [ ] Rolling updates
  - [ ] Health check integration
  - [ ] Automatic rollback on failure
- **Impact**: Production-grade deployment reliability

## Completed Feature Development Tasks (Phase 2)

### 8. Web UI Implementation ✅ COMPLETED (2025-11-13)
- **Status**: Production-ready read-only dashboard implemented
- **Completed Features**:
  - [x] Application list and detail views with real-time status updates
  - [x] Server-Sent Events (SSE) log streaming with auto-scroll
  - [x] Environment variables management with secret masking
  - [x] Service detail pages with connection information
  - [x] Backup management (list, info, restore, delete)
  - [x] Modular architecture (apps, services, backups modules)
  - [x] TailwindCSS + HTMX + Alpine.js stack
  - [x] Full authentication integration with `@require_auth` decorator
- **Architecture**: Multi-Page Application (MPA) with server-side rendering
- **Test Coverage**: 128 integration tests passing
- **Files**: `packages/hop3-server/src/hop3/server/views/dashboard/*`

### 9. Database Service Plugins ✅ COMPLETED (2025-11-12)
- **Goal**: PostgreSQL, Redis lifecycle management
- **Status**: PostgreSQL service fully implemented with encrypted credentials
- **Completed Features**:
  - [x] Service creation and destruction
  - [x] Credential persistence with Fernet AEAD encryption
  - [x] Connection details management
  - [x] Service backup and restore
  - [x] Service info and statistics
- **Files**:
  - `packages/hop3-server/src/hop3/plugins/postgresql/postgres.py`
  - `packages/hop3-server/src/hop3/orm/service_credential.py`

### 10. Backup/Restore Enhancement ✅ COMPLETED (2025-11-13)
- **Status**: Full backup/restore system implemented with 46 tests
- **Completed Features**:
  - [x] Application source code backup
  - [x] Environment variables backup
  - [x] Service data backup (PostgreSQL)
  - [x] Backup verification with SHA256 checksums
  - [x] Backup listing and filtering
  - [x] Backup restore to same or different app
  - [x] Backup deletion
  - [x] Fail-fast behavior (backup fails if services cannot be backed up)
- **Security**: Incomplete backups now properly marked as FAILED
- **Test Coverage**: 18 unit tests + 9 E2E tests
- **Files**: `packages/hop3-server/src/hop3/core/backup.py`

## Quality & Infrastructure Tasks

### 11. Test Coverage Expansion
- **Current**: Basic unit tests passing
- **Need**: More end-to-end tests
- **Action**: Expand test suite coverage

### 12. Docker Runtime Fixes
- **Status**: Complete ✅ (2026-01-04)
- **Progress**:
  - [x] Docker-in-Docker demos skip cleanly in Docker backend (32 demos)
  - [x] Database services (PostgreSQL, MySQL, Redis) working in Docker backend
  - [x] Fixed prebuild worker bug causing Elixir build failures
  - [x] Demo12 and Demo59 now passing
  - [x] Changed Python toolchain to use built-in `venv` instead of external `virtualenv`
- **Result**: All 32+ non-Docker demos pass when run in batches

### 13. Multi-OS Support
- **Status**: Basic support exists
- **Action**: Stabilize support for Ubuntu, Arch, Fedora, NixOS
- **Priority**: Part of P1 MVP goals

## Code Cleanup Tasks

### 14. Remove Legacy Code
- **Files**:
  - `installer/install-hop.py:41` - Use symlink instead of copying
  - `packages/hop3-server/old_cli/main.py:4` - Use pluggy for plugins
  - `tasks.py:51,56` - Fix TODO items
- **Action**: Clean up legacy implementations

### 15. Documentation Updates
- **Files**: `noxfile.py:97` - Complete docs build
- **Action**: Improve documentation build process

### 16. Replace Paramiko with Native SSH
- **Issue**: sshtunnel uses paramiko which triggers CryptographyDeprecationWarning (TripleDES)
- **Files**: `packages/hop3-cli/src/hop3_cli/rpc/client.py`
- **Solution**: Replace sshtunnel with subprocess-based `ssh -L` port forwarding
- **Benefits**: Eliminates paramiko dependency, uses native ssh, simpler code
- **Priority**: LOW - warnings are now suppressed, functional alternative can wait

### 17. Migrate MySQL Addon to Database-Stored Credentials
- **Issue**: MySQL addon stores secrets in JSON files (`/home/hop3/addons/mysql/*.json`) while PostgreSQL uses encrypted database storage (`AddonCredential` table with Fernet encryption)
- **Files**: `packages/hop3-server/src/hop3/plugins/mysql/mysql.py`
- **Solution**: Refactor MySQL addon to use same credential persistence pattern as PostgreSQL
- **Benefits**:
  - Consistent architecture across all addons
  - Better security (encrypted vs plaintext JSON)
  - Centralized credential management
  - Easier backup/restore
- **Reference**: PostgreSQL implementation in `packages/hop3-server/src/hop3/plugins/postgresql/postgres.py`
- **Priority**: MEDIUM - architectural consistency
- **Added**: 2026-01-06

## Development Workflow

1. **Focus on High Priority items first** - These block 0.4.0 usability
2. **Complete plugin architecture** - Foundation for future features
3. **Stabilize core components** - Before adding new features
4. **Expand testing** - Ensure quality throughout refactoring

## Phase 2 Completed Items ✅

### Litestar Phase 2 Migration ✅ COMPLETED (2025-11-24)
- **Status**: Complete migration from Starlette to pure Litestar
- **Completed Features**:
  - [x] Guard-based authentication (replaced Starlette middleware)
  - [x] Native session management (ServerSideSessionConfig)
  - [x] Clean 404 logging (no tracebacks)
  - [x] Favicon serving via static files
  - [x] 128/130 integration tests passing (98.5%, 2 skipped)
  - [x] Zero Starlette dependencies remaining

### Critical Technical Debt Resolved ✅ COMPLETED (2025-11-13)
- **Status**: All 4 critical items complete
- **Security**:
  - [x] Fixed hardcoded PostgreSQL password (secure random generation)
  - [x] Implemented JWT token revocation system
- **Operations**:
  - [x] Implemented Alembic database migrations
  - [x] Fixed SSH tunnel cleanup (context manager pattern)

### DI Integration ✅ COMPLETED (2025-11-22)
- **Status**: Pluggy+Dishka integration complete
- **Completed Features**:
  - [x] BackupManager DI integration with REQUEST scope
  - [x] PostgreSQL and Redis plugin DI providers
  - [x] DatabaseProvider with proper session lifecycle
  - [x] Clean testing patterns established
  - [x] Documentation in docs/src/dev/di-testing-guide.md

## Success Metrics

### Phase 2 Metrics (Complete)
- [x] Plugin architecture fully functional (PostgreSQL + Redis plugins)
- [x] Web UI dashboard operational (read-only with SSE log streaming)
- [x] Backup/restore system production-ready (46 tests)
- [x] Service credential encryption implemented (Fernet AEAD)
- [x] CLI UX improvements complete (rich formatting, confirmations)
- [x] Database migrations (Alembic)
- [x] JWT token revocation
- [x] DI integration patterns established
- [x] Pure Litestar stack (zero Starlette dependencies)

### Phase 3 Metrics (In Progress)
- [ ] Full-featured web UI (CRUD operations for apps/services)
- [ ] RBAC system implemented
- [ ] Audit logging operational
- [ ] Centralized monitoring and alerting
- [x] All tests passing (435 tests, 2 skipped)
- [ ] Multi-process app support
- [ ] Zero-downtime deployments

---

*Last updated: 2026-01-04*
