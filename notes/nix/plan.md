# Hop3 Nixification Plan

This document outlines the strategy for making Hop3 fully compatible with Nix and NixOS.

## Goals

1. **Development**: Reproducible dev environment via `nix develop`
2. **Packaging**: Build hop3-cli and hop3-server as Nix packages
3. **Deployment**: NixOS module for declarative server deployment
4. **Testing**: Validate Hop3 on NixOS as a deployment target

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| `flake.nix` | ✅ Created | Dev shell, packages, NixOS module skeleton |
| Dev shell | ✅ Working | Python 3.12 + uv available |
| hop3-cli package | ✅ Working | Builds and runs successfully |
| hop3-server package | ✅ Working | Builds successfully (uses uvicorn instead of granian) |
| NixOS module | ✅ Complete | Full module with PostgreSQL, Nginx, SSL options |
| System-manager config | ✅ Complete | For Nix-on-Ubuntu deployments |
| NixOS as deployment target | ❌ Not started | Requires OS plugin |

---

## Phase 1: Development Environment (DONE)

### 1.1 Nix Installation on Ubuntu
- ✅ Install `nix-bin` package
- ✅ Enable flakes in `/etc/nix/nix.conf`
- ✅ Create dedicated user with `/nix` ownership
- ✅ Document in `notes/nix/prepare.md`

### 1.2 Development Shell
- ✅ `nix develop` provides Python 3.12 + uv
- ✅ System dependencies available (git, postgresql, sqlite, gcc, openssl)
- ✅ `uv sync` works inside the shell

---

## Phase 2: Package Building (DONE)

### 2.1 Assess Missing Dependencies

Several Python packages used by Hop3 may not be in nixpkgs:

| Package | In nixpkgs? | Action Required |
|---------|-------------|-----------------|
| `litestar` | ✅ Yes | - |
| `advanced-alchemy` | ❌ No | Create overlay |
| `dishka` | ❌ No | Create overlay |
| `granian` | ❓ Check | May need overlay |
| `cyclonedx-bom` | ❓ Check | May need overlay |
| `jsonrpcclient` | ✅ Yes | - |
| `sshtunnel` | ✅ Yes | - |

**Action**: Run `nix search nixpkgs python312Packages.<name>` for each dependency.

### 2.2 Create Python Package Overlays

For missing packages, create overlays in `nix/overlays/python-packages.nix`:

```nix
final: prev: {
  python312 = prev.python312.override {
    packageOverrides = python-final: python-prev: {
      advanced-alchemy = python-final.buildPythonPackage rec {
        pname = "advanced-alchemy";
        version = "...";
        src = python-final.fetchPypi { ... };
        # ...
      };
    };
  };
}
```

### 2.3 Handle Build Backend

Hop3 packages use `uv-build` which isn't in nixpkgs. Options:

1. **Option A**: Patch pyproject.toml to use `hatchling` or `setuptools`
2. **Option B**: Create a `uv-build` package for nixpkgs
3. **Option C**: Use `pyproject.nix` or `uv2nix` tooling

**Recommendation**: Start with Option A (hatchling) for simplicity, migrate to Option B/C later.

### 2.4 Build and Test Packages

```bash
# Test hop3-cli build
nix build .#hop3-cli -L

# Test hop3-server build
nix build .#hop3-server -L

# Verify binaries work
./result/bin/hop3 --version
./result/bin/hop3-server --help
```

### 2.5 Milestone: Working Packages

- [x] `nix build .#hop3-cli` succeeds
- [x] `nix build .#hop3-server` succeeds
- [x] `nix run .#hop3 -- --version` works
- [ ] `nix run .#hop3-server -- serve` starts successfully (blocked by config init at import time)

---

## Phase 3: NixOS Module (DONE)

### 3.1 Basic Service Configuration

The skeleton module in `flake.nix` needs:

