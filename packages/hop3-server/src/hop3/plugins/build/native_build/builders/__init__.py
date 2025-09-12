# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builders for various languages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .clojure import ClojureBuilder
from .go import GoBuilder
from .node import NodeBuilder
from .python import PythonBuilder
from .ruby import RubyBuilder
from .rust import RustBuilder

if TYPE_CHECKING:
    from ._base import Builder

BUILDER_CLASSES: list[type[Builder]] = [
    PythonBuilder,
    RubyBuilder,
    NodeBuilder,
    ClojureBuilder,
    GoBuilder,
    RustBuilder,
]
