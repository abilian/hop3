# OS Setup Strategy Plugins

This directory contains plugins for setting up hop3 on different operating systems. Each plugin implements the `OS` protocol and can auto-detect whether it matches the current system.

## Architecture

### Plugin System

OS setup is handled through hop3's plugin system:

```
OS Protocol (protocols.py)
    ↓
get_os_implementations() hookspec (hookspecs.py)
    ↓
Plugin Registration (each OS plugin)
    ↓
Auto-discovery via get_os_strategy() (plugins.py)
```

### Base Classes

- **`BaseOSStrategy`** (`base.py`): Provides common functionality for all OS strategies
  - OS detection helpers (`read_os_release()`)
  - User creation (`ensure_user()`)
  - File operations (`put_file()`)
  - Symbolic link creation (`ensure_link()`)

- **`DebianBase`** (`debian_base.py`): Adds APT package management
  - `ensure_packages()` using apt-get

### Plugin Structure

Each OS plugin consists of:

1. **Strategy Class**: Implements `OS` protocol
   - `name`: Unique identifier (e.g., "debian12")
   - `display_name`: Human-readable name (e.g., "Debian 12 (Bookworm)")
   - `packages`: List of required packages
   - `detect()`: Returns True if this OS matches
   - `setup_server()`: Performs installation and configuration

2. **Plugin Class**: Provides the strategy via hooks
   - Implements `@hop3_hook_impl` decorated `get_os_implementations()`
   - Returns list containing the Strategy class

3. **Plugin Instance**: For auto-discovery
   - Module-level `plugin` variable

## Available OS Plugins

| Plugin | OS Support | Detection |
|--------|-----------|-----------|
| `debian_family.py` | **All Debian-based distributions** | ID=debian, ubuntu, or ID_LIKE=debian |
| `redhat_family.py` | **All Red Hat-based distributions** | ID=rhel, rocky, almalinux, fedora, centos, or ID_LIKE=rhel/fedora |
| `arch.py` | **Arch Linux and derivatives** | ID=arch, manjaro, endeavouros, or ID_LIKE=arch |
| `macos.py` | **macOS (all versions)** | platform.system() == "Darwin" |
| `bsd.py` | **BSD systems** | platform.system() in ("FreeBSD", "OpenBSD", "NetBSD") |

**Supported distributions:**

### Debian Family
- Debian (all versions: 11, 12, 13, etc.)
- Ubuntu (all versions: 20.04, 22.04, 24.04, etc.)
- Linux Mint, Pop!_OS, and other Debian derivatives

### Red Hat Family
- RHEL (Red Hat Enterprise Linux) - all versions
- Rocky Linux - all versions
- AlmaLinux - all versions
- Fedora - all versions
- CentOS - all versions

### Arch Family
- Arch Linux
- Manjaro
- EndeavourOS

### macOS
- macOS (all versions, requires Homebrew)

### BSD
- FreeBSD (all versions)
- OpenBSD (all versions)

All plugins auto-detect the specific version from `/etc/os-release` (Linux) or `platform` module (macOS/BSD) and use it for the display name.

## Adding a New OS

### Example: Adding Alpine Linux

1. **Create the plugin file**: `alpine.py`

```python
# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import subprocess
from hop3.core.hooks import hop3_hook_impl
from .base import BaseOSStrategy

# Package list (apk names)
PACKAGES = [
    "git",
    "python3",
    "py3-pip",
    "py3-virtualenv",
    "nginx",
    "nodejs",
    "npm",
    "postgresql",
    # ... more packages
]

class AlpineStrategy(BaseOSStrategy):
    """OS setup strategy for Alpine Linux."""

    name = "alpine"
    packages = PACKAGES

    @property
    def display_name(self) -> str:
        """Get display name from /etc/os-release."""
        os_info = self.read_os_release()
        return os_info.get("PRETTY_NAME", "Alpine Linux")

    def detect(self) -> bool:
        """Check if this is Alpine Linux."""
        os_info = self.read_os_release()
        return os_info.get("ID") == "alpine"

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using apk."""
        if update:
            subprocess.run(["apk", "update"], check=True, capture_output=True)

        packages_str = " ".join(packages)
        cmd = f"apk add {packages_str}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)

    def setup_server(self) -> None:
        """Install dependencies and configure Alpine for hop3."""
        # Create hop3 user
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/sh",
            group="nginx",  # Alpine uses 'nginx' group
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Enable services
        subprocess.run(["rc-update", "add", "nginx"], check=True)


class AlpinePlugin:
    """Plugin that provides Alpine Linux OS setup strategy."""

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [AlpineStrategy]


# Plugin instance for auto-discovery
plugin = AlpinePlugin()
```

2. **That's it!** The plugin will be auto-discovered when hop3 starts.

## Usage

### Auto-detect Current OS

```python
from hop3.core.plugins import get_os_strategy

# Auto-detect and return the appropriate strategy
strategy = get_os_strategy()
print(f"Detected: {strategy.display_name}")  # e.g., "Debian GNU/Linux 12 (bookworm)"

# Run server setup
strategy.setup_server()
```

