# Next Development Steps for Hop3

## TOC

<!-- toc -->

- [Current Status](#current-status)
- [High Priority Tasks (Immediate)](#high-priority-tasks-immediate)
  * [1. Complete Monorepo Refactoring](#1-complete-monorepo-refactoring)
  * [2. Fix Plugin Architecture](#2-fix-plugin-architecture)
  * [3. Complete App Model Refactoring](#3-complete-app-model-refactoring)
- [Medium Priority Tasks](#medium-priority-tasks)
  * [4. Resolve Type Checking Issues](#4-resolve-type-checking-issues)
  * [5. Complete CLI Refactoring](#5-complete-cli-refactoring)
  * [6. Stabilize Plugin System](#6-stabilize-plugin-system)
  * [7. Configuration System Cleanup](#7-configuration-system-cleanup)
- [Feature Development Tasks](#feature-development-tasks)
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
- [Development Workflow](#development-workflow)
- [Success Metrics](#success-metrics)

<!-- tocstop -->

## Current Status

**Updated: 2025-11-24**

- **Development Status**: Phase 2 Complete (100%) - Phase 3 Ready to Start
- **Version**: 0.4.0 development branch
- **Architecture**: Monorepo with Pluggy+Dishka DI, Pure Litestar stack
- **Production Readiness**: ~80% (all core PaaS features implemented)
- **Test Coverage**: 435 tests passing across 4 layers (232 unit, 128 integration, 14 system, 21 E2E, 40 dashboard)

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
- **Status**: ✅ All 435 tests passing (2 integration tests skipped due to known Starlette test client limitations)
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
- **Status**: ✅ Production-ready read-only dashboard implemented
- **Completed Features**:
  - Application list and detail views with real-time status updates
  - Server-Sent Events (SSE) log streaming with auto-scroll
  - Environment variables management with secret masking
  - Service detail pages with connection information
  - Backup management (list, info, restore, delete)
  - Modular architecture (apps, services, backups modules)
  - TailwindCSS + HTMX + Alpine.js stack
  - Full authentication integration with `@require_auth` decorator
- **Architecture**: Multi-Page Application (MPA) with server-side rendering
- **Test Coverage**: 128 integration tests passing
- **Files**: `packages/hop3-server/src/hop3/server/views/dashboard/*`

### 9. Database Service Plugins ✅ COMPLETED (2025-11-12)
- **Goal**: PostgreSQL, Redis lifecycle management
- **Status**: ✅ PostgreSQL service fully implemented with encrypted credentials
- **Completed Features**:
  - Service creation and destruction
  - Credential persistence with Fernet AEAD encryption
  - Connection details management
  - Service backup and restore
  - Service info and statistics
- **Files**:
  - `packages/hop3-server/src/hop3/plugins/postgresql/postgres.py`
  - `packages/hop3-server/src/hop3/orm/service_credential.py`

### 10. Backup/Restore Enhancement ✅ COMPLETED (2025-11-13)
- **Status**: ✅ Full backup/restore system implemented with 46 tests
- **Completed Features**:
  - Application source code backup
  - Environment variables backup
  - Service data backup (PostgreSQL)
  - Backup verification with SHA256 checksums
  - Backup listing and filtering
  - Backup restore to same or different app
  - Backup deletion
  - Fail-fast behavior (backup fails if services cannot be backed up)
- **Security**: Incomplete backups now properly marked as FAILED
- **Test Coverage**: 18 unit tests + 9 E2E tests
- **Files**: `packages/hop3-server/src/hop3/core/backup.py`

## Quality & Infrastructure Tasks

### 11. Test Coverage Expansion
- **Current**: Basic unit tests passing
- **Need**: More end-to-end tests
- **Action**: Expand test suite coverage

### 12. Docker Runtime Fixes
- **Status**: Docker building works, runtime needs fixes
- **Roadmap**: "Run as docker image" in P1 MVP
- **Action**: Fix Docker deployment issues

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

## Development Workflow

1. **Focus on High Priority items first** - These block 0.4.0 usability
2. **Complete plugin architecture** - Foundation for future features
3. **Stabilize core components** - Before adding new features
4. **Expand testing** - Ensure quality throughout refactoring

## Phase 2 Completed Items ✅

### Litestar Phase 2 Migration ✅ COMPLETED (2025-11-24)
- **Status**: ✅ Complete migration from Starlette to pure Litestar
- **Completed Features**:
  - Guard-based authentication (replaced Starlette middleware)
  - Native session management (ServerSideSessionConfig)
  - Clean 404 logging (no tracebacks)
  - Favicon serving via static files
  - 128/130 integration tests passing (98.5%, 2 skipped)
  - Zero Starlette dependencies remaining

### Critical Technical Debt Resolved ✅ COMPLETED (2025-11-13)
- **Status**: ✅ All 4 critical items complete
- **Security**:
  - Fixed hardcoded PostgreSQL password (secure random generation)
  - Implemented JWT token revocation system
- **Operations**:
  - Implemented Alembic database migrations
  - Fixed SSH tunnel cleanup (context manager pattern)

### DI Integration ✅ COMPLETED (2025-11-22)
- **Status**: ✅ Pluggy+Dishka integration complete
- **Completed Features**:
  - BackupManager DI integration with REQUEST scope
  - PostgreSQL and Redis plugin DI providers
  - DatabaseProvider with proper session lifecycle
  - Clean testing patterns established
  - Documentation in docs/src/dev/di-testing-guide.md

## Success Metrics

### Phase 2 Metrics (Complete)
- [x] ✅ Plugin architecture fully functional (PostgreSQL + Redis plugins)
- [x] ✅ Web UI dashboard operational (read-only with SSE log streaming)
- [x] ✅ Backup/restore system production-ready (46 tests)
- [x] ✅ Service credential encryption implemented (Fernet AEAD)
- [x] ✅ CLI UX improvements complete (rich formatting, confirmations)
- [x] ✅ Database migrations (Alembic)
- [x] ✅ JWT token revocation
- [x] ✅ DI integration patterns established
- [x] ✅ Pure Litestar stack (zero Starlette dependencies)

### Phase 3 Metrics (In Progress)
- [ ] Full-featured web UI (CRUD operations for apps/services)
- [ ] RBAC system implemented
- [ ] Audit logging operational
- [ ] Centralized monitoring and alerting
- [x] ✅ All tests passing (435 tests, 2 skipped)
- [ ] Multi-process app support
- [ ] Zero-downtime deployments

---

*Last updated: 2025-11-24*
