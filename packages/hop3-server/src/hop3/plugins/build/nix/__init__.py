# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Nix build plugin for Hop3.

This plugin provides NixBuilder, which builds applications using
user-provided hop3.nix files. Phase 1 of Nix integration.

The plugin instance is exported from plugin.py, not from this __init__.py.
This avoids duplicate registration during package discovery, since
pkgutil.walk_packages() discovers both the package (__init__.py) and
the plugin.py submodule. Only plugin.py exports the plugin instance.
"""

from __future__ import annotations
