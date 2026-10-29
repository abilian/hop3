# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType


def scan_package(package_name: str) -> list[ModuleType]:
    """
    Import every module in a package (recursively) and return them.

    Callers import for the side effects (registration on import) and, like the
    plugin manager, may also use the modules. The import is eager: a lazy
    generator would import nothing for a caller that discards the result.
    """
    return [importlib.import_module(name) for name in _iter_module_names(package_name)]


def _iter_module_names(package_name: str) -> Iterator[str]:
    package_or_module = importlib.import_module(package_name)
    if not hasattr(package_or_module, "__path__"):
        # module, not package
        return

    path = package_or_module.__path__
    prefix = package_or_module.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(path, prefix):
        yield module_name