```nix
services.hop3 = {
  enable = true;
  port = 8000;
  homeDir = "/home/hop3";
  secretKeyFile = "/run/secrets/hop3-key";

  # Database configuration
  database = {
    type = "postgresql";  # or "sqlite"
    # PostgreSQL uses local socket by default
  };

  # Nginx integration
  nginx = {
    enable = true;
    virtualHost = "hop3.example.com";
  };
};
```

### 3.2 Module Features

| Feature | Priority | Description |
|---------|----------|-------------|
| Systemd service | High | Run hop3-server as a service |
| User/group creation | High | Create hop3 user with correct permissions |
| Home directory setup | High | `/home/hop3` with proper structure |
| Secret management | High | Integration with sops-nix or agenix |
| PostgreSQL integration | Medium | Auto-configure database |
| Nginx integration | Medium | Reverse proxy configuration |
| Let's Encrypt | Medium | Automatic SSL via ACME |
| Firewall rules | Low | Open ports 80, 443, 22 |

### 3.3 Directory Structure

The NixOS module should create:

```
/home/hop3/
├── apps/           # Application deployments
├── nginx/          # Nginx configs (if not using NixOS nginx)
├── uwsgi-available/
├── uwsgi-enabled/
└── hop3.db         # SQLite database (if not using PostgreSQL)
```

### 3.4 Extract Module to Separate File

Move the NixOS module from `flake.nix` to `nix/modules/hop3.nix` for maintainability:

```
nix/
├── modules/
│   └── hop3.nix       # NixOS module
├── overlays/
│   └── python-packages.nix  # Missing Python packages
└── packages/
    ├── hop3-cli.nix
    └── hop3-server.nix
```

### 3.5 Milestone: Working NixOS Deployment

- [x] Module imports without errors
- [x] `services.hop3.enable = true` configures the service
- [ ] hop3-server accepts connections (needs testing on NixOS)
- [ ] Can deploy a sample app via `hop3` CLI (needs testing)

---

## Phase 4: NixOS as Deployment Target

Currently, Hop3 supports Debian/Ubuntu via its OS plugin system. We need a NixOS plugin.

### 4.1 Create NixOS OS Plugin

Location: `packages/hop3-server/src/hop3/plugins/oses/nixos.py`

```python
from hop3.core.protocols import OS


class NixOS(OS):
    name = "nixos"

    def detect(self) -> bool:
        """Check if running on NixOS."""
        return Path("/etc/nixos").exists()

    def install_packages(self, packages: list[str]) -> None:
        """
        NixOS doesn't support imperative package installation.
        Options:
        1. Use nix-shell/nix-env for user packages
        2. Require packages in system configuration
        3. Use nix profile install
        """
        # Implementation depends on strategy chosen
        pass

    def setup_service(self, name: str, config: dict) -> None:
        """
        Services on NixOS are declarative.
        Options:
        1. Generate a NixOS module snippet for the user
        2. Use systemd directly (bypassing NixOS)
        3. Hybrid approach
        """
        pass
```

### 4.2 Key Differences from Debian

| Aspect | Debian | NixOS |
|--------|--------|-------|
| Package install | `apt install` | Declarative in configuration.nix |
| Service management | `systemctl` + unit files | NixOS module system |
| File locations | FHS standard | `/nix/store` paths |
| User packages | System-wide or pip | nix profile or home-manager |
| Configuration | Mutable files | Immutable, rebuilt on switch |

### 4.3 Strategy Options

