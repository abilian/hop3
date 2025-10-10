# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""OS-specific setup scripts for hop3 server installation.

This module provides a declarative abstraction layer for installing hop3
dependencies on various Linux distributions. Each OS-specific module defines
the required packages, user configuration, and system setup.

## Status: NOT YET INTEGRATED

These modules are currently **stubs** and are not yet used in production.
The actual installation is performed by `installer/install-hop.py` (PyInfra).

## Supported Distributions

- Debian 12 (Bookworm), Debian 13 (Trixie)
- Ubuntu 22.04 LTS (Jammy), Ubuntu 24.04 LTS (Noble)
- NixOS (stub implementation)

## Architecture

Base classes in `helpers.py`:
- `Platform`: Base class for all platforms
- `Linux`: Linux-specific operations (files, links, users)
- `Debian`: Debian/Ubuntu APT package management

Each OS module provides a `setup_server()` function that:
1. Configures package manager settings
2. Creates the hop3 user account
3. Installs required system packages
4. Sets up necessary symbolic links

## Example Usage

```python
from hop3.oses.debian12 import setup_server

# This would install all required packages and configure the system
setup_server()
```

## Roadmap

See `hop3/oses/README.md` for detailed roadmap and integration plans.

The goal is to replace the PyInfra-based installer with this abstraction
and provide automatic OS detection and setup.
"""

from __future__ import annotations

__all__ = [
    # "debian",
    # "debian12",
    # "debian13",
    # "ubuntu2204",
    # "ubuntu2404",
    # "nixos",
    # "helpers",
]
