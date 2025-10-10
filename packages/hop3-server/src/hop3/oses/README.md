# OS Setup Modules

This directory contains OS-specific setup scripts for installing hop3 dependencies on various Linux distributions.

## Purpose

The `hop3.oses` module provides a **declarative abstraction layer** for setting up servers with the required dependencies to run hop3. Each OS-specific module defines:

- Required system packages
- User account configuration
- System file modifications
- Service setup

## Current Status

⚠️ **NOT YET USED IN PRODUCTION**

These modules are currently **stubs** and are not yet integrated into the main hop3 deployment workflow. The actual installation is currently performed by:
- `installer/install-hop.py` - Uses PyInfra for automated server setup

## Architecture

### Base Classes (`helpers.py`)

- **`Platform`**: Base class for all platform implementations
- **`Linux`**: Linux-specific operations (file operations, links, users)
- **`Debian`**: Debian/Ubuntu-specific operations (APT package management)

### OS-Specific Modules

Each OS module provides a `setup_server()` function that:
1. Configures APT settings (for Debian-based systems)
2. Creates the `hop3` user account
3. Installs required system packages
4. Sets up necessary symbolic links

## Supported Distributions

### Debian-based

| Distribution | Module | Status | Notes |
|-------------|--------|--------|-------|
| Debian 12 (Bookworm) | `debian12.py` | ✅ Complete | Current stable |
| Debian 13 (Trixie) | `debian13.py` | ✅ Complete | Testing/unstable |
| Ubuntu 22.04 LTS | `ubuntu2204.py` | ✅ Complete | Jammy Jellyfish |
| Ubuntu 24.04 LTS | `ubuntu2404.py` | ✅ Complete | Noble Numbat |
| Generic Debian | `debian.py` | ✅ Complete | Fallback for any Debian |

### Other

| Distribution | Module | Status | Notes |
|-------------|--------|--------|-------|
| NixOS | `nixos.py` | ⚠️ Stub | Requires declarative config approach |

## Package Dependencies

All Debian-based distributions install:

### Core System Tools
- `bc`, `git`, `sudo`, `cron`
- `build-essential`, `libpcre3-dev`, `zlib1g-dev`

### Python Ecosystem
- `python3`, `python3-pip`, `python3-dev`, `python3-venv`
- `python3-virtualenv`, `python3-setuptools`, `python3-click`

### Web Server & Proxy
- `nginx`, `acl`

### Application Server
- `uwsgi-core`, `uwsgi-plugin-python3`

### SSL/TLS
- `certbot` (Let's Encrypt)

### Language Runtimes & Build Tools
- **Ruby**: `ruby`, `ruby-dev`, `ruby-bundler`
- **Node.js**: `npm`, `nodeenv`, `yarnpkg`
- **Go**: `golang`
- **Clojure**: `clojure`, `leiningen`

### Databases
- `postgresql`, `libpq-dev`

### Graphics Libraries
- `libcairo2`, `libpango-1.0-0`, `libpangoft2-1.0-0`

## Usage Example

```python
from hop3.oses.debian12 import setup_server

# This would install all required packages and configure the system
setup_server()
```

**Note**: Currently this is not called from hop3's main code. See "Roadmap" below.

## Implementation Details

### User Account
- **Username**: `hop3`
- **Home Directory**: `/home/hop3`
- **Shell**: `/bin/bash`
- **Primary Group**: `www-data` (for nginx integration)

### Directory Structure
```
/home/hop3/
├── venv/                    # Python virtual environment
│   └── bin/
│       └── hop-server       # Hop3 server executable
└── .hop3/                   # Hop3 data directory (created by hop3)
    ├── apps/                # Deployed applications
    ├── nginx/               # Nginx configurations
    └── uwsgi/               # uWSGI configurations
```

### APT Configuration
Creates `/etc/apt/apt.conf.d/00-hop3` with optimizations:
- Disable recommended packages
- Disable suggested packages
- Enable gzip compression
- Optimize cache behavior

## Testing

Basic tests are in `packages/hop3-server/tests/a_unit/test_installer.py`:
- `test_put_file()` - Tests file creation
- `test_ensure_link()` - Tests symbolic link creation

**Note**: Package installation tests require root privileges and are not included in the regular test suite.

## Roadmap

### Short Term
- [ ] Integrate OS detection into hop3 installer
- [ ] Add automatic OS detection (`/etc/os-release` parsing)
- [ ] Create comprehensive integration tests
- [ ] Replace PyInfra installer with this abstraction

### Medium Term
- [ ] Add RHEL/CentOS/Rocky Linux support (YUM/DNF)
- [ ] Add Alpine Linux support (APK)
- [ ] Add Arch Linux support (Pacman)
- [ ] Complete NixOS implementation with configuration.nix generation

### Long Term
- [ ] Support for systemd service management
- [ ] Support for OpenRC (Alpine)
- [ ] Automated OS upgrade handling
- [ ] Docker container optimizations

## Related Files

- **Current Installer**: `installer/install-hop.py` (uses PyInfra)
- **Tests**: `packages/hop3-server/tests/a_unit/test_installer.py`
- **Plugin Duplicate**: `packages/hop3-server/src/hop3/plugins/oses/` (⚠️ should be consolidated)

## Contributing

When adding a new OS:

1. Create a new module file: `<distro><version>.py`
2. Import the appropriate base class from `helpers.py`
3. Define the `PACKAGES` list with OS-specific package names
4. Implement `setup_server()` function
5. Add entry to this README
6. Add integration test if possible

## License

Copyright (c) 2023-2025, Abilian SAS
SPDX-License-Identifier: Apache-2.0