### List Supported OSes

```python
from hop3.core.plugins import list_supported_os

supported = list_supported_os()
print(supported)
# Output varies based on /etc/os-release:
# ['Debian GNU/Linux 12 (bookworm)'] on Debian 12
# ['Ubuntu 22.04.3 LTS'] on Ubuntu 22.04
```

### Manual Selection

```python
from hop3.plugins.oses.debian_family import DebianFamilyStrategy

strategy = DebianFamilyStrategy()
if strategy.detect():
    print(f"Setting up {strategy.display_name}")
    strategy.setup_server()
```

## Testing

Test your OS plugin by:

1. **Unit Test Detection**:
```python
def test_detect_debian(monkeypatch):
    """Test detection of Debian-based distributions."""
    from hop3.plugins.oses.debian_family import DebianFamilyStrategy

    def mock_read():
        return {"ID": "debian", "VERSION_ID": "12", "PRETTY_NAME": "Debian GNU/Linux 12 (bookworm)"}

    strategy = DebianFamilyStrategy()
    monkeypatch.setattr(strategy, "read_os_release", mock_read)
    assert strategy.detect() is True
    assert "Debian" in strategy.display_name

def test_detect_ubuntu(monkeypatch):
    """Test detection of Ubuntu."""
    from hop3.plugins.oses.debian_family import DebianFamilyStrategy

    def mock_read():
        return {"ID": "ubuntu", "VERSION_ID": "22.04", "PRETTY_NAME": "Ubuntu 22.04.3 LTS"}

    strategy = DebianFamilyStrategy()
    monkeypatch.setattr(strategy, "read_os_release", mock_read)
    assert strategy.detect() is True
    assert "Ubuntu" in strategy.display_name
```

2. **Integration Test** (requires actual OS):
```bash
# In a Debian 12 container
python3 -c "from hop3.core.plugins import get_os_strategy; print(get_os_strategy().display_name)"
# Should print: Debian GNU/Linux 12 (bookworm)

# In an Ubuntu 22.04 container
python3 -c "from hop3.core.plugins import get_os_strategy; print(get_os_strategy().display_name)"
# Should print: Ubuntu 22.04.3 LTS
```

## Package Requirements by OS Family

### Debian/Ubuntu (Single Generic Plugin!)

The `debian_family.py` plugin handles **all Debian and Ubuntu versions** with the same package list because:
- ✅ Package names are consistent across Debian/Ubuntu versions
- ✅ APT is the standard package manager for all versions
- ✅ System paths (nodejs, yarnpkg) are consistent
- ✅ Group name (`www-data`) is consistent

**Package Manager:** `apt-get`
**User Group:** `www-data`
**Package Naming:** `python3-*` format

This means:
- **No need for version-specific plugins** - one plugin covers Debian 11, 12, 13, and all Ubuntu LTS versions
- **Automatic version detection** - the display name comes from `/etc/os-release`
- **Works with derivatives** - Linux Mint, Pop!_OS, etc. automatically supported

### Red Hat Family (RHEL/Rocky/Alma/Fedora/CentOS)

The `redhat_family.py` plugin handles **all Red Hat-based distributions**:
- ✅ Package names are consistent across RHEL family
- ✅ DNF/YUM work across all versions (auto-detects which to use)
- ✅ Group name (`nginx`) is consistent

**Package Manager:** `dnf` (or `yum` for older systems)
**User Group:** `nginx`
**Package Naming:** `python3*` or version-specific like `python39`

### Arch Linux

The `arch.py` plugin handles **Arch Linux and derivatives**:

**Package Manager:** `pacman`
**User Group:** `http`
**Package Naming:** `python-*` format (no version number)

### macOS

The `macos.py` plugin handles **macOS** using Homebrew:
- ⚠️ Requires Homebrew to be pre-installed (https://brew.sh)

**Package Manager:** `brew`
**User Group:** `staff`
**Package Naming:** Formula names (e.g., `python@3.11`, `node`, `postgresql@15`)

### BSD (FreeBSD/OpenBSD)

The `bsd.py` plugin handles **BSD systems**:

**FreeBSD:**
- Package Manager: `pkg`
- User Group: `www`
- Package Naming: Version-specific (e.g., `python39`, `postgresql15-server`)

**OpenBSD:**
- Package Manager: `pkg_add`
- User Group: `www`
- Package Naming: Generic with py3 prefix (e.g., `py3-pip`)

## Tips

1. **Inherit from base classes** to reuse functionality
2. **Keep package lists comprehensive** - include all buildpacks
3. **Make detect() specific** - check both ID and VERSION_ID
4. **Make setup_server() idempotent** - safe to run multiple times
5. **Document package name differences** in comments

## Related Files

- Core Protocol: `packages/hop3-server/src/hop3/core/protocols.py` (OS)
- Hookspec: `packages/hop3-server/src/hop3/core/hookspecs.py` (get_os_implementations)
- Discovery: `packages/hop3-server/src/hop3/core/plugins.py` (get_os_strategy)
- Legacy Modules: `packages/hop3-server/src/hop3/oses/` (to be deprecated)
