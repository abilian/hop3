# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchains plugin package.

Provides Level 2 toolchains (PythonToolchain, NodeToolchain, etc.)
that are used by LocalBuilder to build applications.

The plugin instance is exported from plugin.py, not from this __init__.py.
This avoids duplicate registration during package discovery, since
pkgutil.walk_packages() discovers both the package (__init__.py) and
the plugin.py submodule. Only plugin.py exports the plugin instance.
"""

from __future__ import annotations
