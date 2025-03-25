# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

import pluggy
from pluggy import PluginManager

from hop3.core import hookspecs

if TYPE_CHECKING:
    from collections.abc import Iterator


def get_core_plugins() -> list:
    """Retrieve a list of core plugins.

    This scans the specified package for core plugins and returns a
    list of these plugins.

    Returns:
    - list: A list containing the core plugins found in the specified package.
    """
    return list(scan_package("hop3.plugins"))


def scan_package(package_name: str) -> Iterator:
    """Import all modules in a package recursively for side effects.

    Input:
    - package_name (str): The name of the package to scan and import modules from.

    Returns:
    - Iterator: An iterator that yields each module imported from the package.
    """
    for module_name in _iter_module_names(package_name):
        # Import the module by name and yield it
        yield importlib.import_module(module_name)


def _iter_module_names(package_name: str) -> Iterator:
    """Generate an iterator over all module names within a given package.

    Input:
    - package_name (str): The name of the package from which to list all modules.

    Returns:
    - Iterator: Yields the names of the modules within the specified package.
    """
    package_or_module = importlib.import_module(package_name)
    if not hasattr(package_or_module, "__path__"):
        # If the imported object is a module, not a package, exit the function.
        return

    path = package_or_module.__path__
    prefix = package_or_module.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(path, prefix):
        # Yield the name of each module found in the package.
        yield module_name


def get_plugin_manager() -> PluginManager:
    """Initialize and configure a PluginManager for the 'hop3' project.

    This creates a PluginManager instance, registers core plugin hooks,
    and loads plugins that are defined in setuptools entry points under the
    'hop3' category.

    Returns:
        PluginManager: An instance of PluginManager configured with core plugins and entry points.
    """
    pm = pluggy.PluginManager("hop3")
    pm.add_hookspecs(hookspecs)

    for plugin in get_core_plugins():
        pm.register(plugin)

    # For plugins that are not built-in, we load them from setuptools entry points
    pm.load_setuptools_entrypoints("hop3")

    return pm
