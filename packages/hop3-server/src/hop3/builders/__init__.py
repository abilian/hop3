# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchains for various languages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .clojure import ClojureToolchain
from .go import GoToolchain
from .node import NodeToolchain
from .python import PythonToolchain
from .ruby import RubyToolchain
from .rust import RustToolchain
from .static import StaticToolchain

if TYPE_CHECKING:
    from ._base import LanguageToolchain

TOOLCHAIN_CLASSES: list[type[LanguageToolchain]] = [
    StaticToolchain,  # Try static first (fastest detection)
    PythonToolchain,
    RubyToolchain,
    NodeToolchain,
    ClojureToolchain,
    GoToolchain,
    RustToolchain,
]
