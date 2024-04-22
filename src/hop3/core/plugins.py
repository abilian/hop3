# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator

import pluggy
from pluggy import PluginManager

from hop3.core import hookspecs


def get_core_plugins() -> list:
    """Return a list of core plugins."""
    return list(scan_package("hop3.commands.plugins"))


def scan_package(package_name: str) -> Iterator:
    """Import all modules in a package (recursively), for side effects."""
    for module_name in _iter_module_names(package_name):
        yield importlib.import_module(module_name)


def _iter_module_names(package_name: str) -> Iterator:
    package_or_module = importlib.import_module(package_name)
    if not hasattr(package_or_module, "__path__"):
        # module, not package
        return

    path = package_or_module.__path__
    prefix = package_or_module.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(path, prefix):
        yield module_name


def get_plugin_manager() -> PluginManager:
    pm = pluggy.PluginManager("hop3")
    pm.add_hookspecs(hookspecs)

    for plugin in get_core_plugins():
        pm.register(plugin)

    pm.load_setuptools_entrypoints("hop3")

    return pm
