# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Every toolchain must honour `[build].build`.

It was a convention each subclass had to remember, and seven of twelve did not:
php, node, go, rust and generic ran the recipe's build command while python,
java, ruby, elixir, clojure, dotnet and static silently ignored it. The same
recipe key therefore worked or did nothing depending on the language — and the
app that hit it (isso) shipped without its JavaScript bundles, which only
surfaced on somebody else's website.

A structural check, deliberately: the failure mode is "a toolchain forgot to
call it", which is exactly what this catches, and it costs nothing to run.
"""

from __future__ import annotations

import inspect
import pkgutil
from importlib import import_module

import pytest

import hop3.toolchains
from hop3.toolchains._base import LanguageToolchain


def _toolchain_classes() -> list[type[LanguageToolchain]]:
    """Every concrete toolchain shipped in hop3.toolchains."""
    found: list[type[LanguageToolchain]] = []
    for module_info in pkgutil.iter_modules(hop3.toolchains.__path__):
        if module_info.name.startswith("_"):
            continue
        module = import_module(f"hop3.toolchains.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, LanguageToolchain)
                and obj is not LanguageToolchain
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return found


def test_there_are_toolchains_to_check() -> None:
    """Guard the guard: an empty sweep would pass vacuously."""
    assert len(_toolchain_classes()) >= 10


@pytest.mark.parametrize(
    "toolchain", _toolchain_classes(), ids=lambda c: c.__module__.rsplit(".", 1)[-1]
)
def test_toolchain_honours_a_declared_build(toolchain) -> None:
    """
    The toolchain must consult the recipe's build command somewhere.

    Either through the shared `_run_declared_build` helper or by calling
    `_get_custom_build_command` itself — both are real implementations; only
    ignoring the key is not.
    """
    source = inspect.getsource(toolchain)

    honoured = "_run_declared_build" in source or "_get_custom_build_command" in source

    assert honoured, (
        f"{toolchain.__module__} ignores [build].build: a recipe declaring one "
        f"would have it silently dropped. Call self._run_declared_build() where "
        f"the toolchain installs dependencies, and skip that step when it "
        f"returns True."
    )