**Option A: Minimal NixOS Support (Recommended First)**
- Detect NixOS and warn user that system packages must be pre-installed
- Use systemd directly for services (bypasses NixOS module system)
- App deployments work normally (they're user-space)

**Option B: Full NixOS Integration**
- Generate NixOS module configurations for each app
- Require `nixos-rebuild switch` for system changes
- More complex but more "NixOS-native"

**Option C: Hybrid with Nix Profiles**
- Use `nix profile install` for toolchains
- Services via systemd user units
- Middle ground between A and B

### 4.4 Toolchain Considerations

Hop3 toolchains (Python, Node, Rust, etc.) need adaptation:

| Toolchain | Current Approach | NixOS Approach |
|-----------|-----------------|----------------|
| Python | pyenv/system | `nix shell nixpkgs#python3` |
| Node | nvm/fnm | `nix shell nixpkgs#nodejs` |
| Rust | rustup | `nix shell nixpkgs#rustc` |
| Go | system | `nix shell nixpkgs#go` |

### 4.5 Milestone: Hop3 Works on NixOS

- [ ] NixOS detected correctly
- [ ] Sample Python app deploys successfully
- [ ] Sample Node app deploys successfully
- [ ] Nginx proxying works
- [ ] PostgreSQL addon works

---

## Phase 5: Testing and CI

### 5.1 NixOS VM Testing

Create a NixOS VM configuration for testing:

```nix
# nix/tests/vm.nix
{ pkgs, ... }: {
  imports = [ self.nixosModules.default ];

  services.hop3.enable = true;

  # Test prerequisites
  services.postgresql.enable = true;
  services.nginx.enable = true;

  # Open firewall for testing
  networking.firewall.allowedTCPPorts = [ 22 80 443 8000 ];
}
```

Run with: `nix run .#nixosConfigurations.test-vm.config.system.build.vm`

### 5.2 Integration with Existing Tests

Add NixOS to the test matrix:

```bash
# packages/hop3-testing/tests
pytest --target=nixos-vm tests/
```

### 5.3 CI Pipeline

Add to `.github/workflows/`:

```yaml
nixos-test:
  runs-on: ubuntu-latest
  steps:
    - uses: cachix/install-nix-action@v24
    - run: nix flake check
    - run: nix build .#hop3-cli
    - run: nix build .#hop3-server
```

---

## Phase 6: Documentation and Polish

### 6.1 User Documentation

- Installation guide for NixOS users
- Configuration examples
- Troubleshooting guide

### 6.2 Developer Documentation

- How to add packages to the overlay
- How to test NixOS module changes
- Architecture of the NixOS OS plugin

### 6.3 Examples

Create example configurations:

```
examples/
├── nixos-minimal/       # Minimal NixOS configuration
├── nixos-full/          # Full setup with PostgreSQL, Nginx, SSL
└── nixos-development/   # Development VM setup
```

---

## Timeline and Priorities

| Phase | Priority | Effort | Dependencies |
|-------|----------|--------|--------------|
| Phase 1: Dev Environment | ✅ Done | - | - |
| Phase 2: Package Building | High | 1-2 days | Fix missing deps |
| Phase 3: NixOS Module | High | 2-3 days | Phase 2 |
| Phase 4: NixOS OS Plugin | Medium | 3-5 days | Phase 3 |
| Phase 5: Testing | Medium | 2-3 days | Phase 4 |
| Phase 6: Documentation | Low | 1-2 days | Phase 5 |

**Recommended Order**:
1. Get `nix build .#hop3-cli` working (quick win)
2. Get `nix build .#hop3-server` working (may need overlays)
3. Test NixOS module on a real NixOS system
4. Implement minimal NixOS OS plugin
5. Iterate based on real-world testing

---

## Open Questions

1. **Build backend**: Should we patch pyproject.toml or create uv-build for Nix?
2. **App isolation**: Should deployed apps use Nix for their dependencies?
3. **Toolchain strategy**: nix-shell per app, or system-wide toolchains?
4. **Service management**: Native NixOS modules or direct systemd?
5. **Updates**: How to handle `nixos-rebuild switch` with running apps?

---

## Resources

- [Nix Pills](https://nixos.org/guides/nix-pills/) - Nix fundamentals
- [NixOS Manual](https://nixos.org/manual/nixos/stable/) - Module system
- [pyproject.nix](https://github.com/nix-community/pyproject.nix) - Python packaging
- [uv2nix](https://github.com/adisbladis/uv2nix) - uv to Nix converter
- [poetry2nix](https://github.com/nix-community/poetry2nix) - Reference for Python Nix packaging
