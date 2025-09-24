# Next Development Steps for Hop3

## Current Status

- **Stable Branch (0.3.0)**: Production-ready for simple web applications
- **Development Branch (0.4.0)**: Major refactoring in progress - not yet usable
- **Architecture**: Transitioning to monorepo with plugin-based architecture

## High Priority Tasks (Immediate)

### 1. Complete Monorepo Refactoring
- **Issue**: Multiple `packages-ignored/` directories with old code
- **Action**: Clean up obsolete packages and finalize structure
- **Files**: `packages-ignored/hop3-*` directories
- **Impact**: Essential for 0.4.0 stability

### 2. Fix Plugin Architecture
- **Issue**: Core plugin registration incomplete
- **Files**:
  - `packages/hop3-server/src/hop3/core/plugins.py:78` - Register core plugins
  - `packages/hop3-server/src/hop3/core/plugins.py:105,115` - Strategy selection logic
- **Action**: Complete plugin loading and strategy selection mechanisms

### 3. Complete App Model Refactoring
- **Issue**: Core deployment method incomplete
- **Files**:
  - `packages/hop3-server/src/hop3/orm/app.py:324` - Finish `deploy()` method refactoring
  - `packages/hop3-server/src/hop3/orm/app.py:356` - Handle already stopped apps
- **Action**: Complete the App lifecycle management refactoring

## Medium Priority Tasks

### 4. Resolve Type Checking Issues
- **Issue**: Multiple typing problems throughout codebase
- **Action**: Fix mypy/pyright compliance as noted in roadmap
- **Benefit**: Improved code quality and IDE support

### 5. Complete CLI Refactoring
- **Issue**: Server-side CLI implementation needs completion
- **Files**: Based on recent commits showing server-side CLI work
- **Action**: Finalize JSON-RPC based CLI architecture

### 6. Stabilize Plugin System
- **Issue**: Hook specifications incomplete
- **Files**:
  - `packages/hop3-server/src/hop3/core/hookspecs.py:24` - CLI commands registration
- **Action**: Complete plugin hook specifications

### 7. Configuration System Cleanup
- **Issue**: Configuration loading has errors
- **Files**:
  - `packages/hop3-server/src/hop3/config.py:1` - FIXME comment
  - `packages/hop3-server/src/hop3/lib/settings.py:95` - Error handling
- **Action**: Resolve configuration loading issues

## Feature Development Tasks

### 8. Web UI Implementation
- **Status**: Basic scaffolding exists
- **Action**: Implement actual web interface functionality
- **Priority**: Medium (part of 0.4.0 goals)

### 9. Database Service Plugins
- **Goal**: PostgreSQL, Redis lifecycle management
- **Status**: Planned in roadmap P1 MVP
- **Action**: Implement service management plugins

### 10. Backup/Restore Enhancement
- **Issue**: Basic mechanism exists but incomplete
- **Files**: `packages/hop3-server/src/hop3/orm/backup.py:24` - Add encryption
- **Action**: Complete backup functionality with encryption

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

## Success Metrics

- [ ] 0.4.0 branch becomes usable for basic deployments
- [ ] Plugin architecture fully functional
- [ ] All typing issues resolved
- [ ] Core App model refactoring complete
- [ ] Monorepo structure finalized

---

*Last updated: 2025-09-23*
*Based on: git log analysis, roadmap.md, and codebase TODO/FIXME review*
