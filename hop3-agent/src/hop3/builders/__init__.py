# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .clojure import ClojureBuilder
from .go import GoBuilder
from .node import NodeBuilder
from .python import PythonBuilder
from .ruby import RubyBuilder

BUILDER_CLASSES = [
    PythonBuilder,
    RubyBuilder,
    NodeBuilder,
    ClojureBuilder,
    GoBuilder,
]
